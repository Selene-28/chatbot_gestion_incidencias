#!/bin/sh
# Uvicorn primero (puerto de Railway). MySQL y migraciones no pueden
# tumbar el proceso: si salen mal, /healthz sigue en 200 y Railway no pone Crashed.
set -eu

MAX_ATTEMPTS="${DB_WAIT_ATTEMPTS:-60}"
SLEEP_SECONDS=2
PRIV_PORT=8001

if grep -q railway.internal /etc/resolv.conf 2>/dev/null \
  || [ -n "${RAILWAY_ENVIRONMENT:-}${RAILWAY_PROJECT_ID:-}" ]; then
  APP_PORT="${PORT:-8080}"
else
  APP_PORT="${PORT:-$PRIV_PORT}"
fi

# En Railway el volumen /data/uploads a menudo es del root y el USER app no escribe.
UPLOADS="${UPLOADS_DIR:-/data/uploads}"
if ! mkdir -p "$UPLOADS" 2>/dev/null || ! touch "$UPLOADS/.write_test" 2>/dev/null; then
  UPLOADS="${HOME:-/tmp}/uploads"
  mkdir -p "$UPLOADS"
  export UPLOADS_DIR="$UPLOADS"
  echo "[entrypoint] AVISO: carpeta de adjuntos no escribible; usando ${UPLOADS_DIR}"
else
  rm -f "$UPLOADS/.write_test"
  echo "[entrypoint] adjuntos en ${UPLOADS}"
fi

echo "[entrypoint] uvicorn 0.0.0.0:${APP_PORT} (PORT=${PORT:-unset})"
uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" \
  --proxy-headers --forwarded-allow-ips='*' &
MAIN_PID=$!

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
from app.core.mysql_url import url_mysql_sync
url = url_mysql_sync(get_settings().DB_URL)
sa.create_engine(url, connect_args={'connect_timeout': 3}).connect().close()
" 2>/dev/null; do
    if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
      echo "[entrypoint] AVISO: MySQL no aceptó conexiones; /healthz sigue vivo" >&2
      exit 0
    fi
    echo "[entrypoint] MySQL aún no está listo (intento ${attempt}/${MAX_ATTEMPTS})..."
    attempt=$((attempt + 1))
    sleep "$SLEEP_SECONDS"
  done
  echo "[entrypoint] alembic upgrade head..."
  alembic upgrade head || echo "[entrypoint] AVISO: alembic falló" >&2
) &

wait "$MAIN_PID"
