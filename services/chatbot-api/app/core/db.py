"""Acceso a base de datos: engine async de SQLAlchemy 2.x (driver asyncmy)."""

import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger("app.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Engine async creado de forma perezosa (permite tests sin BD)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().DB_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Fábrica de sesiones async ligada al engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: entrega una sesión y garantiza su cierre."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Libera el pool de conexiones (shutdown de la app o entre tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def check_db(timeout: float = 2.0) -> bool:
    """Verifica conectividad con la BD (SELECT 1) con timeout corto."""

    async def _ping() -> None:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_ping(), timeout=timeout)
        return True
    except Exception as exc:  # noqa: BLE001 — cualquier fallo implica BD no disponible
        logger.warning("Verificación de base de datos fallida: %s", exc)
        return False
