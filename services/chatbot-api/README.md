# chatbot-api

Superficie conversacional del chatbot de gestión de incidencias CTIC-FIIS UNAC
(FastAPI + SQLAlchemy 2 async + MySQL 8). Semana 1: esqueleto, módulos core y
migraciones (`conversaciones`, `mensajes`, `kb_articulos`, `handoffs`, vistas de
métricas y seeds mínimos de KB).

## Requisitos

- [uv](https://docs.astral.sh/uv/) (gestiona Python 3.12 y las dependencias)
- MySQL 8 solo para correr el servicio con BD real (los tests no lo necesitan)

## Tests y lint

```bash
cd services/chatbot-api
uv sync              # crea .venv con deps de runtime + dev
uv run pytest        # tests unitarios (no requieren MySQL)
uv run ruff check .  # lint
uv run mypy app      # tipado (opcional)
```

## Levantar en desarrollo

```bash
# 1. (opcional) exportar variables; hay defaults sensatos para dev
export DB_URL="mysql+asyncmy://chatbot:chatbot@localhost:3306/chatbot_db"

# 2. aplicar migraciones (usa DB_URL convertido a pymysql)
uv run alembic upgrade head

# 3. levantar la API con recarga
uv run uvicorn app.main:app --reload --port 8000

# comprobar
curl http://localhost:8000/healthz
```

Variables de entorno disponibles (ver `app/core/config.py` y `prd/07` §3-4):
`DB_URL`, `TICKETS_API_BASE_URL`, `TICKETS_API_KEY`, `ANTHROPIC_API_KEY`,
`LLM_MODEL`, `LLM_MODEL_ROUTER`, `CHROMA_DIR`, `ALLOWED_ORIGINS`, `TZ`.

## Docker

```bash
docker build -t chatbot-api .
```

El `entrypoint.sh` ejecuta `alembic upgrade head` (con reintentos mientras
MySQL arranca) y luego `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
