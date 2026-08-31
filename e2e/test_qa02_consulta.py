"""QA-02 · Consulta de estado (DRS §6).

Criterio: por nº de ticket; muestra estado actual, fecha de registro y técnico
asignado (si existe); la información coincide con la BD.

Se registra un ticket, se consulta por chat (F-03, por código) y por el
contrato directo API-02, y se comprueba que ambos coinciden.
"""

import pytest

import helpers

pytestmark = pytest.mark.qa02


async def test_consulta_por_codigo_por_chat_y_api_coinciden(cliente):
    """F-03 por código y API-02 devuelven el mismo estado y fecha de registro."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    # Fuente de verdad: API-02 directo contra el ticket-service.
    resp = await helpers.consultar_ticket(cliente, ticket_id, datos["correo"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    estado_bd = data["estado"]

    # Consulta por chat (F-03): la sesión ya está identificada tras registrar.
    r_modo = await chat.enviar(opcion="consultar_estado")
    r_codigo = await chat.enviar(opcion=r_modo.elegir("Por número de ticket"))
    assert "INC-AAAA-NNNN" in r_codigo.texto  # pide el código
    detalle = await chat.enviar(texto=ticket_id)

    texto = detalle.texto
    assert ticket_id in texto
    assert estado_bd in texto  # el estado coincide con la BD
    assert datos["categoria"] in texto
    assert "Fecha de registro" in texto
    assert data["fechaRegistro"] in texto  # la fecha coincide con la BD


async def test_consulta_muestra_tecnico_cuando_no_asignado(cliente):
    """Sin técnico asignado, la consulta lo refleja explícitamente."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    resp = await helpers.consultar_ticket(cliente, ticket_id, datos["correo"])
    assert resp.json()["data"]["tecnico"] is None

    r_modo = await chat.enviar(opcion="consultar_estado")
    await chat.enviar(opcion=r_modo.elegir("Por número de ticket"))
    detalle = await chat.enviar(texto=ticket_id)
    assert "Técnico asignado" in detalle.texto
