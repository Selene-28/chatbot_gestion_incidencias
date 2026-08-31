#!/usr/bin/env bash
# Restauración de un respaldo del chatbot CTIC-FIIS UNAC (prd/07 §6).
#
# Uso:  ./deploy/restore.sh /ruta/backups/20260705_023000
# Restaura ambos esquemas MySQL y el volumen de adjuntos, y reconstruye el
# índice vectorial Chroma (reindex) desde kb_articulos.
set -euo pipefail

DIR="${1:?Uso: ./deploy/restore.sh <carpeta_de_respaldo>}"
COMPOSE="${COMPOSE:-docker compose}"

if [ -f .env ]; then
  ROOT_PWD="$(grep -E '^DB_ROOT_PASSWORD=' .env | cut -d= -f2-)"
fi
: "${ROOT_PWD:?Define DB_ROOT_PASSWORD en .env}"

echo "[restore] restaurando MySQL desde ${DIR}/mysql_chatbot_tickets.sql.gz ..."
gunzip -c "${DIR}/mysql_chatbot_tickets.sql.gz" \
  | ${COMPOSE} exec -T mysql sh -c "exec mysql -uroot -p\"${ROOT_PWD}\""

if [ -f "${DIR}/uploads.tar.gz" ]; then
  echo "[restore] restaurando adjuntos..."
  tmp="$(mktemp -d)"
  tar -C "${tmp}" -xzf "${DIR}/uploads.tar.gz"
  ${COMPOSE} cp "${tmp}/uploads/." ticket-service:/data/uploads/ || true
  rm -rf "${tmp}"
fi

echo "[restore] reconstruyendo el índice vectorial (reindex)..."
${COMPOSE} exec -T chatbot-api python -m app.scripts.reindex || \
  echo "[restore] (reindex falló o servicio abajo; ejecútalo manualmente luego)"

echo "[restore] OK"
