#!/bin/sh
# Entrypoint del contenedor: espera a que MySQL acepte conexiones, aplica las
# migraciones UNA sola vez (un error real de SQL debe abortar, no reintentarse:
# el DDL de MySQL no es transaccional y reintentar deja el esquema a medias)
# y luego levanta la API con uvicorn.
set -eu

MAX_ATTEMPTS="${DB_WAIT_ATTEMPTS:-60}"
SLEEP_SECONDS=2

# Railway inyecta PORT (casi siempre 8080) y habla IPv4 al dominio público.
# El mesh privado (*.railway.internal) habla IPv6. Hay que escuchar los dos.
if [ -n "${RAILWAY_ENVIRONMENT:-}" ] && [ -z "${PORT:-}" ]; then
  PORT=8080
  export PORT
fi
APP_PORT="${PORT:-8000}"
PRIV_PORT=8000

# Reenvía [::]:PUERTO → 127.0.0.1:PUERTO (IPv6 del mesh → uvicorn IPv4).
escuchar_ipv6() {
  puerto="$1"
  (
  python - "$puerto" <<'PY'
import socket
import sys
import threading

port = int(sys.argv[1])

def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            src.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            dst.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        src.close()
        dst.close()

def handle(client):
    try:
        upstream = socket.create_connection(("127.0.0.1", port), timeout=5)
    except OSError:
        client.close()
        return
    threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
    pipe(upstream, client)

sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
sock.bind(("::", port))
sock.listen(128)
print(f"[entrypoint] IPv6 [::]:{port} → 127.0.0.1:{port}", flush=True)
while True:
    client, _ = sock.accept()
    threading.Thread(target=handle, args=(client,), daemon=True).start()
PY
  ) &
}

attempt=1
until python -c "
import sqlalchemy as sa
from app.core.config import get_settings
url = get_settings().DB_URL.replace('+asyncmy', '+pymysql')
sa.create_engine(url, connect_args={'connect_timeout': 3}).connect().close()
" 2>/dev/null; do
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "[entrypoint] ERROR: MySQL no aceptó conexiones tras ${MAX_ATTEMPTS} intentos" >&2
    exit 1
  fi
  echo "[entrypoint] MySQL aún no está listo (intento ${attempt}/${MAX_ATTEMPTS}); reintentando en ${SLEEP_SECONDS}s..."
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done

echo "[entrypoint] Aplicando migraciones (alembic upgrade head)..."
alembic upgrade head

if [ "${CARGAR_KB_AL_ARRANCAR:-0}" = "1" ]; then
  echo "[entrypoint] Cargando base de conocimiento en segundo plano..."
  python -m app.scripts.cargar_kb &
fi

escuchar_ipv6 "$APP_PORT"
if [ "$APP_PORT" != "$PRIV_PORT" ]; then
  echo "[entrypoint] también en 0.0.0.0:${PRIV_PORT} (mesh interno)"
  escuchar_ipv6 "$PRIV_PORT"
  uvicorn app.main:app --host 0.0.0.0 --port "$PRIV_PORT" --proxy-headers --forwarded-allow-ips='*' &
fi

echo "[entrypoint] Iniciando uvicorn en 0.0.0.0:${APP_PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" --proxy-headers --forwarded-allow-ips='*'
