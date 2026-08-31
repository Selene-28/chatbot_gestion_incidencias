"""Fixtures compartidas: app y TestClient con settings de test (sin BD real)."""

import asyncio
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import (
    ConflictError,
    NotFoundError,
)

# Settings de test: BD apuntando a un puerto local cerrado (falla rápido,
# sin depender de un MySQL en la máquina) y sin API key de LLM.
_TEST_ENV = {
    "DB_URL": "mysql+asyncmy://test:test@127.0.0.1:65531/chatbot_db",
    "ANTHROPIC_API_KEY": "",
    "ALLOWED_ORIGINS": "http://testserver",
}


@pytest.fixture(scope="session", autouse=True)
def test_settings():
    """Fija variables de entorno de test antes de construir la app."""
    previous = {key: os.environ.get(key) for key in _TEST_ENV}
    os.environ.update(_TEST_ENV)
    get_settings.cache_clear()
    yield get_settings()
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()
    asyncio.run(dispose_engine())


class _EjemploBody(BaseModel):
    """Cuerpo de ejemplo para provocar errores de validación de Pydantic."""

    correo: str
    calificacion: int


def _agregar_rutas_de_prueba(application: FastAPI) -> None:
    """Rutas auxiliares solo para ejercitar los exception handlers."""

    @application.get("/_test/not-found")
    async def _not_found() -> None:
        raise NotFoundError("La incidencia no fue encontrada.")

    @application.get("/_test/conflict")
    async def _conflict() -> None:
        raise ConflictError()

    @application.post("/_test/validacion")
    async def _validacion(body: _EjemploBody) -> dict[str, str]:
        return {"ok": "sí"}

    @application.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("detalle interno que no debe filtrarse")


@pytest.fixture(scope="session")
def app(test_settings) -> FastAPI:
    """Aplicación FastAPI construida con la factory y rutas de prueba."""
    from app.main import create_app

    application = create_app()
    _agregar_rutas_de_prueba(application)
    return application


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    """TestClient que delega las excepciones a los handlers (no las relanza)."""
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Integración (MySQL real, marker `integration`) — mismo esquema que
# services/ticket-service/tests/conftest.py: se crea chatbot_test, se migra
# con Alembic y se dropea al final. Autoskip si MySQL no responde.
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402
import sys  # noqa: E402
from collections.abc import AsyncIterator, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402
from urllib.parse import quote_plus  # noqa: E402

SERVICIO_DIR = Path(__file__).resolve().parents[1]
RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
MYSQL_HOST = os.environ.get("MYSQL_TEST_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_TEST_PORT", "3306"))
DB_PRUEBAS = "chatbot_test"


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
    """Crea la BD chatbot_test, la migra con Alembic y la dropea al final."""
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
    """Sessionmaker async contra chatbot_test (sin pool)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(db_pruebas_url, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
async def sesion(fabrica_sesiones):  # type: ignore[no-untyped-def]
    """Sesión async individual contra chatbot_test."""
    async with fabrica_sesiones() as sesion_db:
        yield sesion_db


@pytest.fixture()
def fake_tickets(monkeypatch):  # type: ignore[no-untyped-def]
    """Cliente de tickets falso inyectado en la capa API (monkeypatch)."""
    from tests.fakes import FakeTicketsClient

    falso = FakeTicketsClient()
    monkeypatch.setattr("app.api.chat.get_tickets_client", lambda: falso)
    return falso


def _app_de_chat(fabrica_sesiones):  # type: ignore[no-untyped-def]
    """App liviana con los routers del chatbot (sin lifespan, con BD de pruebas)."""
    from app.api.chat import router as chat_router
    from app.api.handoff import router as handoff_router
    from app.api.kb import router as kb_router
    from app.api.metricas import router as metricas_router
    from app.api.stream import router as stream_router
    from app.core.db import get_session
    from app.core.errors import register_exception_handlers

    aplicacion = FastAPI()
    register_exception_handlers(aplicacion)
    for enrutador in (chat_router, handoff_router, stream_router, kb_router, metricas_router):
        aplicacion.include_router(enrutador)

    async def _sesion_de_pruebas():  # type: ignore[no-untyped-def]
        async with fabrica_sesiones() as sesion_db:
            yield sesion_db

    aplicacion.dependency_overrides[get_session] = _sesion_de_pruebas
    return aplicacion


def token_staff(rol: str = "tecnico", sub: int = 1) -> str:
    """JWT HS256 del staff (mismo formato que emite ticket-service) para tests."""
    import jwt

    return jwt.encode(
        {"sub": str(sub), "rol": rol}, get_settings().JWT_SECRET, algorithm="HS256"
    )


@pytest.fixture()
def cookies_tecnico() -> dict[str, str]:
    """Cookie de sesión del panel con rol tecnico."""
    return {"panel_token": token_staff("tecnico", sub=2)}


@pytest.fixture()
def cookies_admin() -> dict[str, str]:
    """Cookie de sesión del panel con rol admin."""
    return {"panel_token": token_staff("admin", sub=1)}


@pytest.fixture()
async def api_client(fabrica_sesiones) -> AsyncIterator:  # type: ignore[no-untyped-def]
    """Cliente HTTP async contra la app de chat sobre chatbot_test."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=_app_de_chat(fabrica_sesiones)),
        base_url="http://testserver",
    ) as cliente:
        yield cliente


@pytest.fixture()
def nueva_instancia_api(fabrica_sesiones):  # type: ignore[no-untyped-def]
    """Fábrica de clientes API 'reiniciados' (nueva app sobre la MISMA BD)."""
    from httpx import ASGITransport, AsyncClient

    def _crear() -> AsyncClient:
        return AsyncClient(
            transport=ASGITransport(app=_app_de_chat(fabrica_sesiones)),
            base_url="http://testserver",
        )

    return _crear


# ---------------------------------------------------------------------------
# Stack RAG (Semana 4): Chroma en directorio temporal + embedder inyectable.
# ---------------------------------------------------------------------------


@pytest.fixture()
def chroma_tmp(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Colección Chroma aislada en tmp_path (y restaura el estado al salir)."""
    from app.ia import indexado

    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    get_settings.cache_clear()
    indexado.reset_chroma()
    yield indexado
    indexado.reset_chroma()
    get_settings.cache_clear()


@pytest.fixture()
def fake_embedder(monkeypatch):  # type: ignore[no-untyped-def]
    """Inyecta el embedder determinista (sin sentence-transformers/torch).

    El FakeEmbedder usa vectores bag-of-words, cuya escala de similitud coseno
    difiere del modelo real e5-small (para el que se calibró RAG_UMBRAL_SIMILITUD
    = 0.83). Por eso, para estas pruebas de LÓGICA del pipeline, se rebaja el
    umbral: la calibración real se verifica en test_ia_rag_real.py y en la E2E.
    """
    from app.core.config import Settings
    from app.ia import embeddings, rag
    from tests.fakes import FakeEmbedder

    monkeypatch.setattr(rag, "get_settings", lambda: Settings(RAG_UMBRAL_SIMILITUD=0.1))
    embedder = FakeEmbedder()
    embeddings.set_embedder(embedder)
    yield embedder
    embeddings.set_embedder(None)
