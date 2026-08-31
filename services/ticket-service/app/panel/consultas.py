"""Consultas de catálogo para el panel (selects de filtros y asignación).

Los imports de app.models son diferidos: el dominio (tarea 2.4) se desarrolla
en paralelo y este módulo debe poder importarse (y probarse) sin él.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def listar_tecnicos(session: AsyncSession) -> list[Any]:
    """Usuarios con rol ``tecnico`` activos, para el select de asignación."""
    from app.models import Usuario

    resultado = await session.scalars(
        select(Usuario)
        .where(Usuario.rol == "tecnico", Usuario.activo.is_(True))
        .order_by(Usuario.nombre)
    )
    return list(resultado)


async def listar_categorias(session: AsyncSession) -> list[Any]:
    """Categorías activas, para el filtro del listado de tickets."""
    from app.models import Categoria

    resultado = await session.scalars(
        select(Categoria).where(Categoria.activo.is_(True)).order_by(Categoria.nombre)
    )
    return list(resultado)
