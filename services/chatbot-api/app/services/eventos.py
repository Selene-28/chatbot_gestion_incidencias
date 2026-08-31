"""Pub/sub en memoria por sessionId para el streaming SSE del widget (tarea 5.1).

Cada conexión SSE registra una ``asyncio.Queue``; los endpoints de handoff
publican eventos (``agente``, ``estado``, ``encuesta``) que se entregan a todas
las colas suscritas a ese sessionId. El heartbeat lo emite el propio generador
del stream.

TODO(producción): este registro vive en el proceso. Con varios workers de
uvicorn un evento publicado en un worker no llegaría a las conexiones de otro;
para multi-worker habría que sustituirlo por un bus externo (Redis pub/sub).
Para el MVP el servicio corre single-worker (ver prd/07 / entrypoint).
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("app.services.eventos")

# sessionId -> conjunto de colas activas (una por conexión SSE)
_suscriptores: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}


def suscribir(session_id: str) -> "asyncio.Queue[dict[str, Any]]":
    """Registra una nueva conexión SSE y devuelve su cola de eventos."""
    cola: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _suscriptores.setdefault(session_id, set()).add(cola)
    return cola


def desuscribir(session_id: str, cola: "asyncio.Queue[dict[str, Any]]") -> None:
    """Elimina la cola de una conexión SSE cerrada (limpieza)."""
    colas = _suscriptores.get(session_id)
    if not colas:
        return
    colas.discard(cola)
    if not colas:
        _suscriptores.pop(session_id, None)


def hay_suscriptores(session_id: str) -> bool:
    """True si alguna conexión SSE está escuchando este sessionId."""
    return bool(_suscriptores.get(session_id))


async def publicar(session_id: str, evento: str, data: dict[str, Any]) -> None:
    """Encola un evento SSE para todas las conexiones del sessionId."""
    colas = _suscriptores.get(session_id)
    if not colas:
        return
    mensaje = {"event": evento, "data": data}
    for cola in list(colas):
        cola.put_nowait(mensaje)


async def publicar_estado(session_id: str, estado_bot: str) -> None:
    """Evento ``estado`` en transiciones PAUSED↔ACTIVE."""
    await publicar(session_id, "estado", {"estadoBot": estado_bot})


async def publicar_agente(session_id: str, texto: str, fecha: str) -> None:
    """Evento ``agente`` cuando el humano del CTIC escribe (handoff)."""
    await publicar(session_id, "agente", {"texto": texto, "fecha": fecha})


async def publicar_encuesta(session_id: str, mensaje: dict[str, Any]) -> None:
    """Evento ``encuesta`` cuando, tras cerrar el handoff, toca ofrecerla."""
    await publicar(session_id, "encuesta", mensaje)


def reset() -> None:
    """Vacía el registro (tests)."""
    _suscriptores.clear()
