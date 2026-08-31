"""Carga (upsert) de la base de conocimiento inicial + reindexado (tarea 4.5).

Uso: ``python -m app.scripts.cargar_kb``

- Upsert idempotente por ``titulo``: crea los artículos que falten y actualiza
  contenido/categoría/etiquetas de los existentes (incrementando ``version``
  solo si algo cambió). No borra artículos ajenos a ``datos_kb``.
- Al final ejecuta ``reindexar_todo`` (el índice Chroma queda consistente).

Variables de entorno relevantes: DB_URL y CHROMA_DIR (ver app/core/config.py).
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.ia.indexado import reindexar_todo
from app.models import KbArticulo
from app.scripts.datos_kb import ARTICULOS


async def upsert_articulos(session: AsyncSession) -> tuple[int, int, int]:
    """Inserta/actualiza los artículos de datos_kb. → (creados, actualizados, sin_cambios)."""
    creados = actualizados = sin_cambios = 0
    for datos in ARTICULOS:
        existente = (
            await session.execute(select(KbArticulo).where(KbArticulo.titulo == datos["titulo"]))
        ).scalar_one_or_none()
        if existente is None:
            session.add(
                KbArticulo(
                    titulo=datos["titulo"],
                    contenido=datos["contenido"],
                    categoria=datos["categoria"],
                    etiquetas=datos["etiquetas"],
                    activo=True,
                    version=1,
                )
            )
            creados += 1
            continue
        cambio = (
            existente.contenido != datos["contenido"]
            or existente.categoria != datos["categoria"]
            or (existente.etiquetas or "") != datos["etiquetas"]
            or not existente.activo
        )
        if not cambio:
            sin_cambios += 1
            continue
        existente.contenido = datos["contenido"]
        existente.categoria = datos["categoria"]
        existente.etiquetas = datos["etiquetas"]
        existente.activo = True
        existente.version = int(existente.version or 1) + 1
        actualizados += 1
    await session.commit()
    return creados, actualizados, sin_cambios


async def main() -> None:
    """Sesión propia (no reutiliza el pool de la app) + resumen por stdout."""
    settings = get_settings()
    engine = create_async_engine(settings.DB_URL)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with fabrica() as session:
            creados, actualizados, sin_cambios = await upsert_articulos(session)
            indexados = await reindexar_todo(session)
    finally:
        await engine.dispose()

    print("Carga de la base de conocimiento (CONTENIDO PROVISIONAL — validar con el CTIC):")
    print(f"  - artículos creados:      {creados}")
    print(f"  - artículos actualizados: {actualizados}")
    print(f"  - sin cambios:            {sin_cambios}")
    print(f"  - artículos indexados:    {indexados}  (Chroma: {settings.CHROMA_DIR})")


if __name__ == "__main__":
    asyncio.run(main())
