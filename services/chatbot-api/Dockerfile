# Imagen del servicio chatbot-api (multi-stage, ver prd/07 §3)
#
# Notas del stack RAG (Semana 4, prd/06 §5 y prd/07):
# - torch se instala CPU-only vía el índice por-paquete de uv (pyproject:
#   [tool.uv.sources] torch → https://download.pytorch.org/whl/cpu), lo que
#   evita las ruedas CUDA (~2 GB) y mantiene la imagen en un tamaño razonable.
# - El modelo de embeddings intfloat/multilingual-e5-small (~120 MB) se
#   pre-descarga en el build y su caché HF se copia a la imagen final, de modo
#   que el contenedor arranca SIN internet (solo la API de Claude es saliente).

# --- Stage 1: builder — instala dependencias con uv en un venv aislado -------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7.7 /uv /usr/local/bin/uv

ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Herramientas de compilación solo en el builder (asyncmy puede requerirlas)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml uv.lock ./

# Solo dependencias de runtime, reproducibles desde el lock
RUN uv sync --frozen --no-dev --no-install-project

# Pre-descarga del modelo de embeddings a una caché HF propia del build
# (prd/06 §5: E5 small). La caché completa se copia luego a la imagen final.
ENV HF_HOME=/opt/hf-cache
RUN /opt/venv/bin/python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('intfloat/multilingual-e5-small')"

# --- Stage 2: runtime — imagen mínima, usuario no-root, sin curl -------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=America/Lima \
    # caché HF pre-poblada en el build: el arranque no necesita internet
    HF_HOME=/opt/hf-cache

RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/chroma \
    && chown -R app:app /data

WORKDIR /srv/app

COPY --from=builder /opt/venv /opt/venv
# caché del modelo de embeddings con el usuario correcto (lectura en runtime)
COPY --from=builder --chown=app:app /opt/hf-cache /opt/hf-cache
COPY --chown=app:app alembic.ini entrypoint.sh ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app

RUN chmod +x entrypoint.sh

USER app
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
