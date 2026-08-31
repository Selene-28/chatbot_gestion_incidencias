"""QA-01 · Registro de incidencias (DRS §6).

Criterio: captura todos los datos obligatorios; valida completitud; genera
ticket único; persiste en BD; confirma al usuario con el código.

Se conduce el flujo F-02 completo por chat y se verifica contra la BD vía el
contrato API-02 del ticket-service.
"""

import pytest

import helpers

pytestmark = pytest.mark.qa01


async def test_registro_por_chat_genera_ticket_y_persiste(cliente):
    """F-02 de principio a fin → código INC-AAAA-NNNN + persistencia (API-02)."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)

    ticket_id = await helpers.recorrer_registro(chat, datos)

    # Código único con el formato del DRS (RN-01).
    assert helpers.PATRON_TICKET.fullmatch(ticket_id), (
        f"El código {ticket_id!r} no cumple el formato INC-AAAA-NNNN."
    )

    # La incidencia EXISTE en la BD con los datos capturados (API-02).
    resp = await helpers.consultar_ticket(cliente, ticket_id, datos["correo"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["ticketId"] == ticket_id
    assert data["categoria"] == datos["categoria"]
    assert data["estado"] == "Registrado"
    assert data["fechaRegistro"]  # se persistió una fecha de registro


async def test_confirmacion_al_usuario_incluye_el_codigo(cliente):
    """El bot confirma el registro al usuario citando el código del ticket."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)

    await chat.enviar(opcion="registrar_incidencia")
    await chat.enviar(texto=datos["nombre"])
    r_area = await chat.enviar(texto=datos["correo"])
    r_cat = await chat.enviar(opcion=r_area.elegir(datos["area"]))
    await chat.enviar(opcion=r_cat.elegir(datos["categoria"]))
    r_prio = await chat.enviar(texto=datos["descripcion"])
    r_adj = await chat.enviar(opcion=r_prio.elegir(datos["prioridad"]))
    r_conf = await chat.enviar(opcion=r_adj.elegir("omitir"))
    final = await chat.enviar(opcion=r_conf.elegir("confirmar"))

    assert final.ticket_id is not None
    assert "registrada correctamente" in final.texto.lower()
    assert final.ticket_id in final.texto  # el código aparece en el mensaje


async def test_cada_registro_genera_un_codigo_distinto(cliente):
    """Dos registros producen códigos distintos (correlativo transaccional)."""
    chat1 = await helpers.crear_sesion(cliente)
    chat2 = await helpers.crear_sesion(cliente)
    t1 = await helpers.recorrer_registro(chat1, helpers.datos_incidencia())
    t2 = await helpers.recorrer_registro(chat2, helpers.datos_incidencia())
    assert t1 != t2
