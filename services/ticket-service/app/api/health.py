"""Endpoint de salud para healthchecks Docker y monitoreo (prd/04 §4)."""

from typing import Any

from fastapi import APIRouter

from app.core.db import check_db

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Estado del servicio y de la base de datos (sin envelope)."""
    db_ok = await check_db()
    return {"status": "ok", "db": "ok" if db_ok else "down"}
