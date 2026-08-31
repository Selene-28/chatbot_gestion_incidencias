"""Endpoints de incidencias (API-01, API-01b, API-02, API-03 — prd/04 §3).

Todos protegidos con la API key de servicio (header X-Api-Key).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.envelope import ok
from app.core.errors import ForbiddenError, ValidationAppError
from app.core.security import require_api_key
from app.models import Ticket
from app.schemas import comunes
from app.schemas.incidencias import EscalarRequest, IncidenciaCreate
from app.services import adjuntos as servicio_adjuntos
from app.services import tickets as servicio_tickets
from app.services.tickets import ESTADOS_TERMINADOS

router = APIRouter(
    prefix="/api/incidencias",
    tags=["incidencias"],
    dependencies=[Depends(require_api_key)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

OBSERVACIONES_POR_DEFECTO = "Incidencia registrada, pendiente de atención."
LISTADO_MAXIMO = 10  # prd/04 §3: consulta por correo devuelve máx. 10 tickets


def _observaciones(ticket: Ticket) -> str:
    """Respuesta si el ticket está terminado; si no, el último comentario del técnico."""
    if ticket.estado in ESTADOS_TERMINADOS and (ticket.respuesta or "").strip():
        return ticket.respuesta.strip()
    for entrada in reversed(ticket.historial):
        if entrada.comentario:
            return entrada.comentario
    return OBSERVACIONES_POR_DEFECTO


def _ticket_a_dict(ticket: Ticket) -> dict[str, Any]:
    """Serializa un ticket con los campos EXACTOS de API-02 (prd/04 §3)."""
    respuesta = (ticket.respuesta or "").strip() or None
    return {
        "ticketId": ticket.codigo,
        "estado": ticket.estado,
        "categoria": ticket.categoria.nombre,
        "fechaRegistro": ticket.created_at.isoformat(),
        "tecnico": ticket.tecnico.nombre if ticket.tecnico else None,
        "ultimaActualizacion": ticket.updated_at.isoformat(),
        "observaciones": _observaciones(ticket),
        "respuesta": respuesta if ticket.estado in ESTADOS_TERMINADOS else None,
    }


def _validar_correo_consulta(correo: str) -> str:
    """Valida el query param `correo` de las consultas (RF-15)."""
    correo = comunes.normalizar_correo(correo)
    if not comunes.es_correo_institucional(correo):
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[{"field": "correo", "description": comunes.MSG_CORREO_DOMINIO}],
        )
    return correo


@router.post("")
async def registrar_incidencia(
    payload: IncidenciaCreate,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", max_length=64)
    ] = None,
) -> JSONResponse:
    """API-01: registra una incidencia y devuelve su código único (RN-01)."""
    ticket = await servicio_tickets.registrar_incidencia(
        session,
        nombre=payload.nombre,
        correo=payload.correo,
        area=payload.area,
        categoria=payload.categoria,
        subcategoria=payload.subcategoria,
        descripcion=payload.descripcion,
        prioridad=payload.prioridad,
        origen=payload.origen,
        conversacion_codigo=payload.conversacion_codigo,
        adjunto_id=payload.adjunto_id,
        idempotency_key=idempotency_key,
    )
    return ok(
        {"ticketId": ticket.codigo, "estado": ticket.estado},
        message="La incidencia fue registrada correctamente.",
        code=201,
    )


@router.post("/adjuntos")
async def subir_adjunto(
    session: SessionDep,
    file: Annotated[UploadFile, File(description="JPG/JPEG/PNG/PDF, máx. 5 MB")],
) -> JSONResponse:
    """API-01b: sube un adjunto previo al registro; valida MIME real y tamaño (RF-13)."""
    contenido = await file.read()
    fila = await servicio_adjuntos.subir_adjunto(
        session, filename=file.filename or "adjunto", content=contenido
    )
    return ok(
        {"adjuntoId": fila.id},
        message="El archivo fue cargado correctamente.",
        code=201,
    )


@router.get("")
async def listar_incidencias(
    session: SessionDep,
    correo: Annotated[str, Query(description="Correo institucional del propietario")],
) -> JSONResponse:
    """API-02 (por correo): lista los tickets del correo, fecha desc, máx. 10 (RN-03)."""
    correo = _validar_correo_consulta(correo)
    tickets = await servicio_tickets.listar_por_correo(session, correo, limite=LISTADO_MAXIMO)
    return ok(
        {"items": [_ticket_a_dict(t) for t in tickets], "total": len(tickets)},
        message="OK",
    )


@router.get("/{ticket_id}")
async def consultar_incidencia(
    ticket_id: str,
    session: SessionDep,
    correo: Annotated[str, Query(description="Correo institucional del propietario")],
) -> JSONResponse:
    """API-02: consulta el estado de una incidencia; RN-03: solo el propietario."""
    correo = _validar_correo_consulta(correo)
    ticket = await servicio_tickets.obtener_ticket(session, ticket_id)
    if ticket.usuario.correo != correo:
        # RN-03: sin filtrar datos del ticket ajeno
        raise ForbiddenError("No tiene permiso para consultar esta incidencia.")
    return ok(_ticket_a_dict(ticket), message="OK")


@router.put("/escalar")
async def escalar_incidencia(payload: EscalarRequest, session: SessionDep) -> JSONResponse:
    """API-03: escala una incidencia al personal técnico (RN-02/RN-03)."""
    ticket = await servicio_tickets.escalar(
        session, codigo=payload.ticket_id, motivo=payload.motivo, correo=payload.correo
    )
    return ok(
        {"estado": ticket.estado},
        message="La incidencia fue derivada al personal técnico.",
    )
