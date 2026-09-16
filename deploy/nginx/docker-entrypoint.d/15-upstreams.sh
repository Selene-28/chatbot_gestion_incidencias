#!/bin/sh
# Genera default.conf y ajusta upstreams SIN envsubst.
# envsubst + $host / $$host rompe nginx en Railway (Crashed tras Online).
set -eu

LISTEN_PORT="${PORT:-${LISTEN_PORT:-80}}"
CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM:-http://chatbot-api:8000}"
TICKETS_UPSTREAM="${TICKETS_UPSTREAM:-http://ticket-service:8001}"

# En Railway $PORT está definido: usar DNS privado aunque falten variables.
if [ -n "${PORT:-}" ]; then
  case "$CHATBOT_UPSTREAM" in
    *railway.internal*) ;;
    *) CHATBOT_UPSTREAM="http://chatbot-api.railway.internal:8000" ;;
  esac
  case "$TICKETS_UPSTREAM" in
    *railway.internal*) ;;
    *) TICKETS_UPSTREAM="http://ticket-service.railway.internal:8001" ;;
  esac
fi

NS_LIST=""
HAS_DOCKER_DNS=0
while read -r _ ip _; do
  [ -n "${ip:-}" ] || continue
  if [ "$ip" = "127.0.0.11" ]; then
    HAS_DOCKER_DNS=1
  fi
  case "$ip" in
    *:*) ip="[$ip]" ;;
  esac
  NS_LIST="${NS_LIST} ${ip}"
done <<EOF
$(awk '/^nameserver/{print $1, $2}' /etc/resolv.conf 2>/dev/null || true)
EOF
NS_LIST="$(printf '%s' "$NS_LIST" | sed 's/^ *//')"
[ -n "$NS_LIST" ] || NS_LIST="127.0.0.11"

RESOLVER_OPTS="valid=10s"
if [ "$HAS_DOCKER_DNS" = "1" ] && [ -z "${PORT:-}" ]; then
  RESOLVER_OPTS="valid=10s ipv6=off"
fi

echo "[nginx] LISTEN_PORT=${LISTEN_PORT} PORT=${PORT:-unset}"
echo "[nginx] resolv.conf:"
sed -n '1,20p' /etc/resolv.conf 2>/dev/null || true
echo "[nginx] resolver=${NS_LIST} ${RESOLVER_OPTS}"
echo "[nginx] CHATBOT_UPSTREAM=${CHATBOT_UPSTREAM}"
echo "[nginx] TICKETS_UPSTREAM=${TICKETS_UPSTREAM}"

cat > /etc/nginx/conf.d/default.conf <<EOF
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;

port_in_redirect off;
absolute_redirect off;

server {
    listen ${LISTEN_PORT};
    server_name _;
    include /etc/nginx/conf.d/_app.inc;
}
EOF

sed -i \
  -e "s|^resolver .*|resolver ${NS_LIST} ${RESOLVER_OPTS};|" \
  -e "s|^set \$upstream_chatbot .*|set \$upstream_chatbot ${CHATBOT_UPSTREAM};|" \
  -e "s|^set \$upstream_tickets .*|set \$upstream_tickets ${TICKETS_UPSTREAM};|" \
  /etc/nginx/conf.d/_app.inc

nginx -t
