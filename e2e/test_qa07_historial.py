"""QA-07 · Historial de conversaciones (DRS §6, RF-09, API-05).

Criterio: cada interacción queda registrada con fecha/hora e intención
detectada; consultable por personal autorizado (JWT staff).
"""

import pytest

import helpers

pytestmark = pytest.mark.qa07


async def test_historial_registra_cada_interaccion_con_intent_y_fecha(
    cliente, cliente_admin
):
    """Tras una conversación, el historial trae mensajes con intent y fecha/hora."""
    chat = await helpers.crear_sesion(cliente)
    await chat.enviar(texto="hola")
    await chat.enviar(texto="¿cómo recupero mi contraseña del correo?")
    await chat.enviar(texto="gracias")

    resp = await helpers.peticion(
        cliente_admin,
        "GET",
        f"/api/chat/conversaciones/{chat.session_id}/mensajes",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    mensajes = data["mensajes"]

    assert data["total"] == len(mensajes)
    assert len(mensajes) >= 6  # bienvenida + 3 turnos de usuario + respuestas del bot

    # Toda interacción tiene fecha/hora.
    assert all(m["createdAt"] for m in mensajes), "Falta fecha/hora en algún mensaje."

    # Quedan registrados emisores usuario y bot.
    emisores = {m["emisor"] for m in mensajes}
    assert {"usuario", "bot"} <= emisores

    # Se registró la intención detectada (p. ej. el saludo o la recuperación).
    intents = {m["intent"] for m in mensajes if m["intent"]}
    assert intents, "No se registró ninguna intención."
    assert {"saludo", "recuperar_correo", "faq_general", "agradecimiento"} & intents


async def test_historial_requiere_autenticacion_de_staff(cliente):
    """Sin JWT de staff, el historial NO es accesible (401)."""
    chat = await helpers.crear_sesion(cliente)
    await chat.enviar(texto="hola")
    resp = await helpers.peticion(
        cliente, "GET", f"/api/chat/conversaciones/{chat.session_id}/mensajes"
    )
    assert resp.status_code == 401, resp.text
