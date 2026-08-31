# ticket-service

Servicio de gestión de incidencias (tickets) del chatbot CTIC-FIIS UNAC.
Semana 1: esqueleto, módulos core (envelope, errores, seguridad, DB), migraciones Alembic y seeds.

## Requisitos

- Python 3.12 (gestionado con [uv](https://docs.astral.sh/uv/))
- MySQL 8 solo para levantar el servicio; los tests unitarios **no** lo requieren.

## Tests y lint

```bash
cd services/ticket-service
uv sync
uv run pytest
uv run ruff check .
```

## Levantar en desarrollo

Con MySQL corriendo y la variable `DB_URL` apuntando a `tickets_db`
(default: `mysql+asyncmy://tickets:tickets@localhost:3306/tickets_db`):

```bash
# Migraciones + seeds (staff: SEED_ADMIN_PASSWORD / SEED_TECNICO_PASSWORD, default "cambiar123")
uv run alembic upgrade head

# Servidor
uv run uvicorn app.main:app --reload --port 8001
```

Salud: `GET http://localhost:8001/healthz` → `{"status":"ok","db":"ok"}`.

## Docker

```bash
docker build -t ticket-service .
```

El entrypoint aplica `alembic upgrade head` (con reintentos mientras MySQL
arranca) y luego lanza uvicorn en el puerto 8001.

## Variables de entorno principales

| Variable | Default | Descripción |
|---|---|---|
| `DB_URL` | `mysql+asyncmy://tickets:tickets@localhost:3306/tickets_db` | Conexión a tickets_db |
| `JWT_SECRET` | `cambiar-64-chars-aleatorios` | Firma de JWT del panel (HS256, 8 h) |
| `TICKETS_API_KEY` | `cambiar` | Valida el header `X-Api-Key` de servicios |
| `UPLOADS_DIR` | `/data/uploads` | Carpeta de adjuntos |
| `SEED_ADMIN_PASSWORD` | `cambiar123` | Contraseña inicial del admin (seed) |
| `SEED_TECNICO_PASSWORD` | `cambiar123` | Contraseña inicial de los técnicos (seed) |
| `TZ` | `America/Lima` | Zona horaria |
