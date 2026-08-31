"""Integración (MySQL): autenticación del endpoint SSE del widget (tarea 5.1).

El contenido del stream se valida a nivel de generador en tests/test_stream.py
(el transporte ASGI de httpx bufferiza y no puede consumir streams infinitos).
"""

import pytest

pytestmark = pytest.mark.integration


async def _crear_sesion(api_client) -> tuple[str, str]:
    r = await api_client.post("/api/chat/sesiones", json={"canal": "web_widget"})
    data = r.json()["data"]
    return data["sessionId"], data["sessionToken"]


async def test_stream_token_invalido_401(api_client):
    session_id, _token = await _crear_sesion(api_client)
    r = await api_client.get(f"/api/chat/stream?sessionId={session_id}&token=malo")
    assert r.status_code == 401


async def test_stream_sin_token_422(api_client):
    session_id, _token = await _crear_sesion(api_client)
    # falta el query param obligatorio `token` → 400 de validación
    r = await api_client.get(f"/api/chat/stream?sessionId={session_id}")
    assert r.status_code == 400
