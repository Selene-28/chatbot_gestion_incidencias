"""Chunking e indexación en Chroma (prd/06 §4) con embedder fake en tmp_path."""

from types import SimpleNamespace

from app.ia import indexado
from app.models import KbArticulo


def _articulo(id_: int, titulo: str, contenido: str, **kw) -> KbArticulo:  # type: ignore[no-untyped-def]
    return KbArticulo(
        id=id_,
        titulo=titulo,
        contenido=contenido,
        categoria=kw.get("categoria", "Internet/WiFi"),
        etiquetas=kw.get("etiquetas", "wifi,red"),
        activo=kw.get("activo", True),
        version=kw.get("version", 1),
    )


class _SesionStub:
    """Stub mínimo de AsyncSession para reindexar_todo (solo SELECT de artículos)."""

    def __init__(self, articulos: list[KbArticulo]) -> None:
        self._articulos = articulos

    async def execute(self, _stmt):  # type: ignore[no-untyped-def]
        articulos = self._articulos
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: articulos))


# ------------------------------------------------------------------- chunking


def test_trocear_articulo_corto_queda_completo():
    contenido = "Pasos para conectarse al WiFi del campus.\n\n1. Active el WiFi."
    assert indexado.trocear(contenido) == [contenido]


def test_trocear_vacio():
    assert indexado.trocear("   \n ") == []


def test_trocear_articulo_largo_parte_por_secciones():
    seccion = " ".join(["palabra"] * 100)
    contenido = "\n\n".join(f"## Sección {i}\n{seccion}" for i in range(8))
    chunks = indexado.trocear(contenido)

    assert len(chunks) > 1
    # ningún chunk excede el objetivo (~300 tokens ≈ 230 palabras) + solape
    for chunk in chunks:
        assert len(chunk.split()) <= 300
    # el contenido se preserva (toda sección aparece en algún chunk)
    unido = "\n\n".join(chunks)
    for i in range(8):
        assert f"## Sección {i}" in unido


def test_trocear_seccion_gigante_usa_ventana_con_solape():
    contenido = " ".join(f"palabra{i}" for i in range(700))  # sin párrafos
    chunks = indexado.trocear(contenido)

    assert len(chunks) >= 3
    # solape: el inicio de cada chunk repite palabras del anterior
    for anterior, siguiente in zip(chunks, chunks[1:], strict=False):
        assert siguiente.split()[0] in anterior.split()


# ------------------------------------------------------------ upsert / delete


async def test_indexar_articulo_con_metadatos(chroma_tmp, fake_embedder):
    articulo = _articulo(7, "Conexión WiFi", "Cómo conectarse al wifi del campus")

    n = await indexado.indexar_articulo(articulo)

    assert n == 1
    datos = indexado.get_coleccion().get(include=["metadatas"])
    assert datos["ids"] == ["7:0"]
    meta = datos["metadatas"][0]
    assert meta["articulo_id"] == 7
    assert meta["titulo"] == "Conexión WiFi"
    assert meta["categoria"] == "Internet/WiFi"
    assert meta["version"] == 1
    assert meta["activo"] is True


async def test_indexar_articulo_es_upsert(chroma_tmp, fake_embedder):
    articulo = _articulo(1, "WiFi", "Conectarse al wifi del campus")
    await indexado.indexar_articulo(articulo)
    await indexado.indexar_articulo(articulo)  # re-indexar no duplica

    assert indexado.get_coleccion().count() == 1

    articulo.contenido = "Nuevo contenido sobre la red wifi"
    articulo.version = 2
    await indexado.indexar_articulo(articulo)

    datos = indexado.get_coleccion().get(include=["metadatas", "documents"])
    assert len(datos["ids"]) == 1
    assert datos["metadatas"][0]["version"] == 2
    assert "Nuevo contenido" in datos["documents"][0]


async def test_indexar_articulo_inactivo_lo_retira(chroma_tmp, fake_embedder):
    articulo = _articulo(2, "WiFi", "Conectarse al wifi")
    await indexado.indexar_articulo(articulo)
    assert indexado.get_coleccion().count() == 1

    articulo.activo = False
    n = await indexado.indexar_articulo(articulo)

    assert n == 0
    assert indexado.get_coleccion().count() == 0


async def test_desindexar_borra_todos_los_chunks(chroma_tmp, fake_embedder):
    seccion = " ".join(["wifi"] * 100)
    largo = "\n\n".join(f"## Parte {i}\n{seccion}" for i in range(8))
    await indexado.indexar_articulo(_articulo(3, "WiFi largo", largo))
    assert indexado.get_coleccion().count() > 1

    indexado.desindexar(3)

    assert indexado.get_coleccion().count() == 0


async def test_reindexar_todo_idempotente(chroma_tmp, fake_embedder):
    articulos = [
        _articulo(1, "WiFi", "Conectarse al wifi del campus"),
        _articulo(2, "Correo", "Recuperar la contraseña del correo", etiquetas="correo"),
        _articulo(3, "Obsoleto", "Artículo desactivado", activo=False),
    ]
    sesion = _SesionStub(articulos)

    assert await indexado.reindexar_todo(sesion) == 2  # type: ignore[arg-type]
    assert indexado.get_coleccion().count() == 2

    # segunda pasada: mismo resultado, sin duplicados (idempotente)
    assert await indexado.reindexar_todo(sesion) == 2  # type: ignore[arg-type]
    assert indexado.get_coleccion().count() == 2
