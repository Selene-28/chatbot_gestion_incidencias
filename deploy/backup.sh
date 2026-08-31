#!/usr/bin/env bash
# Respaldo del chatbot CTIC-FIIS UNAC (prd/07 §6).
#
# Respalda:
#   - Ambos esquemas MySQL (chatbot_db y tickets_db) con mysqldump.
#   - El volumen de adjuntos (evidencias de incidencias).
# El índice vectorial Chroma NO se respalda: se reconstruye con `reindex`
# desde kb_articulos (idempotente).
#
# Uso:  DEST=/ruta/backups ./deploy/backup.sh
# Recomendado: cron diario (ver crontab de ejemplo al final del archivo).
set -euo pipefail

DEST="${DEST:-./backups}"
RETENCION_DIAS="${RETENCION_DIAS:-30}"
COMPOSE="${COMPOSE:-docker compose}"
FECHA="$(date +%Y%m%d_%H%M%S)"
DIR="${DEST}/${FECHA}"

mkdir -p "${DIR}"
echo "[backup] destino: ${DIR}"

# Contraseña root desde el .env (no se imprime)
if [ -f .env ]; then
  # shellcheck disable=SC1091
  ROOT_PWD="$(grep -E '^DB_ROOT_PASSWORD=' .env | cut -d= -f2-)"
fi
: "${ROOT_PWD:?Define DB_ROOT_PASSWORD en .env}"

echo "[backup] volcando esquemas MySQL..."
${COMPOSE} exec -T mysql sh -c \
  "exec mysqldump -uroot -p\"${ROOT_PWD}\" --databases chatbot_db tickets_db \
   --single-transaction --routines --triggers" \
  | gzip > "${DIR}/mysql_chatbot_tickets.sql.gz"

echo "[backup] copiando volumen de adjuntos..."
${COMPOSE} cp ticket-service:/data/uploads "${DIR}/uploads" 2>/dev/null || \
  echo "[backup] (sin adjuntos o ruta no montada; se omite)"
if [ -d "${DIR}/uploads" ]; then
  tar -C "${DIR}" -czf "${DIR}/uploads.tar.gz" uploads && rm -rf "${DIR}/uploads"
fi

echo "[backup] purga de respaldos > ${RETENCION_DIAS} días..."
find "${DEST}" -maxdepth 1 -type d -name '20*' -mtime "+${RETENCION_DIAS}" -exec rm -rf {} + 2>/dev/null || true

echo "[backup] OK — ${DIR}"

# --- Ejemplo de cron (diario 02:30) -------------------------------------------
#   30 2 * * *  cd /opt/chatbot-ctic && DEST=/var/backups/chatbot ./deploy/backup.sh >> /var/log/chatbot-backup.log 2>&1
