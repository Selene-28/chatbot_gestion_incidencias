#!/usr/bin/env bash
# Verifica que el entorno tenga lo necesario para levantar el stack con
# `docker compose up -d --build` y avisa de forma clara si falta algo.
#
# Uso: ./scripts/verificar_requisitos.sh

set -uo pipefail
cd "$(dirname "$0")/.."

fallo=0

echo "== Verificando requisitos para levantar el stack =="

# --- Docker ---
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker no está instalado o no está en el PATH."
  echo "   Instálalo desde https://www.docker.com/products/docker-desktop/"
  fallo=1
else
  if docker info >/dev/null 2>&1; then
    echo "✅ Docker está instalado y el daemon está corriendo."
  else
    echo "❌ Docker está instalado pero el daemon no responde (¿Docker Desktop abierto?)."
    fallo=1
  fi
fi

# --- Docker Compose (plugin v2) ---
if docker compose version >/dev/null 2>&1; then
  echo "✅ Docker Compose (plugin) disponible: $(docker compose version --short 2>/dev/null)"
else
  echo "❌ 'docker compose' no está disponible (necesitas el plugin Compose v2)."
  fallo=1
fi

# --- .env ---
if [ -f .env ]; then
  echo "✅ .env encontrado."
  if grep -q "REEMPLAZAR_CON_TU_API_KEY_DE_ANTHROPIC" .env 2>/dev/null; then
    echo "⚠️  ANTHROPIC_API_KEY en .env sigue con el valor de ejemplo."
    echo "    El sistema arrancará en modo degradado (sin LLM) hasta que la reemplaces."
  fi
else
  echo "❌ No existe .env en la raíz del proyecto. Copia .env.example y complétalo:"
  echo "   cp .env.example .env"
  fallo=1
fi

# --- Puertos usados por el stack en dev (docker-compose.override.yml) ---
for puerto in 80 8000 8001 3306 8080; do
  if command -v lsof >/dev/null 2>&1 && lsof -i ":$puerto" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "⚠️  El puerto $puerto ya está en uso — puede chocar con el stack (nginx/chatbot-api/ticket-service/mysql/adminer)."
  fi
done

echo ""
if [ "$fallo" -eq 0 ]; then
  echo "Todo listo. Puedes levantar el stack con:"
  echo "  docker compose up -d --build"
else
  echo "Hay requisitos pendientes (ver ❌ arriba). Resuélvelos antes de levantar el stack."
fi

exit "$fallo"
