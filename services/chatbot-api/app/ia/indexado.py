"""Indexación de `kb_articulos` en ChromaDB (prd/06 §4).

- Colección "kb" persistente en ``settings.CHROMA_DIR`` con métrica coseno.
- Chunking: artículos ≤ 400 tokens se indexan completos; mayores se dividen por
  secciones de ~300 tokens con solape de 50 (aprox. tokens = palabras * 1.3).
- Metadatos por chunk: articulo_id, titulo, categoria, version, activo.
- ``indexar_articulo`` es un upsert (borra los chunks viejos del artículo);
  ``reindexar_todo`` es idempotente (reconstrucción completa, arranque inicial
  o cambio de modelo de embeddings — comando: ``python -m app.scripts.reindex``).
"""

import logging
import re
from typing import Any

import chromadb
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ia import embeddings
from app.models import KbArticulo

logger = logging.getLogger("app.ia.indexado")

# prd/06 §4 pedía la colección "kb", pero Chroma exige nombres de 3+ caracteres;
# se usa "kb_articulos" (mismo rol, desviación documentada).
COLECCION_KB = "kb_articulos"

# prd/06 §4 — límites de chunking (en "tokens" aproximados)
MAX_TOKENS_ARTICULO_COMPLETO = 400
TOKENS_POR_CHUNK = 300
TOKENS_SOLAPE = 50
_TOKENS_POR_PALABRA = 1.3

_cliente: chromadb.ClientAPI | None = None


def reset_chroma() -> None:
    """Olvida el cliente Chroma (tests con CHROMA_DIR temporal)."""
    global _cliente
    _cliente = None


def get_coleccion() -> chromadb.Collection:
    """Colección "kb" (coseno) sobre el directorio persistente configurado."""
    global _cliente
    if _cliente is None:
        _cliente = chromadb.PersistentClient(path=get_settings().CHROMA_DIR)
    return _cliente.get_or_create_collection(COLECCION_KB, metadata={"hnsw:space": "cosine"})


# ------------------------------------------------------------------ chunking


def _aprox_tokens(texto: str) -> int:
    return int(len(texto.split()) * _TOKENS_POR_PALABRA)


def _secciones(contenido: str) -> list[str]:
    """Parte por encabezados markdown y párrafos (unidades naturales)."""
    # corta antes de cada encabezado y en líneas en blanco
    piezas = re.split(r"\n(?=#{1,6}\s)|\n\s*\n", contenido)
    return [p.strip() for p in piezas if p.strip()]


def _partir_por_palabras(texto: str, max_palabras: int, solape_palabras: int) -> list[str]:
    """Ventana deslizante por palabras para secciones que exceden el objetivo."""
    palabras = texto.split()
    trozos: list[str] = []
    paso = max(1, max_palabras - solape_palabras)
    for inicio in range(0, len(palabras), paso):
        trozo = " ".join(palabras[inicio : inicio + max_palabras])
        if trozo:
            trozos.append(trozo)
        if inicio + max_palabras >= len(palabras):
            break
    return trozos


def trocear(contenido: str) -> list[str]:
    """Chunks del artículo según prd/06 §4 (≤400 completos; ~300 con solape 50)."""
    contenido = contenido.strip()
    if not contenido:
        return []
    if _aprox_tokens(contenido) <= MAX_TOKENS_ARTICULO_COMPLETO:
        return [contenido]

    max_palabras = int(TOKENS_POR_CHUNK / _TOKENS_POR_PALABRA)  # ≈ 230
    solape_palabras = int(TOKENS_SOLAPE / _TOKENS_POR_PALABRA)  # ≈ 38

    chunks: list[str] = []
    actual: list[str] = []
    palabras_actual = 0
    for seccion in _secciones(contenido):
        n = len(seccion.split())
        if n > max_palabras:
            if actual:
                chunks.append("\n\n".join(actual))
                actual, palabras_actual = [], 0
            chunks.extend(_partir_por_palabras(seccion, max_palabras, solape_palabras))
            continue
        if palabras_actual + n > max_palabras and actual:
            chunks.append("\n\n".join(actual))
            # solape: arrastra la última sección del chunk anterior
            actual = actual[-1:]
            palabras_actual = len(actual[0].split()) if actual else 0
        actual.append(seccion)
        palabras_actual += n
    if actual:
        chunks.append("\n\n".join(actual))
    return chunks


# ---------------------------------------------------------------- operaciones


def _metadatos(articulo: KbArticulo) -> dict[str, Any]:
    return {
        "articulo_id": int(articulo.id),
        "titulo": articulo.titulo,
        "categoria": articulo.categoria,
        "version": int(articulo.version or 1),
        "activo": bool(articulo.activo),
        # extra sobre prd/06 §4: permite el re-ranking por etiquetas sin ir a MySQL
        "etiquetas": articulo.etiquetas or "",
    }


async def indexar_articulo(articulo: KbArticulo) -> int:
    """Upsert de un artículo: borra sus chunks viejos e indexa los nuevos.

    Devuelve la cantidad de chunks indexados (0 si el artículo está inactivo:
    los inactivos se retiran del índice, prd/06 §4).
    """
    coleccion = get_coleccion()
    coleccion.delete(where={"articulo_id": int(articulo.id)})
    if not articulo.activo:
        return 0

    chunks = trocear(articulo.contenido)
    if not chunks:
        return 0
    # el título acompaña a cada chunk: mejora el recall de consultas cortas
    documentos = [f"{articulo.titulo}\n{chunk}" for chunk in chunks]
    vectores = await embeddings.embed_documentos(documentos)
    coleccion.add(
        ids=[f"{articulo.id}:{i}" for i in range(len(chunks))],
        documents=documentos,
        embeddings=vectores,  # type: ignore[arg-type]
        metadatas=[_metadatos(articulo) for _ in chunks],
    )
    return len(chunks)


def desindexar(articulo_id: int) -> None:
    """Elimina todos los chunks de un artículo (borrado/desactivación, RF-12)."""
    get_coleccion().delete(where={"articulo_id": int(articulo_id)})


async def reindexar_todo(session: AsyncSession) -> int:
    """Reconstruye el índice completo desde MySQL. Idempotente.

    Devuelve la cantidad de artículos ACTIVOS indexados.
    """
    articulos = (await session.execute(select(KbArticulo))).scalars().all()
    indexados = 0
    total_chunks = 0
    for articulo in articulos:
        chunks = await indexar_articulo(articulo)
        if chunks:
            indexados += 1
            total_chunks += chunks
    logger.info(
        "Reindexación completa: %d artículos activos, %d chunks (de %d artículos totales)",
        indexados,
        total_chunks,
        len(articulos),
    )
    return indexados
