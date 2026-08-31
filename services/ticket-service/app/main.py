"""Punto de entrada del servicio: fábrica de aplicación FastAPI."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, encuestas, health, incidencias, metricas
from app.api import panel as panel_api
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.panel import router as panel_html_router
from app.services.adjuntos import loop_purga


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Arranca la purga periódica de adjuntos huérfanos (RF-13) y la detiene al apagar."""
    tarea_purga = asyncio.create_task(loop_purga())
    try:
        yield
    finally:
        tarea_purga.cancel()


def create_app() -> FastAPI:
    """Crea y configura la aplicación (logging, routers y handlers de errores)."""
    setup_logging()

    app = FastAPI(
        title="ticket-service",
        description="Servicio de gestión de incidencias — CTIC FIIS UNAC",
        version="0.2.0",
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(incidencias.router)   # API-01/01b/02/03 (X-Api-Key)
    app.include_router(encuestas.router)     # API-06 (X-Api-Key)
    app.include_router(metricas.router)      # /api/metricas/tickets (X-Api-Key, RF-14)
    app.include_router(auth.router)          # /api/auth/* (staff)
    app.include_router(panel_api.router)     # /api/panel/* (JWT staff)
    app.include_router(panel_html_router)    # /panel/* (UI Jinja2 + htmx)

    return app


app = create_app()
