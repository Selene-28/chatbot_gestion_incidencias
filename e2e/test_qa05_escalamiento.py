"""QA-05 · Escalamiento (DRS §6, flujo F-06 / API-03).

Criterio: el usuario puede solicitarlo; se registra el motivo; el ticket pasa a
``Escalado``; el personal técnico lo visualiza en el panel.
"""

import pytest

import helpers

pytestmark = pytest.mark.qa05


async def test_escalar_por_chat_pasa_a_escalado_y_es_visible_en_el_panel(
    cliente, cliente_admin
):
    """Registrar → escalar por chat → estado Escalado (API-02) → visible en panel."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    # F-06 por chat: tras registrar, la sesión conoce el último ticket y el correo,
    # así que el bot pide directamente el motivo del escalamiento.
    r = await chat.enviar(texto="quiero escalar mi incidencia")
    assert "motivo" in helpers.normalizar(r.texto)
    confirm = await chat.enviar(
        texto="El problema persiste y necesito atención especializada del CTIC."
    )
    assert "escalado al personal" in helpers.normalizar(confirm.texto)

    # El estado en la BD es «Escalado» (API-02).
    resp = await helpers.consultar_ticket(cliente, ticket_id, datos["correo"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["estado"] == "Escalado"

    # El staff lo ve en la cola de escalados del panel (filtrando por mi ticket).
    panel = await helpers.peticion(
        cliente_admin, "GET", "/api/panel/tickets", params={"estado": "Escalado"}
    )
    assert panel.status_code == 200, panel.text
    codigos = {t["ticketId"] for t in panel.json()["data"]["items"]}
    assert ticket_id in codigos, f"{ticket_id} no aparece entre los escalados del panel."


async def test_escalar_registra_el_motivo_en_el_historial(cliente, cliente_admin):
    """El motivo del escalamiento queda registrado en el historial del ticket."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    motivo = "Diagnostico agotado sin solucion; requiere revision de un tecnico."
    resp = await helpers.escalar_ticket(cliente, ticket_id, motivo, datos["correo"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["estado"] == "Escalado"

    detalle = await helpers.peticion(
        cliente_admin, "GET", f"/api/panel/tickets/{ticket_id}"
    )
    assert detalle.status_code == 200, detalle.text
    historial = detalle.json()["data"]["historial"]
    comentarios = " ".join(str(ev.get("comentario") or "") for ev in historial)
    estados = {ev.get("estadoNuevo") for ev in historial}
    assert "Escalado" in estados
    assert motivo[:20] in comentarios
