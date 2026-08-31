"""Fixtures compartidas.

- Unitarias: entorno determinista sin MySQL (puerto 6033 apunta a nada).
- Integración (marker `integration`): MySQL local en 3306; se crea una BD
  `tickets_test` desde cero, se migra con Alembic y se dropea al final.
  Si MySQL no responde, las pruebas de integración se autoskipean.
"""

import os
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import quote_plus

import pytest
from fastapi.testclient import TestClient

# Entorno determinista ANTES de importar la app (get_settings usa lru_cache).
# El puerto 6033 apunta a nada: garantiza que check_db falle rápido sin MySQL.
os.environ.setdefault("DB_URL", "mysql+asyncmy://tickets:tickets@127.0.0.1:6033/tickets_db")
os.environ.setdefault("JWT_SECRET", "secreto-de-pruebas-suficientemente-largo-para-hs256")
os.environ.setdefault("TICKETS_API_KEY", "clave-de-pruebas")
os.environ.setdefault("UPLOADS_DIR", tempfile.mkdtemp(prefix="uploads-pruebas-"))

from app.main import create_app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """Cliente HTTP de pruebas contra una app recién creada."""
    return TestClient(create_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Integración (MySQL real)
# ---------------------------------------------------------------------------

SERVICIO_DIR = Path(__file__).resolve().parents[1]
RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
MYSQL_HOST = os.environ.get("MYSQL_TEST_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_TEST_PORT", "3306"))
DB_PRUEBAS = "tickets_test"


def _root_password() -> str:
    """Lee DB_ROOT_PASSWORD del .env de la raíz del proyecto."""
    env_file = RAIZ_PROYECTO / ".env"
    if env_file.exists():
        for linea in env_file.read_text().splitlines():
            if linea.startswith("DB_ROOT_PASSWORD="):
                return linea.split("=", 1)[1].strip()
    return "cambiar"


def _conexion_root():  # type: ignore[no-untyped-def]
    import pymysql

    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user="root",
        password=_root_password(),
        connect_timeout=3,
        autocommit=True,
    )


@pytest.fixture(scope="session")
def db_pruebas_url() -> Iterator[str]:
    """Crea la BD tickets_test, la migra con Alembic y la dropea al final."""
    try:
        conexion = _conexion_root()
    except Exception:
        pytest.skip("MySQL no disponible en localhost:3306; se omiten pruebas de integración")

    with conexion.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS {DB_PRUEBAS}")
        cursor.execute(
            f"CREATE DATABASE {DB_PRUEBAS} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    conexion.close()

    url = (
        f"mysql+asyncmy://root:{quote_plus(_root_password())}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{DB_PRUEBAS}"
    )
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICIO_DIR,
        env={**os.environ, "DB_URL": url},
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, (
        f"alembic upgrade head falló:\n{resultado.stdout}\n{resultado.stderr}"
    )

    yield url

    conexion = _conexion_root()
    with conexion.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS {DB_PRUEBAS}")
    conexion.close()


@pytest.fixture()
async def fabrica_sesiones(db_pruebas_url: str):  # type: ignore[no-untyped-def]
    """Sessionmaker async contra tickets_test (una conexión por sesión, sin pool)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(db_pruebas_url, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
async def sesion(fabrica_sesiones):  # type: ignore[no-untyped-def]
    """Sesión async individual contra tickets_test."""
    async with fabrica_sesiones() as sesion_db:
        yield sesion_db


@pytest.fixture()
async def api_client(fabrica_sesiones) -> AsyncIterator:  # type: ignore[no-untyped-def]
    """Cliente HTTP async contra una app de prueba que monta los routers del dominio."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api import routers
    from app.core.db import get_session
    from app.core.errors import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    for router in routers:
        app.include_router(router)

    async def _sesion_de_pruebas():  # type: ignore[no-untyped-def]
        async with fabrica_sesiones() as sesion_db:
            yield sesion_db

    app.dependency_overrides[get_session] = _sesion_de_pruebas

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Api-Key": os.environ["TICKETS_API_KEY"]},
    ) as cliente:
        yield cliente
