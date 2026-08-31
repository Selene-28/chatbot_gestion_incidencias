"""Streaming SSE hacia el widget (tarea 5.1).

``GET /api/chat/stream?sessionId=...&token=...`` → ``text/event-stream``.

Autenticación por query param: EventSource no envía cabeceras, así que el token
opaco de sesión viaja en la URL y se valida contra ``session_token_hash``.

Eventos emitidos (ver app/services/eventos.py):
  - ``agente``   — {texto, fecha} cuando el humano del CTIC escribe (handoff).
  - ``estado``   — {estadoBot} en transiciones PAUSED↔ACTIVE.
  - ``encuesta`` — el MensajeBot de encuesta cuando, tras cerrar el handoff, toca.
  - ``: heartbeat`` — comentario SSE cada 20 s para mantener viva la conexión.

TODO(5.1 · RAG streaming): el POST /api/chat/mensajes sigue devolviendo el
mensaje completo (el widget funciona sin SSE y sin LLM). Cuando haya API key,
``llm.generar_stream`` alimentaría aquí eventos ``token`` (fragmentos) y ``fin``
(mensaje completo + meta); no es necesario que el POST haga streaming ahora.

TODO(producción): el pub/sub es en memoria (single-worker). Multi-worker
requeriría Redis pub/sub — ver app/services/eventos.py.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.services import eventos, sesiones

logger = logging.getLogger("app.api.stream")

router = APIRouter(prefix="/api/chat", tags=["stream"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

HEARTBEAT_S = 20.0

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # desactiva el buffering de nginx para SSE
}


async def _event_stream(session_id: str) -> AsyncIterator[str]:
    """Generador SSE: entrega los eventos de la cola + heartbeats periódicos."""
    cola = eventos.suscribir(session_id)
    try:
        yield ": conectado\n\n"
        while True:
            try:
                mensaje = await asyncio.wait_for(cola.get(), timeout=HEARTBEAT_S)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            data = json.dumps(mensaje["data"], ensure_ascii=False)
            yield f"event: {mensaje['event']}\ndata: {data}\n\n"
    finally:
        # Limpieza al desconectar el cliente (StreamingResponse cierra el generador).
        eventos.desuscribir(session_id, cola)


@router.get("/stream")
async def stream(sessionId: str, token: str, session: SessionDep) -> StreamingResponse:  # noqa: N803
    """Abre el canal SSE del widget tras validar el token de la sesión."""
    conv = await sesiones.autenticar_stream(session, sessionId, token)
    return StreamingResponse(
        _event_stream(conv.codigo),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


__all__ = ["router"]
