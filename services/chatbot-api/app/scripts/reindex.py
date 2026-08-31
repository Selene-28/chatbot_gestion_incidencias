"""Reindexación completa del índice vectorial (prd/06 §4). Idempotente.

Uso: ``python -m app.scripts.reindex``

Reconstruye la colección "kb" de Chroma desde ``kb_articulos`` (MySQL):
upsert de todos los artículos activos y retiro de los inactivos. Pensado para
el arranque inicial y para cambios de modelo de embeddings.
"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.ia.indexado import get_coleccion, reindexar_todo


async def main() -> None:
    """Sesión propia contra DB_URL + resumen por stdout."""
    settings = get_settings()
    engine = create_async_engine(settings.DB_URL)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with fabrica() as session:
            indexados = await reindexar_todo(session)
    finally:
        await engine.dispose()

    print("Reindexación del índice RAG completada:")
    print(f"  - artículos activos indexados: {indexados}")
    print(f"  - chunks totales en la colección: {get_coleccion().count()}")
    print(f"  - directorio Chroma: {settings.CHROMA_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
