# Multi-stage build con uv (prd/07 §3: imagen final slim, usuario no-root, sin curl)

# --- Etapa de build: instala dependencias en un venv ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Herramientas de compilación solo en el builder (asyncmy se compila desde
# el sdist en plataformas sin wheel, p. ej. linux/arm64)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Solo runtime (sin grupo dev), reproducible con uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Etapa final ---
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PATH="/srv/.venv/bin:$PATH" \
    TZ=America/Lima

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/uploads \
    && chown -R app:app /data/uploads

WORKDIR /srv

COPY --from=builder /srv/.venv /srv/.venv
COPY --chown=app:app alembic.ini entrypoint.sh ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
RUN chmod +x entrypoint.sh

USER app
EXPOSE 8001

ENTRYPOINT ["./entrypoint.sh"]
