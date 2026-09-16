#!/bin/sh
# Entrypoint del contenedor: espera a que MySQL acepte conexiones, aplica las
# migraciones UNA sola vez (un error real de SQL debe abortar, no reintentarse:
# el DDL de MySQL no es transaccional y reintentar deja el esquema a medias)
# y luego levanta la API con uvicorn.
set -eu

MAX_ATTEMPTS="${DB_WAIT_ATTEMPTS:-60}"
SLEEP_SECONDS=2

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
  echo "[entrypoint] Cargando base de conocimiento (CARGAR_KB_AL_ARRANCAR=1)..."
  python -m app.scripts.cargar_kb
fi

echo "[entrypoint] Iniciando uvicorn en 0.0.0.0:${PORT:-8000}..."
# 0.0.0.0 = IPv4 (dominio público de Railway). :: solo IPv6 no recibe el proxy.
if [ -n "${PORT:-}" ] && [ "${PORT}" != "8000" ]; then
  echo "[entrypoint] también en 0.0.0.0:8000"
  uvicorn app.main:app --host 0.0.0.0 --port 8000 &
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
