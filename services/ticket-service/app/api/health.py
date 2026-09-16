"""Endpoint de salud para healthchecks Docker y monitoreo (prd/04 §4)."""

from typing import Any

from fastapi import APIRouter

from app.core.db import check_db
from app.core.mysql_url import ultimo_error_mysql

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Estado del servicio y de la base de datos (sin envelope)."""
    db_ok = await check_db()
    cuerpo: dict[str, Any] = {"status": "ok", "db": "ok" if db_ok else "down"}
    if not db_ok:
        detalle = ultimo_error_mysql()
        if detalle:
            cuerpo["db_error"] = detalle
    return cuerpo
