"""Superficie de chat del widget (prd/04 §4) + auditoría de conversaciones.

Protocolo compartido con el widget (EXACTO):
- POST /api/chat/sesiones       → 201 {sessionId, sessionToken, mensajeBienvenida, menu}
- POST /api/chat/mensajes       → 200 {mensajes: [MensajeBot], estadoBot}
- POST /api/chat/adjuntos       → proxy API-01b (el widget nunca conoce la X-Api-Key)
- GET  /api/chat/conversaciones/{sessionId}/mensajes → auditoría QA-07
"""

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.tickets import get_tickets_client
from app.core.auth_staff import StaffActor, require_staff
from app.core.db import get_session
from app.core.envelope import ok
from app.core.errors import NotFoundError
from app.dialogo import textos
from app.dialogo.engine import Deps
from app.dialogo.manager import get_orquestador
from app.dialogo.tipos import Entrada, MensajeBot, Opcion
from app.models import Conversacion, Mensaje
from app.services import eventos, sesiones

logger = logging.getLogger("app.api.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TokenDep = Annotated[str | None, Header(alias="X-Session-Token")]


# ------------------------------------------------------------------ schemas


class SesionCreate(BaseModel):
    """Cuerpo de POST /api/chat/sesiones."""

    canal: str = "web_widget"


class MensajeIn(BaseModel):
    """Cuerpo de POST /api/chat/mensajes: uno de `texto` u `opcionId`."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    session_id: str = Field(alias="sessionId", max_length=36)
    texto: str | None = Field(default=None, max_length=4000)
    opcion_id: str | None = Field(default=None, alias="opcionId", max_length=80)
    adjunto_id: str | None = Field(default=None, alias="adjuntoId", max_length=40)

    @model_validator(mode="after")
    def _texto_u_opcion(self) -> "MensajeIn":
        if not self.texto and not self.opcion_id:
            raise PydanticCustomError(
                "entrada_vacia", "Debe enviar `texto` o `opcionId`."
            )
        if self.texto and self.opcion_id:
            raise PydanticCustomError(
                "entrada_ambigua", "Envíe solo uno de `texto` u `opcionId`."
            )
        return self


# ---------------------------------------------------------------- endpoints


@router.post("/sesiones")
async def crear_sesion(session: SessionDep, body: SesionCreate | None = None) -> JSONResponse:
    """Crea la sesión de chat: sessionId + token opaco + bienvenida + menú."""
    conv, token = await sesiones.crear_sesion(session, canal=(body or SesionCreate()).canal)
    # RF-09: la bienvenida y el menú también quedan registrados
    sesiones.guardar_mensaje(session, conv, "bot", textos.BIENVENIDA, intent="saludo")
    await session.commit()
    menu = [Opcion(id=i, texto=t).model_dump() for i, t in textos.MENU_OPCIONES]
    return JSONResponse(
        status_code=201,
        content=ok(
            {
                "sessionId": conv.codigo,
                "sessionToken": token,
                "mensajeBienvenida": textos.BIENVENIDA,
                "menu": menu,
            },
            code=201,
        ),
    )


@router.post("/mensajes")
async def enviar_mensaje(
    body: MensajeIn, session: SessionDep, x_session_token: TokenDep = None
) -> JSONResponse:
    """Procesa un mensaje del usuario y devuelve la respuesta del bot (F-01)."""
    inicio = time.perf_counter()
    conv = await sesiones.autenticar(session, body.session_id, x_session_token)
    estado_previo = conv.estado_bot

    entrada = Entrada(
        texto=body.texto or None,
        opcion_id=body.opcion_id or None,
        adjunto_id=body.adjunto_id or None,
    )
    deps = Deps(session=session, tickets=get_tickets_client())
    turno = await get_orquestador().procesar(conv, entrada, deps)

    latencia_ms = int((time.perf_counter() - inicio) * 1000)
    contenido_usuario = body.texto if body.texto else f"[opción] {body.opcion_id}"
    if body.adjunto_id:
        contenido_usuario += f" [adjunto {body.adjunto_id}]"
    sesiones.guardar_mensaje(
        session,
        conv,
        "usuario",
        contenido_usuario,
        intent=turno.intent,
        confianza=turno.confianza,
    )
    # RN-05: con el bot en PAUSED el mensaje del usuario queda para el agente y el
    # acuse del bot NO se persiste (no es una respuesta del motor de intenciones).
    if turno.persistir_bot:
        for mensaje in turno.mensajes:
            sesiones.guardar_mensaje(
                session,
                conv,
                "bot",
                mensaje.texto,
                intent=(mensaje.meta or {}).get("intent"),
                latencia_ms=latencia_ms,
            )
    await session.commit()

    # SSE: notifica transiciones PAUSED↔ACTIVE a otras conexiones del widget
    if conv.estado_bot != estado_previo:
        await eventos.publicar_estado(conv.codigo, conv.estado_bot)

    return JSONResponse(
        status_code=200,
        content=ok(
            {
                "mensajes": [m.a_dict() for m in turno.mensajes],
                "estadoBot": conv.estado_bot,
            }
        ),
    )


@router.post("/adjuntos")
async def subir_adjunto(
    session: SessionDep,
    file: Annotated[UploadFile, File(description="JPG/JPEG/PNG/PDF, máx. 5 MB")],
    x_session_token: TokenDep = None,
) -> JSONResponse:
    """Proxy hacia API-01b del ticket-service (el widget nunca ve la X-Api-Key)."""
    await sesiones.autenticar_por_token(session, x_session_token)
    contenido = await file.read()
    data = await get_tickets_client().subir_adjunto(
        filename=file.filename or "adjunto",
        content=contenido,
        mime=file.content_type or "application/octet-stream",
    )
    return JSONResponse(
        status_code=201,
        content=ok(
            {
                "adjuntoId": data.get("adjuntoId"),
                "nombreOriginal": file.filename or "adjunto",
            },
            message="El archivo fue cargado correctamente.",
            code=201,
        ),
    )


@router.get("/conversaciones/{session_id}/mensajes")
async def listar_mensajes(
    session_id: str,
    session: SessionDep,
    _staff: Annotated[StaffActor, Depends(require_staff)],
) -> JSONResponse:
    """Auditoría QA-07/QA-08: historial completo de una conversación (staff).

    Protegido con el JWT del staff (cookie ``panel_token``); 401 si falta o es
    inválido. Cualquier rol de staff (tecnico|admin) puede consultarlo.
    """
    conv = (
        await session.execute(select(Conversacion).where(Conversacion.codigo == session_id))
    ).scalar_one_or_none()
    if conv is None:
        raise NotFoundError("La conversación no fue encontrada.")
    filas = (
        (
            await session.execute(
                select(Mensaje).where(Mensaje.conversacion_id == conv.id).order_by(Mensaje.id)
            )
        )
        .scalars()
        .all()
    )
    return JSONResponse(
        status_code=200,
        content=ok(
            {
                "sessionId": conv.codigo,
                "estado": conv.estado,
                "mensajes": [_mensaje_a_dict(m) for m in filas],
                "total": len(filas),
            }
        ),
    )


# ---------------------------------------------------------------- utilidades


def _mensaje_a_dict(mensaje: Mensaje) -> dict[str, Any]:
    """Serializa un mensaje para la vista de auditoría."""
    return {
        "id": mensaje.id,
        "emisor": mensaje.emisor,
        "contenido": mensaje.contenido,
        "intent": mensaje.intent,
        "confianza": float(mensaje.confianza) if mensaje.confianza is not None else None,
        "latenciaMs": mensaje.latencia_ms,
        "createdAt": mensaje.created_at.isoformat() if mensaje.created_at else None,
    }


__all__ = ["router", "MensajeIn", "SesionCreate", "MensajeBot"]
