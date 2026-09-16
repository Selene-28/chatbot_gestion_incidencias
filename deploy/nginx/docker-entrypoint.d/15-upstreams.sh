#!/bin/sh
# Genera default.conf y ajusta upstreams SIN envsubst.
set -u

LISTEN_PORT="${PORT:-${LISTEN_PORT:-80}}"
CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM:-http://chatbot-api:8000}"
TICKETS_UPSTREAM="${TICKETS_UPSTREAM:-http://ticket-service:8001}"
CHATBOT_UPSTREAM="${CHATBOT_UPSTREAM%/}"
TICKETS_UPSTREAM="${TICKETS_UPSTREAM%/}"

if [ -n "${PORT:-}" ]; then
  case "$CHATBOT_UPSTREAM" in
    *railway.internal*|*up.railway.app*|https://*) ;;
    *) CHATBOT_UPSTREAM="http://chatbot-api.railway.internal:8000" ;;
  esac
  case "$TICKETS_UPSTREAM" in
    *railway.internal*|*up.railway.app*|https://*) ;;
    *) TICKETS_UPSTREAM="http://ticket-service.railway.internal:8001" ;;
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
  # wget/nginx prefieren el A IPv4 (10.x) que rechaza el puerto; la red privada es AAAA fd12:.
  RESOLVER_OPTS="valid=10s ipv4=off"
fi

echo "[nginx] LISTEN_PORT=${LISTEN_PORT} PORT=${PORT:-unset}"
echo "[nginx] resolver=${NS_LIST} ${RESOLVER_OPTS}"

# Convierte hostname a http://[ipv6]:puerto si wget /healthz responde.
pick_reachable() {
  _name="$1"
  _default_url="$2"
  _ip="$(getent hosts "$_name" 2>/dev/null | awk '/:/{print $1; exit}')"
  if [ -z "$_ip" ]; then
    echo "$_default_url"
    return
  fi
  _base="http://[${_ip}]"
  for _p in 8000 8001 8080 80; do
    if wget -T 2 -qO- "${_base}:${_p}/healthz" >/tmp/nginx-probe.out 2>/dev/null; then
      echo "${_base}:${_p}"
      return
    fi
  done
  echo "${_base}:8000"
}

if [ -n "${PORT:-}" ]; then
  case "$CHATBOT_UPSTREAM" in
    *up.railway.app*|https://*)
      echo "[nginx] usando URL pública; no se fuerza IPv6 interno"
      ;;
    *)
      CB_RESOLVED="$(pick_reachable chatbot-api.railway.internal "$CHATBOT_UPSTREAM")"
      TK_RESOLVED="$(pick_reachable ticket-service.railway.internal "$TICKETS_UPSTREAM")"
      echo "[nginx] pick chatbot=${CB_RESOLVED}"
      echo "[nginx] pick tickets=${TK_RESOLVED}"
      CHATBOT_UPSTREAM="$CB_RESOLVED"
      TICKETS_UPSTREAM="$TK_RESOLVED"
      ;;
  esac
fi

{
  echo "LISTEN_PORT=${LISTEN_PORT}"
  echo "resolver=${NS_LIST} ${RESOLVER_OPTS}"
  echo "CHATBOT_UPSTREAM=${CHATBOT_UPSTREAM}"
  echo "TICKETS_UPSTREAM=${TICKETS_UPSTREAM}"
  echo "--- resolv.conf ---"
  cat /etc/resolv.conf 2>/dev/null || true
  echo "--- getent ---"
  getent hosts chatbot-api.railway.internal 2>/dev/null || true
  getent hosts ticket-service.railway.internal 2>/dev/null || true
  echo "--- wget chatbot ipv6 :8000 ---"
  CB6="$(getent hosts chatbot-api.railway.internal 2>/dev/null | awk '/:/{print $1; exit}')"
  echo "ipv6=${CB6}"
  if [ -n "$CB6" ]; then
    wget -T 2 -S -O- "http://[${CB6}]:8000/healthz" 2>&1 | head -c 500 || true
    echo
    wget -T 2 -S -O- "http://[${CB6}]:8080/healthz" 2>&1 | head -c 300 || true
    echo
  fi
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

# El valor puede contener [] y : ; sed usa | como separador.
sed -i \
  -e "s|^resolver .*|resolver ${NS_LIST} ${RESOLVER_OPTS};|" \
  -e "s|^set \$upstream_chatbot .*|set \$upstream_chatbot ${CHATBOT_UPSTREAM};|" \
  -e "s|^set \$upstream_tickets .*|set \$upstream_tickets ${TICKETS_UPSTREAM};|" \
  /etc/nginx/conf.d/_app.inc

nginx -t
