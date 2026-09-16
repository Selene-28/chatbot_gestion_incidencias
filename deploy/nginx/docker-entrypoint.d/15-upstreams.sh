#!/bin/sh
# Prepara variables para las plantillas de nginx (Docker y Railway).
# El entrypoint oficial (20-envsubst-on-templates.sh) corre después de este.
set -eu

export LISTEN_PORT="${PORT:-${LISTEN_PORT:-80}}"
export CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM:-http://chatbot-api:8000}"
export TICKETS_UPSTREAM="${TICKETS_UPSTREAM:-http://ticket-service:8001}"
echo "[nginx] escuchando LISTEN_PORT=${LISTEN_PORT} (PORT=${PORT:-unset})"

if [ -z "${NGINX_RESOLVER:-}" ]; then
  NS="$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null || true)"
  [ -n "$NS" ] || NS="127.0.0.11"
  case "$NS" in
    *:*) NS="[$NS]" ;;
  esac
  export NGINX_RESOLVER="$NS"
fi
