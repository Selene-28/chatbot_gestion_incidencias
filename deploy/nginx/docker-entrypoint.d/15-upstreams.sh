#!/bin/sh
# Genera default.conf y ajusta upstreams SIN envsubst.
# envsubst + $host / $$host rompe nginx en Railway (Crashed tras Online).
set -eu

LISTEN_PORT="${PORT:-${LISTEN_PORT:-80}}"
CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM:-http://chatbot-api:8000}"
TICKETS_UPSTREAM="${TICKETS_UPSTREAM:-http://ticket-service:8001}"

NS="${NGINX_RESOLVER:-}"
if [ -z "$NS" ]; then
  NS="$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null || true)"
  [ -n "$NS" ] || NS="127.0.0.11"
fi
case "$NS" in
  *:*) NS="[$NS]" ;;
esac

echo "[nginx] LISTEN_PORT=${LISTEN_PORT} PORT=${PORT:-unset} resolver=${NS}"
echo "[nginx] CHATBOT_UPSTREAM=${CHATBOT_UPSTREAM}"
echo "[nginx] TICKETS_UPSTREAM=${TICKETS_UPSTREAM}"

cat > /etc/nginx/conf.d/default.conf <<EOF
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    listen ${LISTEN_PORT};
    server_name _;
    include /etc/nginx/conf.d/_app.inc;
}
EOF

sed -i \
  -e "s|^resolver .*|resolver ${NS} valid=10s ipv6=off;|" \
  -e "s|^set \$upstream_chatbot .*|set \$upstream_chatbot ${CHATBOT_UPSTREAM};|" \
  -e "s|^set \$upstream_tickets .*|set \$upstream_tickets ${TICKETS_UPSTREAM};|" \
  /etc/nginx/conf.d/_app.inc

nginx -t
