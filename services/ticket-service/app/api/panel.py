"""Endpoints JSON del panel de agentes (RF-11, prd/04 §3 «Endpoints del panel»).

Todas las rutas exigen staff autenticado vía cookie ``panel_token``
(app.core.deps.require_staff). Los AppError del servicio de dominio
(404 no encontrado, 409 transición inválida, etc.) se propagan al
handler global, que los traduce al envelope estándar.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_staff
from app.core.envelope import ok
from app.core.errors import ValidationAppError
from app.panel import consultas
from app.schemas import comunes

router = APIRouter(prefix="/api/panel", tags=["panel"], dependencies=[Depends(require_staff)])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
StaffDep = Annotated[Any, Depends(require_staff)]


def _servicio_tickets() -> Any:
    """Módulo de servicios de dominio (import diferido).

    app.services.tickets lo implementa la tarea 2.4 en paralelo; diferir el
    import permite importar y probar este módulo sin el dominio presente.
    """
    from app.services import tickets

    return tickets


def _nombre_actor(evento: Any) -> str | None:
    """Nombre del actor de un evento de historial (None = sistema/chatbot)."""
    actor = getattr(evento, "actor", None)
    if actor is not None:
        return getattr(actor, "nombre", None)
    return None


def _ticket_resumen(ticket: Any) -> dict[str, Any]:
    """Proyección de listado: campos del contrato del panel (prd/04 §3)."""
    return {
        "ticketId": ticket.codigo,
        "estado": ticket.estado,
        "prioridad": ticket.prioridad,
        "categoria": ticket.categoria.nombre if ticket.categoria else None,
        "solicitante": ticket.usuario.nombre if ticket.usuario else None,
        "tecnico": ticket.tecnico.nombre if ticket.tecnico else None,
        "fechaRegistro": ticket.created_at.isoformat(),
    }


def _ticket_detalle(ticket: Any) -> dict[str, Any]:
    """Proyección de detalle: resumen + descripción + historial + adjuntos."""
    return {
        **_ticket_resumen(ticket),
        "subcategoria": ticket.subcategoria,
        "descripcion": ticket.descripcion,
        "respuesta": getattr(ticket, "respuesta", None),
        "ultimaActualizacion": ticket.updated_at.isoformat(),
        "adjuntos": [
            {
                "id": adjunto.id,
                "nombre": adjunto.nombre_original,
                "mimeType": adjunto.mime_type,
                "tamanoBytes": adjunto.tamano_bytes,
                "url": f"/panel/tickets/{ticket.codigo}/adjuntos/{adjunto.id}",
            }
            for adjunto in (getattr(ticket, "adjuntos", None) or [])
        ],
        "historial": [
            {
                "estadoAnterior": evento.estado_anterior,
                "estadoNuevo": evento.estado_nuevo,
                "comentario": evento.comentario,
                "actor": _nombre_actor(evento),
                "fecha": evento.created_at.isoformat(),
            }
            for evento in ticket.historial
        ],
    }


class PatchTicketRequest(BaseModel):
    """Cuerpo de PATCH /api/panel/tickets/{ticketId}: estado y/o técnico."""

    model_config = ConfigDict(populate_by_name=True)

    estado: str | None = None
    tecnico_id: int | None = Field(default=None, alias="tecnicoId")
    comentario: str | None = Field(default=None, max_length=comunes.COMENTARIO_MAX)
    respuesta: str | None = Field(default=None, max_length=comunes.RESPUESTA_MAX)


@router.get("/tickets")
async def listar_tickets(
    session: SessionDep,
    estado: Annotated[str | None, Query(max_length=20)] = None,
    categoria: Annotated[int | None, Query(ge=1)] = None,
    tecnico: Annotated[int | None, Query(ge=1)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    """Listado con filtros y paginación (prd/04 §5: data.items + data.total)."""
    items, total = await _servicio_tickets().listar_tickets(
        session,
        estado=estado or None,
        categoria_id=categoria,
        tecnico_id=tecnico,
        page=page,
        size=size,
    )
    return ok({"items": [_ticket_resumen(t) for t in items], "total": total})


@router.get("/tickets/{ticket_id}")
async def obtener_ticket(ticket_id: str, session: SessionDep) -> JSONResponse:
    """Detalle de un ticket con su historial de estados."""
    ticket = await _servicio_tickets().obtener_ticket(session, ticket_id)
    return ok(_ticket_detalle(ticket))


@router.patch("/tickets/{ticket_id}")
async def actualizar_ticket(
    ticket_id: str, body: PatchTicketRequest, session: SessionDep, staff: StaffDep
) -> JSONResponse:
    """Asigna técnico y/o cambia estado, con el staff autenticado como actor.

    Orden: primero la asignación (Registrado→Asignado suele requerirla) y
    luego la transición de estado. Las transiciones inválidas (RN-02) llegan
    como ConflictError 409 desde el dominio y se propagan tal cual.
    """
    if body.estado is None and body.tecnico_id is None and body.respuesta is None:
        raise ValidationAppError(
            "Debe indicar al menos un cambio (estado, tecnicoId o respuesta).",
            [{"field": "estado", "description": "No se indicó ningún cambio a aplicar."}],
        )
    servicio = _servicio_tickets()
    ticket = None
    if body.tecnico_id is not None:
        ticket = await servicio.asignar_tecnico(
            session, codigo=ticket_id, tecnico_id=body.tecnico_id, actor_id=staff.id
        )
    if body.estado is not None:
        ticket = await servicio.cambiar_estado(
            session,
            codigo=ticket_id,
            nuevo_estado=body.estado,
            actor_id=staff.id,
            comentario=body.comentario,
        )
    if body.respuesta is not None:
        ticket = await servicio.guardar_respuesta(
            session, codigo=ticket_id, texto=body.respuesta, actor_id=staff.id
        )
    return ok(_ticket_detalle(ticket), "El ticket fue actualizado correctamente.")


@router.get("/tecnicos")
async def listar_tecnicos(session: SessionDep) -> JSONResponse:
    """Técnicos activos (para el select de asignación del panel)."""
    tecnicos = await consultas.listar_tecnicos(session)
    return ok(
        {
            "items": [
                {"id": t.id, "nombre": t.nombre, "correo": t.correo} for t in tecnicos
            ]
        }
    )
