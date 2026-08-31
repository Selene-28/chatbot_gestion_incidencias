"""Handoff a agente humano (F-07) — chatbot-api es dueño del dominio conversacional.

- ``POST /api/chat/handoff``              — widget (X-Session-Token): pausa el bot.
- ``GET  /api/chat/handoffs``             — staff: cola de handoffs + últimos 20 msg.
- ``POST /api/chat/handoffs/{id}/atender``— staff: toma la conversación.
- ``POST /api/chat/handoffs/{id}/mensajes``— staff: mensaje del agente → SSE.
- ``GET  /api/chat/handoffs/{id}/mensajes``— staff: respaldo de polling del panel.
- ``POST /api/chat/handoffs/{id}/cerrar`` — staff: reactiva el bot (RN-06) + encuesta.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.tickets import get_tickets_client
from app.core.auth_staff import StaffActor, require_staff
from app.core.db import get_session
from app.core.envelope import ok
from app.core.errors import ConflictError, NotFoundError
from app.dialogo import textos
from app.dialogo.engine import Deps
from app.dialogo.manager import get_orquestador
from app.dialogo.tipos import texto_plano
from app.models import Conversacion, Handoff, Mensaje
from app.services import eventos, sesiones

logger = logging.getLogger("app.api.handoff")

router = APIRouter(prefix="/api/chat", tags=["handoff"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
StaffDep = Annotated[StaffActor, Depends(require_staff)]
TokenDep = Annotated[str | None, Header(alias="X-Session-Token")]

ESTADOS_CERRADOS = ("cerrado", "expirado")
ULTIMOS_MENSAJES = 20


# ------------------------------------------------------------------ schemas


class HandoffRequest(BaseModel):
    """Cuerpo de POST /api/chat/handoff (widget)."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    session_id: str = Field(alias="sessionId", max_length=36)
    motivo: str | None = Field(default=None, max_length=40)


