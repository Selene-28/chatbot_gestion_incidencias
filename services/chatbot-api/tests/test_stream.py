"""Unit: generador SSE (app/api/stream) sobre el pub/sub en memoria.

El transporte ASGI de httpx bufferiza la respuesta completa, por lo que no puede
consumir un stream infinito en tests; se ejercita el generador directamente
(mismo código que uvicorn transmite en producción). La autenticación HTTP del
endpoint se cubre en tests/test_integracion_stream.py.
"""

import asyncio
import json

import pytest

from app.api import stream
from app.services import eventos


@pytest.fixture(autouse=True)
def _limpiar():
    eventos.reset()
    yield
    eventos.reset()


async def test_event_stream_entrega_evento_agente():
    gen = stream._event_stream("sess-x")
    try:
        conectado = await gen.__anext__()
        assert conectado.startswith(":")  # comentario SSE de conexión
        # el suscriptor ya está registrado: publicamos un mensaje del agente
        await eventos.publicar_agente("sess-x", "Hola, soy del CTIC", "2026-07-04T10:00:00")
        frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
        assert frame.startswith("event: agente\n")
        data_line = next(ln for ln in frame.splitlines() if ln.startswith("data:"))
        payload = json.loads(data_line[len("data:") :].strip())
        assert payload == {"texto": "Hola, soy del CTIC", "fecha": "2026-07-04T10:00:00"}
    finally:
        await gen.aclose()
    # al cerrar el generador se limpia la suscripción
    assert eventos.hay_suscriptores("sess-x") is False


async def test_event_stream_heartbeat(monkeypatch):
    monkeypatch.setattr(stream, "HEARTBEAT_S", 0.05)
    gen = stream._event_stream("sess-hb")
    try:
        await gen.__anext__()  # ": conectado"
        frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
        assert frame.strip() == ": heartbeat"
    finally:
        await gen.aclose()


async def test_event_stream_estado_y_encuesta():
    gen = stream._event_stream("sess-y")
    try:
        await gen.__anext__()
        await eventos.publicar_estado("sess-y", "ACTIVE")
        frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
        assert frame.startswith("event: estado\n")
        assert '"estadoBot": "ACTIVE"' in frame
    finally:
        await gen.aclose()
