"""QA-03 · Preguntas frecuentes (FAQ) (DRS §6).

Criterio: identifica la intención; consulta la base de conocimiento; la
respuesta corresponde a la consulta; si no existe respuesta, informa la
limitación y ofrece registrar incidencia.

NOTA DE DEGRADACIÓN: sin ANTHROPIC_API_KEY real, el motor RAG degrada a la
recuperación textual (FULLTEXT) de MySQL (prd/06 §6). La respuesta sigue
proviniendo del artículo correcto de la KB: verificamos ``meta.fuentesKb`` y el
contenido, no una redacción concreta del LLM.
"""

import pytest

import helpers

pytestmark = pytest.mark.qa03


async def test_faq_cubierta_responde_desde_la_kb(cliente):
    """Consulta cubierta → respuesta anclada a un artículo (meta.fuentesKb)."""
    chat = await helpers.crear_sesion(cliente)
    r = await chat.enviar(texto="¿cómo recupero mi contraseña del correo?")

    fuentes = r.buscar_meta("fuentesKb")
    assert fuentes, f"Se esperaba meta.fuentesKb con el artículo fuente. Meta: {r.metas()}"
    assert isinstance(fuentes, list) and len(fuentes) >= 1

    intent = r.buscar_meta("intent")
    assert intent in {"recuperar_correo", "faq_general"}
    # El contenido corresponde a la consulta (pasos de recuperación de contraseña).
    texto = helpers.normalizar(r.texto)
    assert "contrasena" in texto
    assert "olvido" in texto or "restablec" in texto or "recuper" in texto


async def test_faq_fuera_de_cobertura_informa_limitacion_y_ofrece_registrar(cliente):
    """Sin artículo relevante → limitación QA-03 + opción de registrar incidencia.

    Se usa el mini-flujo FAQ (botón «Preguntas frecuentes») con una consulta
    claramente fuera del dominio del CTIC. Con el umbral de similitud calibrado
    (RAG_UMBRAL_SIMILITUD, config del chatbot-api) el motor no fuerza un artículo
    irrelevante: informa la limitación y ofrece registrar la incidencia (RN-08).
    """
    chat = await helpers.crear_sesion(cliente)
    await chat.enviar(opcion="faq_general")  # pide la consulta
    r = await chat.enviar(
        texto="receta de ceviche de pescado con limon, cebolla y camote"
    )

    texto = helpers.normalizar(r.texto)
    assert "no tengo informacion" in texto  # limitación oficial (KB_SIN_RESPUESTA)
    assert "registrar_incidencia" in r.ids_opciones  # ofrece registrar incidencia


async def test_faq_info_ctic_responde_desde_la_kb(cliente):
    """Información del CTIC (horario/contacto) se responde desde la KB."""
    chat = await helpers.crear_sesion(cliente)
    r = await chat.enviar(opcion="info_ctic")
    fuentes = r.buscar_meta("fuentesKb")
    assert fuentes, f"info_ctic debería anclarse a un artículo. Meta: {r.metas()}"