class MensajeAgente(BaseModel):
    """Cuerpo de POST /api/chat/handoffs/{id}/mensajes (agente)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    texto: str = Field(min_length=1, max_length=2000)


# ------------------------------------------------------------------ utilidades


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


async def _get_handoff(session: AsyncSession, handoff_id: int) -> Handoff:
    handoff = await session.get(Handoff, handoff_id)
    if handoff is None:
        raise NotFoundError("El handoff no fue encontrado.")
    return handoff


async def _get_conversacion(session: AsyncSession, handoff: Handoff) -> Conversacion:
    conv = await session.get(Conversacion, handoff.conversacion_id)
    if conv is None:  # integridad referencial garantiza que exista
        raise NotFoundError("La conversación del handoff no fue encontrada.")
    return conv


async def _ultimos_mensajes(
    session: AsyncSession, conversacion_id: int, limite: int = ULTIMOS_MENSAJES
) -> list[dict[str, Any]]:
    """Los últimos ``limite`` mensajes de la conversación, en orden cronológico."""
    filas = (
        (
            await session.execute(
                select(Mensaje)
                .where(Mensaje.conversacion_id == conversacion_id)
                .order_by(Mensaje.id.desc())
                .limit(limite)
            )
        )
        .scalars()
        .all()
    )
    return [
        {"emisor": m.emisor, "contenido": m.contenido, "fecha": _iso(m.created_at)}
        for m in reversed(filas)
    ]


# ---------------------------------------------------------------- endpoints


@router.post("/handoff")
async def solicitar_handoff(
    body: HandoffRequest, session: SessionDep, x_session_token: TokenDep = None
) -> JSONResponse:
    """Widget: asegura un handoff pendiente y pausa el bot (RN-05)."""
    conv = await sesiones.autenticar(session, body.session_id, x_session_token)

    activo = (
        await session.execute(
            select(Handoff)
            .where(
                Handoff.conversacion_id == conv.id,
                Handoff.estado.in_(("pendiente", "atendido")),
            )
            .order_by(Handoff.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if activo is None:
        from app.dialogo.engine import sesion_de

        session.add(
            Handoff(
                conversacion_id=conv.id,
                motivo=body.motivo or "solicitud_usuario",
                ticket_codigo=sesion_de(conv).get("ultimo_ticket"),
            )
        )

    # RN-05: pausa el bot y abandona el flujo activo (los mensajes van al agente)
    get_orquestador().engine.cancelar(conv)
    conv.estado_bot = "PAUSED"
    conv.fallback_consecutivos = 0
    sesiones.guardar_mensaje(session, conv, "bot", textos.TRANSICION_HANDOFF, intent="handoff")
    await session.commit()

    await eventos.publicar_estado(conv.codigo, "PAUSED")
    return JSONResponse(
        content=ok({"estadoBot": "PAUSED", "mensaje": textos.TRANSICION_HANDOFF})
    )


@router.get("/handoffs")
async def listar_handoffs(
    session: SessionDep, staff: StaffDep, estado: str = "pendiente"
) -> JSONResponse:
    """Staff: cola de handoffs (pendiente|atendido|todos) con últimos 20 mensajes."""
    consulta = select(Handoff, Conversacion).join(
        Conversacion, Conversacion.id == Handoff.conversacion_id
    )
    if estado != "todos":
        filtro = estado if estado in ("pendiente", "atendido") else "pendiente"
        consulta = consulta.where(Handoff.estado == filtro)
    consulta = consulta.order_by(Handoff.solicitado_at.asc())

    filas = (await session.execute(consulta)).all()
    items = []
    for handoff, conv in filas:
        items.append(
            {
                "id": handoff.id,
                "sessionId": conv.codigo,
                "motivo": handoff.motivo,
                "estado": handoff.estado,
                "solicitadoAt": _iso(handoff.solicitado_at),
                "usuarioCorreo": conv.usuario_correo,
                "usuarioNombre": conv.usuario_nombre,
                "ultimosMensajes": await _ultimos_mensajes(session, conv.id),
            }
        )
    return JSONResponse(content=ok({"items": items, "total": len(items)}))


@router.post("/handoffs/{handoff_id}/atender")
async def atender_handoff(handoff_id: int, session: SessionDep, staff: StaffDep) -> JSONResponse:
    """Staff: asigna el handoff al agente autenticado (409 si ya está cerrado)."""
    handoff = await _get_handoff(session, handoff_id)
    if handoff.estado in ESTADOS_CERRADOS:
        raise ConflictError("El handoff ya fue cerrado o expiró.")
    handoff.agente_id = staff.id
    handoff.estado = "atendido"
    handoff.atendido_at = datetime.now()
    await session.commit()
    return JSONResponse(content=ok({"id": handoff.id, "estado": "atendido"}))


@router.post("/handoffs/{handoff_id}/mensajes")
async def mensaje_del_agente(
    handoff_id: int, body: MensajeAgente, session: SessionDep, staff: StaffDep
) -> JSONResponse:
    """Staff: el agente escribe al usuario; se entrega al widget por SSE (evento agente)."""
    handoff = await _get_handoff(session, handoff_id)
    if handoff.estado != "atendido":
        raise ConflictError("El handoff no está en atención.")
    conv = await _get_conversacion(session, handoff)
    sesiones.guardar_mensaje(session, conv, "agente", body.texto)
    await session.commit()

    await eventos.publicar_agente(conv.codigo, body.texto, datetime.now().isoformat())
    return JSONResponse(content=ok({"ok": True}))


@router.get("/handoffs/{handoff_id}/mensajes")
async def mensajes_del_usuario(
    handoff_id: int, session: SessionDep, staff: StaffDep, desde: int = 0
) -> JSONResponse:
    """Staff: respaldo de polling — mensajes de la conversación con id > ``desde``."""
    handoff = await _get_handoff(session, handoff_id)
    filas = (
        (
            await session.execute(
                select(Mensaje)
                .where(Mensaje.conversacion_id == handoff.conversacion_id, Mensaje.id > desde)
                .order_by(Mensaje.id)
            )
        )
        .scalars()
        .all()
    )
    items = [
        {"id": m.id, "emisor": m.emisor, "contenido": m.contenido, "fecha": _iso(m.created_at)}
        for m in filas
    ]
    ultimo_id = items[-1]["id"] if items else desde
    return JSONResponse(content=ok({"items": items, "ultimoId": ultimo_id}))


@router.post("/handoffs/{handoff_id}/cerrar")
async def cerrar_handoff(handoff_id: int, session: SessionDep, staff: StaffDep) -> JSONResponse:
    """Staff: cierra el handoff, reactiva el bot (RN-06) y ofrece la encuesta (F-08)."""
    handoff = await _get_handoff(session, handoff_id)
    if handoff.estado in ESTADOS_CERRADOS:
        raise ConflictError("El handoff ya fue cerrado o expiró.")
    conv = await _get_conversacion(session, handoff)

    handoff.estado = "cerrado"
    handoff.cerrado_at = datetime.now()
    conv.estado_bot = "ACTIVE"  # RN-06

    # Reutiliza el flujo de encuesta F-08: el bot vuelve y ofrece calificar.
    deps = Deps(session=session, tickets=get_tickets_client())
    encuesta_msgs = await get_orquestador().engine.iniciar(conv, "encuesta", deps)
    mensajes = [texto_plano(textos.HANDOFF_REACTIVADO), *encuesta_msgs]
    for mensaje in mensajes:
        sesiones.guardar_mensaje(session, conv, "bot", mensaje.texto)
    await session.commit()

    # SSE: transición a ACTIVE + el MensajeBot de encuesta para el widget
    await eventos.publicar_estado(conv.codigo, "ACTIVE")
    encuesta_bot = next((m for m in encuesta_msgs if m.tipo == "encuesta"), None)
    if encuesta_bot is not None:
        await eventos.publicar_encuesta(conv.codigo, encuesta_bot.a_dict())
    return JSONResponse(content=ok({"id": handoff.id, "estado": "cerrado"}))


__all__ = ["router"]
