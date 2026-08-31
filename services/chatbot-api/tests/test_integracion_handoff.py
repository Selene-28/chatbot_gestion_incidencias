"""Integración (MySQL): ciclo completo de handoff F-07 y expiración (RN-09).

Cubre: solicitud → PAUSED → cola con últimos 20 → atender → mensaje del agente
persiste → el usuario responde durante PAUSED sin respuesta del bot → cerrar →
ACTIVE → encuesta ofrecida; y la expiración a los 10 min con reloj retro-datado.
"""

from typing import Any

import pytest
from sqlalchemy import text as sql_text

from app.dialogo import textos
from tests.conftest import token_staff

pytestmark = pytest.mark.integration

STAFF = {"panel_token": token_staff("tecnico", sub=5)}


async def _crear_sesion(api_client) -> tuple[str, dict[str, str]]:
    r = await api_client.post("/api/chat/sesiones", json={"canal": "web_widget"})
    data = r.json()["data"]
    return data["sessionId"], {"X-Session-Token": data["sessionToken"]}


async def _enviar(api_client, session_id, headers, **campos: Any) -> dict[str, Any]:
    r = await api_client.post(
        "/api/chat/mensajes", json={"sessionId": session_id, **campos}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_ciclo_handoff_completo(api_client, fake_tickets, sesion):
    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, texto="hola")

    # 1) solicitud de handoff → PAUSED (RN-05)
    r = await api_client.post(
        "/api/chat/handoff", json={"sessionId": session_id}, headers=headers
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["estadoBot"] == "PAUSED"
    assert data["mensaje"] == textos.TRANSICION_HANDOFF

    # 2) cola de handoffs (staff) con los últimos mensajes
    r = await api_client.get("/api/chat/handoffs?estado=pendiente", cookies=STAFF)
    assert r.status_code == 200
    cola = r.json()["data"]
    item = next(h for h in cola["items"] if h["sessionId"] == session_id)
    assert item["estado"] == "pendiente"
    assert item["motivo"] == "solicitud_usuario"
    assert len(item["ultimosMensajes"]) >= 1
    handoff_id = item["id"]

    # el usuario escribe DURANTE el handoff: se persiste como 'usuario', sin bot
    await _enviar(api_client, session_id, headers, texto="¿alguien me atiende?")
    # el respaldo de polling del panel lo ve como 'usuario' (RN-05: sin bot detrás)
    r = await api_client.get(f"/api/chat/handoffs/{handoff_id}/mensajes?desde=0", cookies=STAFF)
    items = r.json()["data"]["items"]
    assert ("usuario", "¿alguien me atiende?") in [(m["emisor"], m["contenido"]) for m in items]
    assert items[-1]["emisor"] == "usuario"  # el bot no responde durante el handoff

    # 3) atender
    r = await api_client.post(f"/api/chat/handoffs/{handoff_id}/atender", cookies=STAFF)
    assert r.status_code == 200
    assert r.json()["data"]["estado"] == "atendido"

    # 4) mensaje del agente → persiste como 'agente'
    r = await api_client.post(
        f"/api/chat/handoffs/{handoff_id}/mensajes",
        json={"texto": "Hola, soy del CTIC, reviso tu caso."},
        cookies=STAFF,
    )
    assert r.status_code == 200 and r.json()["data"]["ok"] is True

    # 5) polling del panel: ve los mensajes del usuario y del agente
    r = await api_client.get(f"/api/chat/handoffs/{handoff_id}/mensajes?desde=0", cookies=STAFF)
    poll = r.json()["data"]
    emisores = {m["emisor"] for m in poll["items"]}
    assert "usuario" in emisores and "agente" in emisores
    assert poll["ultimoId"] == poll["items"][-1]["id"]

    # 6) cerrar → ACTIVE (RN-06) + encuesta ofrecida
    r = await api_client.post(f"/api/chat/handoffs/{handoff_id}/cerrar", cookies=STAFF)
    assert r.status_code == 200 and r.json()["data"]["estado"] == "cerrado"
    estado_bot = (
        await sesion.execute(
            sql_text("SELECT estado_bot FROM conversaciones WHERE codigo = :c"),
            {"c": session_id},
        )
    ).scalar_one()
    assert estado_bot == "ACTIVE"  # RN-06

    # el usuario ahora califica: el flujo de encuesta (F-08) ya está activo
    data = await _enviar(api_client, session_id, headers, opcionId="calif_5")
    assert "comentario" in data["mensajes"][0]["texto"].lower()
    data = await _enviar(api_client, session_id, headers, opcionId="omitir")
    assert data["mensajes"][-1]["texto"] == textos.DESPEDIDA
    assert fake_tickets.encuestas[0]["calificacion"] == 5


async def test_atender_handoff_cerrado_devuelve_409(api_client, sesion):
    session_id, headers = await _crear_sesion(api_client)
    await api_client.post("/api/chat/handoff", json={"sessionId": session_id}, headers=headers)
    r = await api_client.get("/api/chat/handoffs?estado=pendiente", cookies=STAFF)
    hid = next(h for h in r.json()["data"]["items"] if h["sessionId"] == session_id)["id"]

    await api_client.post(f"/api/chat/handoffs/{hid}/atender", cookies=STAFF)
    await api_client.post(f"/api/chat/handoffs/{hid}/cerrar", cookies=STAFF)
    # ya cerrado → 409
    r = await api_client.post(f"/api/chat/handoffs/{hid}/atender", cookies=STAFF)
    assert r.status_code == 409


async def test_handoffs_requiere_staff(api_client):
    r = await api_client.get("/api/chat/handoffs")
    assert r.status_code == 401


async def test_expiracion_handoff_pendiente(api_client, sesion):
    from app.services.sesiones import expirar_handoffs_pendientes

    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, texto="hola")
    await api_client.post("/api/chat/handoff", json={"sessionId": session_id}, headers=headers)

    # reloj simulado: el handoff se solicitó hace 11 minutos
    await sesion.execute(
        sql_text(
            "UPDATE handoffs h JOIN conversaciones c ON c.id = h.conversacion_id "
            "SET h.solicitado_at = NOW() - INTERVAL 11 MINUTE WHERE c.codigo = :c"
        ),
        {"c": session_id},
    )
    await sesion.commit()

    expirados = await expirar_handoffs_pendientes(sesion)
    assert expirados >= 1

    fila = (
        await sesion.execute(
            sql_text(
                "SELECT h.estado, c.estado_bot FROM handoffs h "
                "JOIN conversaciones c ON c.id = h.conversacion_id WHERE c.codigo = :c"
            ),
            {"c": session_id},
        )
    ).one()
    assert fila.estado == "expirado"
    assert fila.estado_bot == "ACTIVE"

    # en la próxima interacción el bot se disculpa y ofrece registrar incidencia
    data = await _enviar(api_client, session_id, headers, texto="hola?")
    assert data["mensajes"][0]["texto"] == textos.HANDOFF_EXPIRADO
    assert any(o["id"] == "registrar_incidencia" for o in data["mensajes"][0]["opciones"])
