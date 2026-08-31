"""Motor async de SQLAlchemy 2 (asyncmy) y utilidades de sesión."""

import asyncio
import logging
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DB_CHECK_TIMEOUT_S = 2.0


@lru_cache
def get_engine() -> AsyncEngine:
    """Crea (una sola vez) el engine async contra tickets_db."""
    return create_async_engine(get_settings().DB_URL, pool_pre_ping=True, pool_recycle=3600)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Fábrica de sesiones async ligada al engine."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: entrega una sesión y la cierra al terminar."""
    async with get_sessionmaker()() as session:
        yield session


async def check_db() -> bool:
    """Verifica conectividad con la base de datos (SELECT 1, timeout 2 s)."""

    async def _ping() -> None:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_ping(), timeout=DB_CHECK_TIMEOUT_S)
        return True
    except Exception:
        logger.warning("Base de datos no disponible en el chequeo de salud")
        return False
