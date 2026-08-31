"""Endpoint de métricas del chatbot (tarea 5.4 / RF-14, prd/04 §8, prd/03 §4).

``GET /api/metricas/resumen?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`` — rol ``admin``.

Fuentes:
- chatbot_db: conteo de conversaciones/mensajes y las vistas SQL
  ``v_autoservicio_diario``, ``v_latencia_bot`` e ``v_intents_frecuentes``.
- ticket-service (vía cliente HTTP): ticketsPorEstado, calificacionProm, encuestas
  (viven en tickets_db / vista v_satisfaccion).
- llm.tokens_consumidos(): total de tokens LLM del proceso (0 sin API key).
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.tickets import get_tickets_client
from app.core.auth_staff import StaffActor, require_admin
from app.core.db import get_session
from app.core.envelope import ok
from app.core.errors import AppError, ValidationAppError
from app.ia import llm

logger = logging.getLogger("app.api.metricas")

router = APIRouter(prefix="/api/metricas", tags=["metricas"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminDep = Annotated[StaffActor, Depends(require_admin)]


def _validar_fecha(valor: str, campo: str) -> str:
    """Valida el formato YYYY-MM-DD; 400 con el campo si no es una fecha."""
    try:
        datetime.strptime(valor, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationAppError(
            "El rango de fechas es inválido.",
            errors=[{"field": campo, "description": "Use el formato YYYY-MM-DD."}],
        ) from exc
    return valor


@router.get("/resumen")
async def resumen(
    session: SessionDep, admin: AdminDep, desde: str, hasta: str
) -> JSONResponse:
    """Resumen de métricas del rango [desde, hasta] (prd/04 §8)."""
    desde = _validar_fecha(desde, "desde")
    hasta = _validar_fecha(hasta, "hasta")
    rango = {"desde": desde, "hasta": hasta}

    conversaciones = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM conversaciones "
                "WHERE DATE(iniciada_at) BETWEEN :desde AND :hasta"
            ),
            rango,
        )
    ).scalar_one()

    mensajes = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM mensajes m "
                "JOIN conversaciones c ON c.id = m.conversacion_id "
                "WHERE DATE(c.iniciada_at) BETWEEN :desde AND :hasta"
            ),
            rango,
        )
    ).scalar_one()

    # Latencia media ponderada por número de respuestas (vista v_latencia_bot)
    latencia_ms = (
        await session.execute(
            text(
                "SELECT ROUND(SUM(respuestas * latencia_prom_ms) / NULLIF(SUM(respuestas), 0)) "
                "FROM v_latencia_bot WHERE fecha BETWEEN :desde AND :hasta"
            ),
            rango,
        )
    ).scalar_one()

    # Intenciones más frecuentes (vista v_intents_frecuentes; no está fechada, por
    # lo que refleja el histórico completo — limitación conocida de la vista).
    intents_top = [
        {"intent": fila.intent, "total": int(fila.total)}
        for fila in (
            await session.execute(
                text("SELECT intent, total FROM v_intents_frecuentes LIMIT 10")
            )
        ).all()
    ]

    # Tasa de autoservicio (vista v_autoservicio_diario): referencia tickets_db,
    # que puede no existir en algunos entornos → degrada a null si la vista falla.
    tasa_autoservicio: float | None = None
    try:
        fila = (
            await session.execute(
                text(
                    "SELECT SUM(conversaciones) AS conv, SUM(sin_ticket) AS sin_t "
                    "FROM v_autoservicio_diario WHERE fecha BETWEEN :desde AND :hasta"
                ),
                rango,
            )
        ).one()
        if fila.conv:
            tasa_autoservicio = round(float(fila.sin_t or 0) / float(fila.conv), 2)
    except Exception as exc:  # noqa: BLE001 — la vista puede no existir (tickets_db)
        await session.rollback()
        logger.warning("v_autoservicio_diario no disponible: %s", exc)

    # Métricas del lado de tickets (ticket-service); degrada si no responde
    tickets_data: dict[str, Any] = {}
    try:
        tickets_data = await get_tickets_client().resumen_metricas(desde, hasta)
    except AppError as exc:
        logger.warning("Métricas de tickets no disponibles: %s", exc.message)

    data = {
        "conversaciones": int(conversaciones),
        "mensajes": int(mensajes),
        "tasaAutoservicio": tasa_autoservicio,
        "latenciaPromMs": int(latencia_ms) if latencia_ms is not None else None,
        "calificacionProm": tickets_data.get("calificacionProm"),
        "encuestas": int(tickets_data.get("encuestas") or 0),
        "ticketsPorEstado": tickets_data.get("ticketsPorEstado") or {},
        "intentsTop": intents_top,
        "tokensLlm": llm.tokens_consumidos(),
    }
    return JSONResponse(content=ok(data))


__all__ = ["router"]
