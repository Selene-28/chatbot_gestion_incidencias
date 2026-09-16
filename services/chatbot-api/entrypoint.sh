#!/bin/sh
# MySQL y migraciones no pueden bloquear el puerto: en Railway el 502
# aparece si 8080 no atiende con la API real (POST /api/chat, etc.).
set -eu

MAX_ATTEMPTS="${DB_WAIT_ATTEMPTS:-60}"
SLEEP_SECONDS=2
PRIV_PORT=8000

on_railway=0
if [ -n "${RAILWAY_ENVIRONMENT:-}${RAILWAY_PROJECT_ID:-}${RAILWAY_PRIVATE_DOMAIN:-}" ]; then
  on_railway=1
fi
if grep -q railway.internal /etc/resolv.conf 2>/dev/null; then
  on_railway=1
fi
if [ "$on_railway" = "1" ] && [ -z "${PORT:-}" ]; then
  PORT=8080
  export PORT
fi
APP_PORT="${PORT:-$PRIV_PORT}"
if [ "$on_railway" = "1" ]; then
  APP_PORT="${PORT:-8080}"
fi

escuchar_ipv6() {
  puerto="$1"
  PORT_V6="$puerto" python -c '
import os, socket, threading

port = int(os.environ["PORT_V6"])

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
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()

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
print("[entrypoint] IPv6 [::]:%s -> 127.0.0.1:%s" % (port, port), flush=True)
while True:
    client, _ = sock.accept()
    threading.Thread(target=handle, args=(client,), daemon=True).start()
' &
}

iniciar_uvicorn() {
  puerto="$1"
  echo "[entrypoint] uvicorn 0.0.0.0:${puerto}"
  uvicorn app.main:app --host 0.0.0.0 --port "$puerto" \
    --proxy-headers --forwarded-allow-ips='*' &
}

echo "[entrypoint] on_railway=${on_railway} PORT=${PORT:-unset} APP_PORT=${APP_PORT}"
iniciar_uvicorn "$APP_PORT"
MAIN_PID=$!
escuchar_ipv6 "$APP_PORT"

if [ "$on_railway" = "1" ] && [ "$APP_PORT" != "$PRIV_PORT" ]; then
  iniciar_uvicorn "$PRIV_PORT"
  escuchar_ipv6 "$PRIV_PORT"
fi
if [ "$on_railway" = "1" ] && [ "$APP_PORT" != "8080" ]; then
  iniciar_uvicorn 8080
  escuchar_ipv6 8080
fi

term() {
  kill "$MAIN_PID" 2>/dev/null || true
  wait "$MAIN_PID" 2>/dev/null || true
  exit 0
}
trap term TERM INT

(
  attempt=1
  until python -c "
import sqlalchemy as sa
from app.core.config import get_settings
url = get_settings().DB_URL.replace('+asyncmy', '+pymysql')
sa.create_engine(url, connect_args={'connect_timeout': 3}).connect().close()
" 2>/dev/null; do
    if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
      echo "[entrypoint] AVISO: MySQL no aceptó conexiones; la API sigue en ${APP_PORT}" >&2
      exit 0
    fi
    echo "[entrypoint] MySQL aún no está listo (intento ${attempt}/${MAX_ATTEMPTS})..."
    attempt=$((attempt + 1))
    sleep "$SLEEP_SECONDS"
  done
  echo "[entrypoint] Aplicando migraciones (alembic upgrade head)..."
  alembic upgrade head || echo "[entrypoint] AVISO: alembic falló" >&2
  if [ "${CARGAR_KB_AL_ARRANCAR:-0}" = "1" ]; then
    echo "[entrypoint] Cargando base de conocimiento..."
    python -m app.scripts.cargar_kb || echo "[entrypoint] AVISO: cargar_kb falló" >&2
  fi
) &

wait "$MAIN_PID"
