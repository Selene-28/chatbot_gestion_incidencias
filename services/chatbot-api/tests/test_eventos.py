"""Unit: pub/sub en memoria del streaming SSE (app/services/eventos.py)."""

import asyncio

import pytest

from app.services import eventos


@pytest.fixture(autouse=True)
def _limpiar_registro():
    eventos.reset()
    yield
    eventos.reset()


async def test_publicar_llega_al_suscriptor():
    cola = eventos.suscribir("sess-1")
    await eventos.publicar_agente("sess-1", "Hola, soy Carlos del CTIC", "2026-07-04T10:00:00")
    mensaje = await asyncio.wait_for(cola.get(), timeout=1)
    assert mensaje["event"] == "agente"
    assert mensaje["data"] == {"texto": "Hola, soy Carlos del CTIC", "fecha": "2026-07-04T10:00:00"}


async def test_estado_y_encuesta():
    cola = eventos.suscribir("sess-2")
    await eventos.publicar_estado("sess-2", "ACTIVE")
    await eventos.publicar_encuesta("sess-2", {"tipo": "encuesta", "texto": "califica"})
    e1 = await asyncio.wait_for(cola.get(), timeout=1)
    e2 = await asyncio.wait_for(cola.get(), timeout=1)
    assert e1 == {"event": "estado", "data": {"estadoBot": "ACTIVE"}}
    assert e2["event"] == "encuesta" and e2["data"]["tipo"] == "encuesta"


async def test_varias_conexiones_del_mismo_session_reciben():
    a = eventos.suscribir("sess-3")
    b = eventos.suscribir("sess-3")
    await eventos.publicar_estado("sess-3", "PAUSED")
    assert (await asyncio.wait_for(a.get(), timeout=1))["data"]["estadoBot"] == "PAUSED"
    assert (await asyncio.wait_for(b.get(), timeout=1))["data"]["estadoBot"] == "PAUSED"


async def test_publicar_sin_suscriptores_no_falla():
    await eventos.publicar_estado("nadie", "ACTIVE")  # no debe lanzar


async def test_desuscribir_limpia_el_registro():
    cola = eventos.suscribir("sess-4")
    assert eventos.hay_suscriptores("sess-4") is True
    eventos.desuscribir("sess-4", cola)
    assert eventos.hay_suscriptores("sess-4") is False
