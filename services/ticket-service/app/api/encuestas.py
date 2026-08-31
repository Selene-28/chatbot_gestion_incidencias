"""Endpoint de encuesta de satisfacción (API-06 — prd/04 §3, RN-04)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.envelope import ok
from app.core.security import require_api_key
from app.schemas.encuestas import EncuestaCreate
from app.services import tickets as servicio_tickets

router = APIRouter(prefix="/api", tags=["encuestas"], dependencies=[Depends(require_api_key)])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/encuesta")
async def registrar_encuesta(payload: EncuestaCreate, session: SessionDep) -> JSONResponse:
    """API-06: registra la calificación 1–5; una sola por atención (RN-04)."""
    await servicio_tickets.registrar_encuesta(
        session,
        ticket_codigo=payload.ticket_id,
        conversacion_codigo=payload.conversacion_codigo,
        calificacion=payload.calificacion,
        comentario=payload.comentario,
    )
    return ok({}, message="Gracias por valorar nuestro servicio.", code=201)
