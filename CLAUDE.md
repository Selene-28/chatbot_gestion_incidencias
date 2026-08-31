# CLAUDE.md — Guía del proyecto para agentes de IA

Chatbot de gestión de incidencias para el CTIC de la FIIS-UNAC (proyecto de tesis).
Implementación **completa** de las 6 semanas del plan. Los PRD en `prd/` son la
**fuente de verdad viva**: si la implementación se desvía, el PRD se actualiza en
el mismo cambio. Los criterios QA-01…QA-11 (`prd/01` §6) son la Definición de
Terminado; la suite `e2e/` los verifica y es el **gate de release** (también en CI).

## Comandos esenciales

```bash
# Stack completo (dev: hot-reload + puertos 8000/8001/3306/8080 publicados + Adminer)
docker compose up -d --build
# Producción (sin override de dev; TLS con certs en deploy/certs + tls.conf):
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Cargar/reindexar la base de conocimiento (dentro del contenedor)
docker compose exec -T chatbot-api python -m app.scripts.cargar_kb
docker compose exec -T chatbot-api python -m app.scripts.reindex

# Tests por servicio (cada servicio es un proyecto uv independiente)
cd services/chatbot-api  && uv run pytest -m "not llm"     # todo salvo LLM real
cd services/ticket-service && uv run pytest
# Markers de chatbot-api: integration (MySQL local), rag (modelo E5 real),
# llm (API key real), e2e (ticket-service vivo). Autoskip si falta el requisito.

# Suite E2E QA-01..QA-11 (requiere el stack arriba y la KB cargada)
cd e2e && uv run pytest -q

# Lint / tipos (en cada services/*, e2e/, evidencia/)
uv run ruff check .  &&  uv run mypy app

# Migraciones (por servicio; corren solas en el entrypoint del contenedor)
cd services/<svc> && uv run alembic revision -m "..." && uv run alembic upgrade head

# Evidencia de tesis (evidencia/): carga Locust, precisión router, recall RAG, KPIs CSV
```

## Arquitectura (detalle en prd/02)

- **nginx** (:80, único puerto público) enruta: `/api/chat|faq|kb|metricas` → **chatbot-api**
  (:8000); `/api/incidencias|encuesta|auth|panel` y `/panel` → **ticket-service** (:8001);
  `/widget/` y `/demo.html` → estáticos. Rutas compartidas :80/:443 en `deploy/nginx/conf.d/_app.inc`.
- **chatbot-api** (FastAPI): diálogo (máquinas de estado en BD → sobrevive reinicios),
  router de intenciones 2 capas (reglas → LLM), RAG (Chroma embebido + e5-small local),
  handoff + SSE, métricas. Esquema `chatbot_db`.
- **ticket-service** (FastAPI): contratos API-01..03/06 del DRS (simula el sistema real,
  ADR-03), panel Jinja2+htmx, auth staff (Argon2 + JWT cookie `panel_token`). Esquema `tickets_db`.
- **Regla ADR-03**: chatbot-api NUNCA lee `tickets_db` directo; todo por HTTP
  (`TICKETS_API_BASE_URL` — en producción apuntará al sistema real de la universidad).
  Única excepción documentada: la vista SQL `v_autoservicio_diario`.
- El JWT del staff lo emite ticket-service y chatbot-api lo valida con el mismo
  `JWT_SECRET` (cookie same-origin vía nginx).

## Convenciones

- **Español** para dominio, mensajes de usuario, comentarios y tests; inglés para infraestructura.
- Respuestas HTTP siempre con el envelope de `prd/04` §2 (`ok()`/`fail()` en `app/core/envelope.py`);
  errores vía jerarquía `AppError` (`app/core/errors.py`). El SSE es la excepción.
- Los textos oficiales del DRS viven en `app/dialogo/textos.py` — no reescribirlos.
- Validaciones de entrada con Pydantic (`prd/01` §4); escala de encuesta **1–5**.
- Cada componente (`services/*`, `e2e/`, `evidencia/`) es un proyecto **uv** aislado con su
  propio `pyproject.toml`; ruff line-length 100, target py312.

## Gotchas (aprendidos durante el desarrollo — evitan horas de debugging)

- **Dependencias nuevas de Python requieren rebuild de imagen**: el venv va horneado.
  `uv add X` + `docker compose build <svc>` + `up -d --force-recreate <svc>`.
- **Hot-reload en macOS a veces no dispara** (eventos FS no cruzan el bind-mount):
  si un cambio no se refleja, `docker compose restart <svc>`.
- El override de dev monta el código del host en el WORKDIR real de cada imagen
  (chatbot-api: `/srv/app/app`; ticket-service: `/srv/app`) — no cambiar esas rutas.
- **torch debe quedarse CPU-only** (índice `pytorch-cpu` fijado en el pyproject de
  chatbot-api). Si el lock resuelve la rueda CUDA, la imagen pasa de 2.6 GB a 9.4 GB.
- **Sin `ANTHROPIC_API_KEY` real** el sistema opera en modo degradado *correcto*:
  router solo Capa 1 (reglas) y FAQ por recuperación semántica textual. `/healthz`
  reporta `llm: disabled|degraded|configured`.
- `RAG_UMBRAL_SIMILITUD=0.83` está **calibrado para e5-small** (relevantes ≈0.88–0.92,
  irrelevantes ≈0.75–0.82). Si se cambia el modelo de embeddings, recalibrar midiendo
  ambos grupos (hay verificación en `e2e/test_qa03_faq.py`).
- **nginx limita 10 r/s por IP** en `/api/` — las pruebas de carga desde localhost
  (una sola IP) ven 503 del rate-limiter, no de la app; medir capacidad directo a :8000.
- El pub/sub del SSE es **en memoria → single-worker**; multi-worker requiere Redis
  (TODO documentado en `app/services/eventos.py`).
- El DDL de MySQL **no es transaccional**: los entrypoints esperan la conexión y migran
  UNA vez (un error real de SQL debe abortar, nunca reintentar la migración en bucle).
- Los tests de integración crean BDs `*_test` contra el MySQL local (root/`cambiar` del
  `.env`) y hacen autoskip si no hay MySQL. Credenciales seed del panel: `admin@ctic.local`
  y `tecnico1@ctic.local` con `SEED_*_PASSWORD` del `.env` (dev: `cambiar`).
- En los tests E2E/carga, **nunca** tomar `items[0]` de colas: filtrar por el
  sessionId/código creado por el propio test (los datos se acumulan entre corridas).

## Estructura

```
prd/          Especificación (fuente de verdad) · manuales/  Docs operativas
services/chatbot-api/    diálogo, IA/RAG, handoff+SSE, métricas (chatbot_db)
services/ticket-service/ tickets DRS, panel, auth staff (tickets_db)
widget/public/           widget embebible vanilla JS/CSS + demo.html
e2e/          Suite QA-01..QA-11 (gate) · evidencia/  carga + evaluadores de tesis
deploy/       nginx, TLS, backup/restore/monitor · db/init/  bootstrap MySQL
```
