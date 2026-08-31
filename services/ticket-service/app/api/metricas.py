"""Métricas del dominio de tickets para el dashboard (RF-14, prd/04 §8).

``GET /api/metricas/tickets?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`` — auth X-Api-Key.
Lo consume chatbot-api (cliente HTTP) para componer /api/metricas/resumen, ya que
los tickets, encuestas y la vista v_satisfaccion viven en tickets_db.

Devuelve, en el rango de fechas (inclusive):
  - ``ticketsPorEstado``: conteo de tickets por estado (por fecha de registro)
  - ``calificacionProm``: promedio de calificaciones de encuestas (o null)
  - ``encuestas``: número de encuestas registradas
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.envelope import ok
from app.core.security import require_api_key
from app.models import Encuesta, Ticket

router = APIRouter(
    prefix="/api/metricas", tags=["metricas"], dependencies=[Depends(require_api_key)]
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Los rangos llegan como fecha (YYYY-MM-DD); el límite superior es inclusive
# hasta el fin de ese día.
_FIN_DEL_DIA = " 23:59:59"


@router.get("/tickets")
async def metricas_tickets(session: SessionDep, desde: str, hasta: str) -> JSONResponse:
    """Conteo de tickets por estado + satisfacción, en el rango dado."""
    hasta_fin = hasta + _FIN_DEL_DIA

    por_estado_filas = (
        await session.execute(
            select(Ticket.estado, func.count())
            .where(Ticket.created_at >= desde, Ticket.created_at <= hasta_fin)
            .group_by(Ticket.estado)
        )
    ).all()
    tickets_por_estado = {estado: total for estado, total in por_estado_filas}

    encuesta_fila = (
        await session.execute(
            select(func.avg(Encuesta.calificacion), func.count()).where(
                Encuesta.created_at >= desde, Encuesta.created_at <= hasta_fin
            )
        )
    ).one()
    promedio, n_encuestas = encuesta_fila
    calificacion_prom = round(float(promedio), 2) if promedio is not None else None

    return ok(
        {
            "ticketsPorEstado": tickets_por_estado,
            "calificacionProm": calificacion_prom,
            "encuestas": int(n_encuestas or 0),
        }
    )


__all__ = ["router"]
