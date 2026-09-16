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

probe_host() {
  _url="$1"
  _host="$(printf '%s' "$_url" | sed -e 's|^https://||' -e 's|^http://||' -e 's|/.*||' -e 's|:.*||')"
  echo "[nginx] getent ${_host}:"
  getent hosts "$_host" 2>/dev/null || echo "(sin getent)"
  if command -v wget >/dev/null 2>&1; then
    echo "[nginx] wget ${_url}/healthz:"
    wget -T 3 -qO- "${_url}/healthz" 2>&1 | head -c 200 || echo "(wget falló)"
    echo
  fi
}

probe_host "$CHATBOT_UPSTREAM"
probe_host "$TICKETS_UPSTREAM"

{
  echo "LISTEN_PORT=${LISTEN_PORT}"
  echo "resolver=${NS_LIST} ${RESOLVER_OPTS}"
  echo "CHATBOT_UPSTREAM=${CHATBOT_UPSTREAM}"
  echo "TICKETS_UPSTREAM=${TICKETS_UPSTREAM}"
  echo "--- resolv.conf ---"
  cat /etc/resolv.conf 2>/dev/null || true
  echo "--- getent chatbot-api.railway.internal ---"
  getent hosts chatbot-api.railway.internal 2>/dev/null || true
  echo "--- getent ticket-service.railway.internal ---"
  getent hosts ticket-service.railway.internal 2>/dev/null || true
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
