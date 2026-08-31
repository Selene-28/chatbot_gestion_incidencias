#!/usr/bin/env bash
# Monitoreo simple del chatbot CTIC-FIIS UNAC (prd/07 §6).
# Consulta /healthz y alerta por correo si el servicio no está sano.
# Pensado para un cron cada 5 minutos.
#
# Uso:  URL=https://chatbot.fiis.unac.edu.pe ALERTA=soporte-ctic@unac.edu.pe ./deploy/monitor.sh
set -euo pipefail

URL="${URL:-http://localhost}"
ALERTA="${ALERTA:-}"

respuesta="$(curl -sf --max-time 8 "${URL}/healthz" 2>/dev/null || echo '{"status":"down"}')"
estado="$(printf '%s' "${respuesta}" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')"
llm="$(printf '%s' "${respuesta}" | sed -n 's/.*"llm":"\([^"]*\)".*/\1/p')"

if [ "${estado}" != "ok" ]; then
  msg="[ALERTA] Chatbot CTIC no responde sano en ${URL}/healthz — estado='${estado:-desconocido}'"
  echo "${msg}" >&2
  if [ -n "${ALERTA}" ] && command -v mail >/dev/null 2>&1; then
    printf '%s\n\nRespuesta:\n%s\n' "${msg}" "${respuesta}" | mail -s "Chatbot CTIC caído" "${ALERTA}"
  fi
  exit 1
fi

# Aviso informativo (no crítico): el LLM está degradado o deshabilitado
if [ "${llm}" = "degraded" ] || [ "${llm}" = "disabled" ]; then
  echo "[aviso] servicio sano pero LLM='${llm}' (opera en modo degradado: recuperación semántica/textual)"
fi

echo "[monitor] OK — status=${estado} llm=${llm}"

# --- Ejemplo de cron (cada 5 min) ---------------------------------------------
#   */5 * * * *  cd /opt/chatbot-ctic && URL=https://chatbot.fiis.unac.edu.pe ALERTA=ctic@unac.edu.pe ./deploy/monitor.sh >> /var/log/chatbot-monitor.log 2>&1
