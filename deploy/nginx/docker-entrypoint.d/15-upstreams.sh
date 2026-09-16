#!/bin/sh
# Genera default.conf y ajusta upstreams SIN envsubst.
# En Railway no uses la IP de getent: el mesh privado solo enruta el hostname.
set -u

LISTEN_PORT="${PORT:-${LISTEN_PORT:-80}}"
CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM:-http://chatbot-api:8000}"
TICKETS_UPSTREAM="${TICKETS_UPSTREAM:-http://ticket-service:8001}"
CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM%/}"
TICKETS_UPSTREAM="${TICKETS_UPSTREAM%/}"

if [ -n "${PORT:-}" ]; then
  case "$CHATBOT_UPSTREAM" in
    *up.railway.app*|https://*) ;;
    *)
      CHATBOT_UPSTREAM="http://chatbot-api.railway.internal:${CHATBOT_PRIVATE_PORT:-8080}"
      ;;
  esac
  case "$TICKETS_UPSTREAM" in
    *up.railway.app*|https://*) ;;
    *)
      TICKETS_UPSTREAM="http://ticket-service.railway.internal:${TICKETS_PRIVATE_PORT:-8080}"
      ;;
  esac
  CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM%/}"
  TICKETS_UPSTREAM="${TICKETS_UPSTREAM%/}"
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
elif [ -n "${PORT:-}" ]; then
  RESOLVER_OPTS="valid=10s ipv4=off"
fi

echo "[nginx] LISTEN_PORT=${LISTEN_PORT} PORT=${PORT:-unset}"
echo "[nginx] resolver=${NS_LIST} ${RESOLVER_OPTS}"
echo "[nginx] CHATBOT_UPSTREAM=${CHATBOT_UPSTREAM}"
echo "[nginx] TICKETS_UPSTREAM=${TICKETS_UPSTREAM}"

{
  echo "LISTEN_PORT=${LISTEN_PORT}"
  echo "resolver=${NS_LIST} ${RESOLVER_OPTS}"
  echo "CHATBOT_UPSTREAM=${CHATBOT_UPSTREAM}"
  echo "TICKETS_UPSTREAM=${TICKETS_UPSTREAM}"
  echo "--- resolv.conf ---"
  cat /etc/resolv.conf 2>/dev/null || true
} > /usr/share/nginx/html/widget/upstreams.txt

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
