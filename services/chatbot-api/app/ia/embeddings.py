"""Embeddings locales con `intfloat/multilingual-e5-small` (prd/06 §5).

- Costo cero por consulta: el modelo corre en CPU dentro del contenedor.
- E5 exige prefijos: "query: " para consultas y "passage: " para documentos.
- Singleton perezoso (la primera carga descarga/lee ~120 MB de la caché HF);
  ``encode`` corre en ``run_in_executor`` para no bloquear el event loop.
- El embedder es inyectable (``set_embedder``) para tests con vectores fake.
"""

import asyncio
import logging
import threading
from typing import Any, Protocol

logger = logging.getLogger("app.ia.embeddings")

MODELO_EMBEDDINGS_DEFAULT = "intfloat/multilingual-e5-small"

PREFIJO_CONSULTA = "query: "
PREFIJO_DOCUMENTO = "passage: "


class Embedder(Protocol):
    """Contrato mínimo: lista de textos (ya con prefijo E5) → lista de vectores."""

    def encode(self, textos: list[str]) -> list[list[float]]: ...


class EmbedderE5:
    """SentenceTransformer con carga perezosa y thread-safe."""

    def __init__(self, nombre_modelo: str = MODELO_EMBEDDINGS_DEFAULT) -> None:
        self._nombre = nombre_modelo
        self._modelo = None
        self._lock = threading.Lock()

    def _cargar(self) -> Any:
        # import perezoso: sentence-transformers/torch son pesados y solo se
        # necesitan cuando el RAG se usa de verdad (tests unitarios no los cargan)
        from sentence_transformers import SentenceTransformer

        with self._lock:
            if self._modelo is None:
                logger.info("Cargando modelo de embeddings %s ...", self._nombre)
                self._modelo = SentenceTransformer(self._nombre)
        return self._modelo

    def encode(self, textos: list[str]) -> list[list[float]]:
        """Codifica textos (con prefijo E5 ya aplicado) a vectores normalizados."""
        modelo = self._modelo or self._cargar()
        vectores = modelo.encode(textos, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectores]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Embedder singleton (E5 real salvo que un test inyecte uno fake)."""
    global _embedder
    if _embedder is None:
        _embedder = EmbedderE5()
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Inyecta un embedder alternativo (None restaura el default). Para tests."""
    global _embedder
    _embedder = embedder


async def _encode_async(textos: list[str]) -> list[list[float]]:
    """Ejecuta el encode (CPU-bound) fuera del event loop."""
    loop = asyncio.get_running_loop()
    embedder = get_embedder()
    return await loop.run_in_executor(None, embedder.encode, textos)


async def embed_consulta(texto: str) -> list[float]:
    """Vector de una consulta de usuario (prefijo E5 "query: ")."""
    vectores = await _encode_async([PREFIJO_CONSULTA + texto])
    return vectores[0]


async def embed_documentos(textos: list[str]) -> list[list[float]]:
    """Vectores de chunks de artículos (prefijo E5 "passage: ")."""
    if not textos:
        return []
    return await _encode_async([PREFIJO_DOCUMENTO + t for t in textos])
