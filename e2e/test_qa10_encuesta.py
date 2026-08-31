"""QA-10 · Encuesta de satisfacción (DRS §6, RF-08, RN-04, API-06).

Criterio: se solicita al finalizar; acepta valoración 1–5; queda almacenada
para estadísticas. Además, una segunda encuesta para la misma atención → 409.
"""

import pytest

import helpers

pytestmark = pytest.mark.qa10


async def test_encuesta_por_chat_al_finalizar_se_almacena(cliente):
    """Finalizar una atención (F-08) → calificar 1–5 → queda almacenada."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    # Disparar la encuesta (intent finalizar) tras una atención con ticket.
    r_encuesta = await chat.enviar(texto="finalizar")
    assert "encuesta" in r_encuesta.tipos, f"No se ofreció la encuesta: {r_encuesta.textos}"
    assert "calificar" in helpers.normalizar(r_encuesta.texto)
    assert "calif_5" in r_encuesta.ids_opciones  # botones ⭐1–⭐5

    # Calificar 5 y omitir el comentario.
    r_coment = await chat.enviar(opcion="calif_5")
    cierre = await chat.enviar(opcion=r_coment.elegir("Omitir"))
    assert "gracias" in helpers.normalizar(cierre.texto)

    # Quedó almacenada: una segunda encuesta para el mismo ticket → 409 (RN-04).
    repetida = await helpers.registrar_encuesta(cliente, calificacion=3, ticket_id=ticket_id)
    assert repetida.status_code == 409, repetida.text


async def test_api06_acepta_1_a_5_y_rechaza_duplicada(cliente):
    """API-06 acepta calificación 1–5 y una segunda para la misma atención → 409."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    primera = await helpers.registrar_encuesta(
        cliente, calificacion=4, ticket_id=ticket_id, comentario="Atención clara."
    )
    assert primera.status_code == 201, primera.text

    segunda = await helpers.registrar_encuesta(cliente, calificacion=2, ticket_id=ticket_id)
    assert segunda.status_code == 409, segunda.text


async def test_api06_rechaza_calificacion_fuera_de_rango(cliente):
    """API-06 valida el rango 1–5: una calificación de 6 se rechaza (400)."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    resp = await helpers.registrar_encuesta(cliente, calificacion=6, ticket_id=ticket_id)
    assert resp.status_code == 400, resp.text
