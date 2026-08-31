"""QA-11 · Flujo completo (DRS §6) — criterio GLOBAL.

Criterio: el 100 % de los happy paths termina en la acción correcta sin colapsar
el backend (se verifica con suite E2E automatizada).

Se ejecutan de principio a fin los 5 happy paths principales: registrar,
consultar, FAQ, diagnóstico resuelto y escalar. Cada interacción por chat pasa
por ``chat.enviar`` (que exige HTTP 200; cualquier 5xx haría fallar el paso), y
las llamadas directas al ticket-service verifican explícitamente 2xx.
"""

import pytest

import helpers

pytestmark = pytest.mark.qa11


def _sin_5xx(*respuestas):
    for r in respuestas:
        assert r.status_code < 500, f"El backend respondió {r.status_code}: {r.text[:200]}"
        assert 200 <= r.status_code < 300, f"Se esperaba 2xx, llegó {r.status_code}"


async def test_happy_path_registrar(cliente):
    """Happy path 1: registrar incidencia → termina con un código de ticket."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)
    assert helpers.PATRON_TICKET.fullmatch(ticket_id)
    resp = await helpers.consultar_ticket(cliente, ticket_id, datos["correo"])
    _sin_5xx(resp)


async def test_happy_path_consultar(cliente):
    """Happy path 2: consultar estado → termina mostrando el detalle del ticket."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    r_modo = await chat.enviar(opcion="consultar_estado")
    await chat.enviar(opcion=r_modo.elegir("Por número de ticket"))
    detalle = await chat.enviar(texto=ticket_id)
    assert ticket_id in detalle.texto
    assert "Estado" in detalle.texto


async def test_happy_path_faq(cliente):
    """Happy path 3: FAQ → termina con una respuesta anclada a la KB."""
    chat = await helpers.crear_sesion(cliente)
    r = await chat.enviar(texto="¿cómo recupero mi contraseña del correo?")
    assert r.buscar_meta("fuentesKb")


async def test_happy_path_diagnostico_resuelto(cliente):
    """Happy path 4: diagnóstico → termina en cierre feliz cuando se resuelve."""
    chat = await helpers.crear_sesion(cliente)
    inicio = await chat.enviar(texto="no tengo internet")
    pasos = await chat.enviar(opcion=inicio.elegir("Cable"))
    cierre = await chat.enviar(opcion=pasos.elegir("Sí, se resolvió"))
    assert "resolvió" in cierre.texto.lower() or "resuelto" in cierre.texto.lower()


async def test_happy_path_escalar(cliente):
    """Happy path 5: escalar → termina con el ticket en estado Escalado."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    r = await chat.enviar(texto="deseo escalar mi incidencia")
    assert "motivo" in helpers.normalizar(r.texto)
    confirm = await chat.enviar(texto="El problema persiste y requiere a un técnico del CTIC.")
    assert "escalado" in helpers.normalizar(confirm.texto)

    resp = await helpers.consultar_ticket(cliente, ticket_id, datos["correo"])
    _sin_5xx(resp)
    assert resp.json()["data"]["estado"] == "Escalado"
