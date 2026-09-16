#!/bin/sh
# Entrypoint: MySQL → migraciones UNA vez → uvicorn.
# En Railway el proxy público habla IPv4:8080 desde el segundo 1; el mesh
# interno habla IPv6. Si el puerto se abre tarde, el visitante ve 502.
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

abrir_placeholder() {
  puerto="$1"
  PORT_PLACEHOLDER="$puerto" python -c '
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(os.environ["PORT_PLACEHOLDER"])

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"{\"status\":\"starting\"}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args):
        return

print("[entrypoint] placeholder 0.0.0.0:%s" % port, flush=True)
HTTPServer(("0.0.0.0", port), H).serve_forever()
' &
  echo $! > "/tmp/placeholder-${puerto}.pid"
}

cerrar_placeholder() {
  puerto="$1"
  pidfile="/tmp/placeholder-${puerto}.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pidfile"
  fi
}

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

# --- Railway: abrir 8080 YA, antes de MySQL / KB ---
if [ "$on_railway" = "1" ]; then
  echo "[entrypoint] Railway detectado; PORT=${PORT:-unset} APP_PORT=${APP_PORT}"
  abrir_placeholder "$APP_PORT"
  escuchar_ipv6 "$APP_PORT"
  if [ "$APP_PORT" != "$PRIV_PORT" ]; then
    abrir_placeholder "$PRIV_PORT"
    escuchar_ipv6 "$PRIV_PORT"
  fi
  if [ "$APP_PORT" != "8080" ]; then
    abrir_placeholder 8080
    escuchar_ipv6 8080
  fi
fi

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

if [ "$on_railway" = "1" ]; then
  cerrar_placeholder "$APP_PORT"
  if [ "$APP_PORT" != "$PRIV_PORT" ]; then
    cerrar_placeholder "$PRIV_PORT"
    echo "[entrypoint] también en 0.0.0.0:${PRIV_PORT}"
    uvicorn app.main:app --host 0.0.0.0 --port "$PRIV_PORT" --proxy-headers --forwarded-allow-ips='*' &
  fi
  if [ "$APP_PORT" != "8080" ]; then
    cerrar_placeholder 8080
    echo "[entrypoint] también en 0.0.0.0:8080 (dominio público Railway)"
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*' &
  fi
elif [ -n "${PORT:-}" ] && [ "$APP_PORT" != "$PRIV_PORT" ]; then
  echo "[entrypoint] también en 0.0.0.0:${PRIV_PORT}"
  uvicorn app.main:app --host 0.0.0.0 --port "$PRIV_PORT" --proxy-headers --forwarded-allow-ips='*' &
fi

echo "[entrypoint] Iniciando uvicorn en 0.0.0.0:${APP_PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" --proxy-headers --forwarded-allow-ips='*'
