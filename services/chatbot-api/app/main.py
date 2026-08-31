"""Punto de entrada de la aplicación FastAPI (factory create_app)."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.handoff import router as handoff_router
from app.api.health import router as health_router
from app.api.kb import router as kb_router
from app.api.metricas import router as metricas_router
from app.api.stream import router as stream_router
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.services.sesiones import loop_cierre_inactividad

logger = logging.getLogger("app.main")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Ciclo de vida: loop de cierre por inactividad (RN-09) y pool al apagar."""
    logger.info("chatbot-api iniciado")
    tarea_inactividad = asyncio.create_task(loop_cierre_inactividad())
    yield
    tarea_inactividad.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tarea_inactividad
    await dispose_engine()
    logger.info("chatbot-api detenido")


def create_app() -> FastAPI:
    """Crea y configura la aplicación: logging, CORS, routers y handlers."""
    setup_logging()
    settings = get_settings()

    application = FastAPI(
        title="chatbot-api",
        description="API del chatbot de gestión de incidencias CTIC-FIIS UNAC",
        version="0.1.0",
        lifespan=_lifespan,
    )

    # CORS: solo los orígenes institucionales configurados (prd/04 §5)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(chat_router)
    application.include_router(handoff_router)
    application.include_router(stream_router)
    application.include_router(kb_router)
    application.include_router(metricas_router)

    return application


app = create_app()
