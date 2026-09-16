"""Endpoint de salud para healthchecks Docker y monitoreo (prd/04 §4)."""

from typing import Any

from fastapi import APIRouter

from app.core.db import check_db
from app.core.mysql_url import diagnostico_dns, ultimo_error_mysql
from app.services.adjuntos import directorio_uploads

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Estado del servicio y de la base de datos (sin envelope)."""
    db_ok = await check_db()
    cuerpo: dict[str, Any] = {"status": "ok", "db": "ok" if db_ok else "down"}
    try:
        directorio_uploads()
        cuerpo["uploads"] = "ok"
    except OSError:
        cuerpo["uploads"] = "unwritable"
    if not db_ok:
        detalle = ultimo_error_mysql()
        if detalle:
            cuerpo["db_error"] = detalle
        cuerpo["dns"] = diagnostico_dns()
    return cuerpo
