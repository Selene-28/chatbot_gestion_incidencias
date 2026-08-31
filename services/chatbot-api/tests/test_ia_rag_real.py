"""Marker `rag`: reindexación y recall con el modelo E5 REAL (sin LLM ni MySQL).

Autoskip si sentence-transformers no está instalado. La primera ejecución
descarga `intfloat/multilingual-e5-small` (~120 MB) a la caché HF local.

Ejecutar con: pytest -m rag
"""

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.ia import embeddings, indexado, rag
from app.models import KbArticulo

pytest.importorskip("sentence_transformers", reason="sentence-transformers no instalado")

pytestmark = pytest.mark.rag


def _articulo(id_: int, titulo: str, contenido: str, categoria: str, etiquetas: str) -> KbArticulo:
    return KbArticulo(
        id=id_,
        titulo=titulo,
        contenido=contenido,
        categoria=categoria,
        etiquetas=etiquetas,
        activo=True,
        version=1,
    )


ARTICULOS = [
    _articulo(
        1,
        "Conexión a la red WiFi de la UNAC",
        "Para conectarse a la red inalámbrica del campus seleccione la red "
        "UNAC-CAMPUS, ingrese su correo institucional y la contraseña del correo. "
        "Si aparece un portal cautivo, acepte los términos de uso.",
        "Internet/WiFi",
        "wifi,internet,red,conexión",
    ),
    _articulo(
        2,
        "Recuperación de contraseña del correo institucional",
        "Si olvidó la contraseña de su correo @unac.edu.pe ingrese al portal, "
        "haga clic en ¿Olvidó su contraseña? y siga el enlace que llega a su "
        "correo personal alterno para restablecerla.",
        "Correo Institucional",
        "correo,contraseña,recuperar,restablecer",
    ),
    _articulo(
        3,
        "MATLAB con licencia campus de la UNAC",
        "La universidad dispone de licencia campus de MATLAB. Cree una cuenta de "
        "MathWorks con su correo institucional, descargue el instalador y active "
        "la licencia Academic Total Headcount.",
        "Software Institucional",
        "matlab,licencia,software,instalación",
    ),
]


class _SesionStub:
    async def execute(self, _stmt):  # type: ignore[no-untyped-def]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ARTICULOS))


@pytest.fixture()
def embedder_real():  # type: ignore[no-untyped-def]
    """Garantiza el embedder E5 real (por si otro test dejó un fake inyectado)."""
    embeddings.set_embedder(None)
    yield
    embeddings.set_embedder(None)


async def test_reindexar_todo_y_recall_con_modelo_real(chroma_tmp, embedder_real):
    indexados = await indexado.reindexar_todo(_SesionStub())  # type: ignore[arg-type]
    assert indexados == 3
    assert indexado.get_coleccion().count() == 3

    # idempotencia con el modelo real
    assert await indexado.reindexar_todo(_SesionStub()) == 3  # type: ignore[arg-type]
    assert indexado.get_coleccion().count() == 3

    # recall de una consulta obvia: el artículo de WiFi debe ganar sobre el umbral
    umbral = get_settings().RAG_UMBRAL_SIMILITUD
    candidatos = await rag._recuperar("¿cómo me conecto al wifi del campus?")
    assert candidatos, "sin candidatos sobre el umbral para una consulta obvia"
    assert candidatos[0].articulo_id == 1
    assert candidatos[0].similitud >= umbral

    # otra consulta obvia hacia otro artículo (no siempre el mismo ganador)
    candidatos = await rag._recuperar("olvidé la contraseña de mi correo institucional")
    assert candidatos
    assert candidatos[0].articulo_id == 2
