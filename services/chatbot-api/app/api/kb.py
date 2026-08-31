"""API de gestión de la base de conocimiento (tarea 5.3 / RF-12, prd/04 §4).

Lectura para todo el staff; escritura solo para ``admin``. Cada escritura
reindexa el artículo afectado en el índice vectorial (indexado incremental,
REN-06) para que la búsqueda semántica no requiera reiniciar el servicio.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_staff import StaffActor, require_admin, require_staff
from app.core.db import get_session
from app.core.envelope import ok
from app.core.errors import NotFoundError
from app.ia import indexado
from app.models import KbArticulo

logger = logging.getLogger("app.api.kb")

router = APIRouter(prefix="/api/kb", tags=["kb"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
StaffDep = Annotated[StaffActor, Depends(require_staff)]
AdminDep = Annotated[StaffActor, Depends(require_admin)]

SIZE_DEFAULT = 20
SIZE_MAX = 100


# ------------------------------------------------------------------ schemas


class ArticuloIn(BaseModel):
    """Cuerpo de creación/edición de un artículo (admin)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    titulo: str = Field(min_length=1, max_length=200)
    contenido: str = Field(min_length=1, max_length=200_000)
    categoria: str = Field(min_length=1, max_length=80)
    etiquetas: list[str] = Field(default_factory=list, max_length=50)


def _unir_etiquetas(etiquetas: list[str]) -> str | None:
    """Normaliza la lista de etiquetas a la cadena separada por comas del DDL."""
    limpias = [e.strip() for e in etiquetas if e and e.strip()]
    return ",".join(limpias) or None


def _lista_etiquetas(etiquetas: str | None) -> list[str]:
    """Separa la cadena persistida en lista (contrato JSON del panel)."""
    if not etiquetas:
        return []
    return [e.strip() for e in etiquetas.split(",") if e.strip()]


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _resumen(art: KbArticulo) -> dict[str, Any]:
    """Vista de listado (sin el contenido completo)."""
    return {
        "id": art.id,
        "titulo": art.titulo,
        "categoria": art.categoria,
        "etiquetas": _lista_etiquetas(art.etiquetas),
        "activo": bool(art.activo),
        "version": art.version,
        "updatedAt": _iso(art.updated_at),
    }


def _detalle(art: KbArticulo) -> dict[str, Any]:
    """Vista completa (incluye el contenido)."""
    return {**_resumen(art), "contenido": art.contenido}


async def _get_articulo(session: AsyncSession, articulo_id: int) -> KbArticulo:
    art = await session.get(KbArticulo, articulo_id)
    if art is None:
        raise NotFoundError("El artículo no fue encontrado.")
    return art


# ---------------------------------------------------------------- endpoints


@router.get("/articulos")
async def listar_articulos(
    session: SessionDep,
    staff: StaffDep,
    activo: bool | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = SIZE_DEFAULT,
) -> JSONResponse:
    """Staff: lista paginada de artículos con filtros por estado y texto."""
    page = max(1, page)
    size = max(1, min(size, SIZE_MAX))

    filtros = []
    if activo is not None:
        filtros.append(KbArticulo.activo == activo)
    if q:
        patron = f"%{q.strip()}%"
        filtros.append(
            or_(
                KbArticulo.titulo.like(patron),
                KbArticulo.contenido.like(patron),
                KbArticulo.etiquetas.like(patron),
            )
        )

    total = (
        await session.execute(select(func.count()).select_from(KbArticulo).where(*filtros))
    ).scalar_one()
    filas = (
        (
            await session.execute(
                select(KbArticulo)
                .where(*filtros)
                .order_by(KbArticulo.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .all()
    )
    return JSONResponse(
        content=ok({"items": [_resumen(a) for a in filas], "total": int(total)})
    )


@router.get("/articulos/{articulo_id}")
async def obtener_articulo(articulo_id: int, session: SessionDep, staff: StaffDep) -> JSONResponse:
    """Staff: artículo completo (incluye el contenido)."""
    art = await _get_articulo(session, articulo_id)
    return JSONResponse(content=ok(_detalle(art)))


@router.post("/articulos")
async def crear_articulo(body: ArticuloIn, session: SessionDep, admin: AdminDep) -> JSONResponse:
    """Admin: crea un artículo (version=1) y lo indexa en el motor semántico."""
    art = KbArticulo(
        titulo=body.titulo,
        contenido=body.contenido,
        categoria=body.categoria,
        etiquetas=_unir_etiquetas(body.etiquetas),
        version=1,
        activo=True,
        updated_by=admin.id,
    )
    session.add(art)
    await session.commit()
    await session.refresh(art)

    await indexado.indexar_articulo(art)
    return JSONResponse(status_code=201, content=ok({"id": art.id}, code=201))


@router.put("/articulos/{articulo_id}")
async def actualizar_articulo(
    articulo_id: int, body: ArticuloIn, session: SessionDep, admin: AdminDep
) -> JSONResponse:
    """Admin: actualiza el artículo (version+1) y lo re-indexa."""
    art = await _get_articulo(session, articulo_id)
    art.titulo = body.titulo
    art.contenido = body.contenido
    art.categoria = body.categoria
    art.etiquetas = _unir_etiquetas(body.etiquetas)
    art.version = int(art.version or 1) + 1
    art.updated_by = admin.id
    await session.commit()
    await session.refresh(art)

    await indexado.indexar_articulo(art)
    return JSONResponse(content=ok(_detalle(art)))


@router.delete("/articulos/{articulo_id}")
async def desactivar_articulo(
    articulo_id: int, session: SessionDep, admin: AdminDep
) -> JSONResponse:
    """Admin: baja lógica (activo=false) y retiro del índice vectorial."""
    art = await _get_articulo(session, articulo_id)
    art.activo = False
    await session.commit()

    indexado.desindexar(art.id)
    return JSONResponse(content=ok({"ok": True}))


@router.post("/reindex")
async def reindexar(session: SessionDep, admin: AdminDep) -> JSONResponse:
    """Admin: reconstruye el índice completo desde MySQL (idempotente)."""
    indexados = await indexado.reindexar_todo(session)
    return JSONResponse(content=ok({"indexados": indexados}))


__all__ = ["router"]
