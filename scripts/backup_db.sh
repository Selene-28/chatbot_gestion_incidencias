#!/usr/bin/env bash
# Respaldo (.sql) de chatbot_db y tickets_db hacia una carpeta local en la
# PC del admin. Complementa al volumen `mysql_data` de Docker (que ya
# persiste los datos automáticamente): esto genera además archivos .sql
# portables, fáciles de copiar a un USB, subir a la nube, etc.
#
# Uso:
#   ./scripts/backup_db.sh              # respaldo a ./backups (por defecto)
#   ./scripts/backup_db.sh /ruta/otra    # respaldo a una carpeta específica
#
# Requiere: el contenedor `mysql` corriendo (docker compose up) y el .env
# del proyecto con DB_ROOT_PASSWORD (mismo que usa docker-compose.yml).
#
# Idempotente y seguro de repetir: cada corrida crea archivos nuevos con
# fecha y hora en el nombre; nunca sobrescribe ni borra respaldos previos.

set -euo pipefail

CARPETA_DESTINO="${1:-./backups}"
RAIZ_PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVO_ENV="${RAIZ_PROYECTO}/.env"

if [[ ! -f "${ARCHIVO_ENV}" ]]; then
  echo "No se encontró ${ARCHIVO_ENV}. Copia .env.example a .env primero." >&2
  exit 1
fi

# Carga solo DB_ROOT_PASSWORD del .env, sin exportar todo el archivo.
DB_ROOT_PASSWORD="$(grep -E '^DB_ROOT_PASSWORD=' "${ARCHIVO_ENV}" | cut -d '=' -f2-)"
: "${DB_ROOT_PASSWORD:?No se encontró DB_ROOT_PASSWORD en .env}"

mkdir -p "${CARPETA_DESTINO}"
MARCA_TIEMPO="$(date +%Y%m%d_%H%M%S)"

respaldar() {
  local base_datos="$1"
  local destino="${CARPETA_DESTINO}/${base_datos}_${MARCA_TIEMPO}.sql"
  echo "Respaldando ${base_datos} → ${destino}"
  docker compose -f "${RAIZ_PROYECTO}/docker-compose.yml" exec -T mysql \
    mysqldump --user=root --password="${DB_ROOT_PASSWORD}" \
    --single-transaction --routines --triggers "${base_datos}" \
    > "${destino}"
}

respaldar chatbot_db
respaldar tickets_db

echo "Listo. Respaldos guardados en: $(cd "${CARPETA_DESTINO}" && pwd)"
