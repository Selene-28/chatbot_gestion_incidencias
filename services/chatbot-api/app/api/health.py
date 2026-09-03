"""Endpoint de salud para healthchecks de Docker y monitoreo (prd/04 §4).

Nota: este endpoint es de infraestructura y NO usa el envelope estándar.
"""

from fastapi import APIRouter

from app.core.db import check_db
from app.ia import llm

router = APIRouter(tags=["infraestructura"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Devuelve 200 siempre que la app viva; reporta estado de dependencias.

    llm: "configured" (key real sk-ant-…) | "degraded" (circuit breaker abierto,
    prd/06 §6) | "disabled" (sin key o placeholder de .env.example).
    """
    db_ok = await check_db(timeout=2.0)
    return {
        "status": "ok",
        "db": "ok" if db_ok else "down",
        "llm": llm.estado_llm(),
    }
