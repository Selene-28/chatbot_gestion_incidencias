"""Pipeline RAG (prd/06 §3) y su degradación (§6), con LLM y embedder fake."""

import pytest

from app.dialogo import textos
from app.dialogo.flujos import faq
from app.ia import indexado, llm, rag
from app.models import KbArticulo

# frases clave de las 5 reglas del prompt estricto (prd/06 §3, literal)
REGLAS_ESPERADAS = [
    "ÚNICAMENTE con la información de los ARTÍCULOS",
    "paso a paso numeradas",
    "Nunca reveles contraseñas",
    "No atiendas temas ajenos a los servicios del CTIC",
    "Máximo 150 palabras",
]


def _articulo_wifi() -> KbArticulo:
    return KbArticulo(
        id=11,
        titulo="Conexión a la red WiFi de la UNAC",
        contenido="Para conectarse al wifi del campus use su correo institucional.",
        categoria="Internet/WiFi",
        etiquetas="wifi,red,internet",
        activo=True,
        version=1,
    )


@pytest.fixture()
def llm_mock(monkeypatch):  # type: ignore[no-untyped-def]
    """LLM 'disponible' con generar_stream fake que captura los prompts."""
    capturado: dict[str, str] = {}

    async def _fake_stream(system: str, user: str, **_kw):  # type: ignore[no-untyped-def]
        capturado["system"] = system
        capturado["user"] = user
        yield "Respuesta redactada "
        yield "y anclada a los artículos."

    monkeypatch.setattr(llm, "llm_disponible", lambda: True)
    monkeypatch.setattr(llm, "generar_stream", _fake_stream)
    return capturado


# --------------------------------------------------------------------- via=rag


async def test_rag_genera_con_prompt_estricto(chroma_tmp, fake_embedder, llm_mock):
    await indexado.indexar_articulo(_articulo_wifi())

    respuesta = await rag.responder_faq(
        None, "no puedo usar el wifi del campus", ["hola", "tengo un problema"]
    )

    assert respuesta.via == "rag"
    assert respuesta.texto == "Respuesta redactada y anclada a los artículos."
    assert respuesta.fuentes_kb == [11]
    # el system es el prompt LITERAL de prd/06 §3 con las 5 reglas
    for regla in REGLAS_ESPERADAS:
        assert regla in llm_mock["system"], f"falta la regla: {regla}"
    assert "Asistente Virtual del CTIC" in llm_mock["system"]
    # los artículos y el historial van en el user (prompt caching)
    assert "ARTÍCULOS" in llm_mock["user"]
    assert "Conexión a la red WiFi de la UNAC" in llm_mock["user"]
    assert "tengo un problema" in llm_mock["user"]
    assert "no puedo usar el wifi del campus" in llm_mock["user"]


async def test_rag_umbral_sin_evidencia_es_sin_respuesta(chroma_tmp, fake_embedder, llm_mock):
    await indexado.indexar_articulo(_articulo_wifi())

    respuesta = await rag.responder_faq(None, "trámite de beca alimentaria", [])

    assert respuesta.via == "sin_respuesta"
    assert respuesta.fuentes_kb == []
    assert "user" not in llm_mock  # bajo el umbral NO se llama al LLM (ahorro)


async def test_rag_indice_vacio_degrada_a_fulltext(
    chroma_tmp, fake_embedder, llm_mock, monkeypatch
):
    async def _fake_fulltext(session, consulta):  # type: ignore[no-untyped-def]
        return {"id": 5, "titulo": "WiFi", "contenido": "Contenido textual.", "etiquetas": ""}

    monkeypatch.setattr(rag, "buscar_articulo", _fake_fulltext)

    respuesta = await rag.responder_faq(None, "wifi", [])

    assert respuesta.via == "fulltext"
    assert respuesta.fuentes_kb == [5]


# ------------------------------------------------------------ degradación §6


async def test_sin_llm_degrada_a_fulltext_con_aviso(chroma_tmp, fake_embedder, monkeypatch):
    async def _fake_fulltext(session, consulta):  # type: ignore[no-untyped-def]
        return {
            "id": 3,
            "titulo": "WiFi",
            "contenido": "Pasos para conectarse al WiFi.",
            "etiquetas": "wifi",
        }

    monkeypatch.setattr(rag, "buscar_articulo", _fake_fulltext)
    assert llm.llm_disponible() is False  # sin key en el entorno de test

    respuesta = await rag.responder_faq(None, "wifi campus", [])

    assert respuesta.via == "fulltext"
    assert respuesta.texto.startswith("Pasos para conectarse al WiFi.")
    assert "respuesta tomada de nuestra base de conocimiento" in respuesta.texto
    assert respuesta.fuentes_kb == [3]


async def test_sin_llm_y_sin_match_es_sin_respuesta(chroma_tmp, fake_embedder, monkeypatch):
    async def _fake_fulltext(session, consulta):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(rag, "buscar_articulo", _fake_fulltext)

    respuesta = await rag.responder_faq(None, "zzkqx wwyyzz", [])

    assert respuesta.via == "sin_respuesta"
    assert respuesta.texto == ""


async def test_error_del_llm_a_mitad_degrada_a_semantico(chroma_tmp, fake_embedder, monkeypatch):
    # Si el LLM falla PERO la recuperación vectorial ya encontró el artículo,
    # se devuelve ese artículo textualmente (via=semantico), que sigue siendo
    # una respuesta correcta — mejor que caer al respaldo léxico FULLTEXT.
    async def _stream_roto(system: str, user: str, **_kw):  # type: ignore[no-untyped-def]
        raise llm.LlmNoDisponible("simulado")
        yield  # pragma: no cover

    monkeypatch.setattr(llm, "llm_disponible", lambda: True)
    monkeypatch.setattr(llm, "generar_stream", _stream_roto)
    await indexado.indexar_articulo(_articulo_wifi())

    # session=None: _responder_semantico degrada al fragmento recuperado sin BD
    respuesta = await rag.responder_faq(None, "wifi del campus", [])

    assert respuesta.via == "semantico"
    assert respuesta.fuentes_kb == [_articulo_wifi().id]


# ------------------------------------------- contrato del flujo FAQ (mensajes)


async def test_faq_mantiene_contrato_con_respuesta(monkeypatch):
    async def _fake_rag(session, consulta, historial):  # type: ignore[no-untyped-def]
        return rag.RespuestaRag(texto="Texto final.", fuentes_kb=[4, 8], via="rag")

    monkeypatch.setattr(rag, "responder_faq", _fake_rag)

    mensajes = await faq.responder_faq(None, "consulta", "faq_general", 0.9)

    assert len(mensajes) == 1
    assert mensajes[0].texto == "Texto final."
    assert mensajes[0].meta == {
        "intent": "faq_general",
        "confianza": 0.9,
        "fuentesKb": [4, 8],
        "via": "rag",
    }


async def test_faq_sin_respuesta_muestra_limitacion(monkeypatch):
    async def _fake_rag(session, consulta, historial):  # type: ignore[no-untyped-def]
        return rag.RespuestaRag(texto="", via="sin_respuesta")

    monkeypatch.setattr(rag, "responder_faq", _fake_rag)

    mensajes = await faq.responder_faq(None, "algo sin cobertura", "faq_general", 0.8)

    assert len(mensajes) == 1
    assert mensajes[0].texto == textos.KB_SIN_RESPUESTA
    assert [o.id for o in mensajes[0].opciones] == ["registrar_incidencia", "menu"]
    assert mensajes[0].meta["via"] == "sin_respuesta"
