"""Integración contra MySQL real (chatbot_test) con el cliente de tickets mockeado.

Cubre: protocolo de chat completo, F-02/F-03/F-06/F-08, fallback x3 → handoff,
persistencia del flujo tras "reinicio", cierre por inactividad (RN-09) y
registro de latencia_ms (RF-09).
"""

from typing import Any

import pytest
from sqlalchemy import text as sql_text

from app.dialogo import textos
from tests.fakes import detalle_ticket

pytestmark = pytest.mark.integration


async def _crear_sesion(api_client) -> tuple[str, dict[str, str]]:
    r = await api_client.post("/api/chat/sesiones", json={"canal": "web_widget"})
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["success"] is True and cuerpo["code"] == 201
    data = cuerpo["data"]
    assert data["mensajeBienvenida"] == textos.BIENVENIDA
    assert [o["id"] for o in data["menu"]] == [i for i, _ in textos.MENU_OPCIONES]
    return data["sessionId"], {"X-Session-Token": data["sessionToken"]}


async def _enviar(api_client, session_id, headers, **campos: Any) -> dict[str, Any]:
    r = await api_client.post(
        "/api/chat/mensajes", json={"sessionId": session_id, **campos}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ------------------------------------------------------------------ protocolo


async def test_sesion_y_autenticacion(api_client):
    session_id, headers = await _crear_sesion(api_client)

    # sin token → 401 envelope
    r = await api_client.post(
        "/api/chat/mensajes", json={"sessionId": session_id, "texto": "hola"}
    )
    assert r.status_code == 401
    assert r.json()["success"] is False

    # token inválido → 401
    r = await api_client.post(
        "/api/chat/mensajes",
        json={"sessionId": session_id, "texto": "hola"},
        headers={"X-Session-Token": "token-falso"},
    )
    assert r.status_code == 401

    # token correcto → 200 con estadoBot
    data = await _enviar(api_client, session_id, headers, texto="hola")
    assert data["estadoBot"] == "ACTIVE"
    assert data["mensajes"][0]["texto"] == textos.BIENVENIDA


async def test_body_invalido_400(api_client):
    session_id, headers = await _crear_sesion(api_client)
    r = await api_client.post(
        "/api/chat/mensajes", json={"sessionId": session_id}, headers=headers
    )
    assert r.status_code == 400
    r = await api_client.post(
        "/api/chat/mensajes",
        json={"sessionId": session_id, "texto": "hola", "opcionId": "menu"},
        headers=headers,
    )
    assert r.status_code == 400


async def test_sesion_sin_body_tambien_funciona(api_client):
    r = await api_client.post("/api/chat/sesiones")
    assert r.status_code == 201
    assert r.json()["data"]["sessionToken"]


async def test_adjuntos_proxy(api_client, fake_tickets):
    session_id, headers = await _crear_sesion(api_client)

    # sin token → 401
    r = await api_client.post(
        "/api/chat/adjuntos", files={"file": ("captura.png", b"png-bytes", "image/png")}
    )
    assert r.status_code == 401

    r = await api_client.post(
        "/api/chat/adjuntos",
        files={"file": ("captura.png", b"png-bytes", "image/png")},
        headers=headers,
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["adjuntoId"] == fake_tickets.adjuntos[0]
    assert data["nombreOriginal"] == "captura.png"


# ------------------------------------------------------------------ F-02


async def test_f02_ciclo_completo_http(api_client, fake_tickets, sesion):
    session_id, headers = await _crear_sesion(api_client)

    await _enviar(api_client, session_id, headers, opcionId="registrar_incidencia")
    await _enviar(api_client, session_id, headers, texto="Juan Pérez")
    await _enviar(api_client, session_id, headers, texto="2021012345")
    await _enviar(api_client, session_id, headers, texto="jperez@unac.edu.pe")
    await _enviar(api_client, session_id, headers, opcionId="escuela_industrial")
    await _enviar(api_client, session_id, headers, opcionId="cat_0")
    await _enviar(
        api_client, session_id, headers, texto="No puedo acceder a mi correo institucional."
    )
    await _enviar(api_client, session_id, headers, opcionId="prio_media")
    data = await _enviar(api_client, session_id, headers, opcionId="omitir")
    assert "confirma los datos" in data["mensajes"][0]["texto"]

    data = await _enviar(api_client, session_id, headers, opcionId="confirmar")
    assert data["mensajes"][0]["texto"] == textos.ticket_registrado("INC-2026-0001")

    payload, clave = fake_tickets.registros[0]
    assert payload["correo"] == "jperez@unac.edu.pe"
    assert payload["conversacionCodigo"] == session_id
    assert len(clave) == 36

    # el estado del flujo quedó limpio y la sesión identificada, en BD
    fila = (
        await sesion.execute(
            sql_text(
                "SELECT usuario_correo, flujo_activo FROM conversaciones WHERE codigo = :c"
            ),
            {"c": session_id},
        )
    ).one()
    assert fila.usuario_correo == "jperez@unac.edu.pe"
    assert fila.flujo_activo is None


async def test_f02_persistencia_tras_reinicio(nueva_instancia_api, fake_tickets):
    """Criterio 3.2: el flujo sobrevive a un reinicio del servicio (estado en BD)."""
    async with nueva_instancia_api() as cliente_a:
        session_id, headers = await _crear_sesion(cliente_a)
        await _enviar(cliente_a, session_id, headers, opcionId="registrar_incidencia")
        await _enviar(cliente_a, session_id, headers, texto="Ana Torres")
        await _enviar(cliente_a, session_id, headers, texto="2021012345")
        await _enviar(cliente_a, session_id, headers, texto="atorres@unac.edu.pe")

    # 'reinicio': app nueva sobre la misma BD; el flujo continúa donde quedó
    async with nueva_instancia_api() as cliente_b:
        data = await _enviar(cliente_b, session_id, headers, opcionId="escuela_sistemas")
        assert "categoría" in data["mensajes"][0]["texto"].lower()
        await _enviar(cliente_b, session_id, headers, opcionId="cat_2")
        await _enviar(cliente_b, session_id, headers, texto="El wifi no funciona en el aula 204.")
        await _enviar(cliente_b, session_id, headers, opcionId="prio_alta")
        await _enviar(cliente_b, session_id, headers, opcionId="omitir")
        data = await _enviar(cliente_b, session_id, headers, opcionId="confirmar")
        assert data["mensajes"][0]["texto"] == textos.ticket_registrado("INC-2026-0001")
    payload, _ = fake_tickets.registros[0]
    assert payload["nombre"] == "Ana Torres"  # datos capturados antes del reinicio


# ------------------------------------------------------------------ F-03


async def test_f03_consulta_por_codigo_http(api_client, fake_tickets):
    fake_tickets.tickets["INC-2026-0009"] = {
        "correo": "ana@unac.edu.pe",
        "detalle": detalle_ticket("INC-2026-0009", estado="Asignado"),
    }
    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, opcionId="consultar_estado")
    await _enviar(api_client, session_id, headers, texto="ana@unac.edu.pe")
    await _enviar(api_client, session_id, headers, opcionId="modo_codigo")
    data = await _enviar(api_client, session_id, headers, texto="INC-2026-0009")
    assert "Asignado" in data["mensajes"][0]["texto"]


# ------------------------------------------------------------------ F-06


async def test_f06_escalar_http(api_client, fake_tickets):
    fake_tickets.tickets["INC-2026-0002"] = {"correo": "ana@unac.edu.pe", "escalable": True}
    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, texto="quiero escalar el INC-2026-0002")
    await _enviar(api_client, session_id, headers, texto="ana@unac.edu.pe")
    data = await _enviar(
        api_client, session_id, headers, texto="Sigue sin resolverse desde hace días."
    )
    assert data["mensajes"][0]["texto"] == textos.ESCALADO_CONFIRMACION
    assert fake_tickets.escalados[0][0] == "INC-2026-0002"


# ------------------------------------------------------------------ F-08


async def test_f08_encuesta_http(api_client, fake_tickets):
    session_id, headers = await _crear_sesion(api_client)
    data = await _enviar(api_client, session_id, headers, opcionId="finalizar")
    assert data["mensajes"][0]["tipo"] == "encuesta"
    await _enviar(api_client, session_id, headers, opcionId="calif_4")
    data = await _enviar(api_client, session_id, headers, opcionId="omitir")
    assert data["mensajes"][-1]["texto"] == textos.DESPEDIDA
    assert fake_tickets.encuestas[0]["calificacion"] == 4
    assert fake_tickets.encuestas[0]["conversacionCodigo"] == session_id

    # la conversación quedó cerrada → siguiente mensaje 409 con aviso de reinicio
    r = await api_client.post(
        "/api/chat/mensajes",
        json={"sessionId": session_id, "texto": "hola"},
        headers=headers,
    )
    assert r.status_code == 409
    assert r.json()["message"] == textos.SESION_CERRADA


# ------------------------------------------------------------------ F-09


async def test_fallback_x3_crea_handoff(api_client, fake_tickets, sesion):
    session_id, headers = await _crear_sesion(api_client)
    data = await _enviar(api_client, session_id, headers, texto="xyzzy")
    assert data["mensajes"][0]["texto"] == textos.FALLO_1
    data = await _enviar(api_client, session_id, headers, texto="xyzzy dos")
    assert data["mensajes"][0]["texto"] == textos.FALLO_2
    data = await _enviar(api_client, session_id, headers, texto="xyzzy tres")
    assert data["mensajes"][0]["tipo"] == "handoff"
    assert data["mensajes"][0]["texto"] == textos.TRANSICION_HANDOFF
    assert data["estadoBot"] == "PAUSED"  # Semana 5 (F-07): el bot se pausa (RN-05)

    fila = (
        await sesion.execute(
            sql_text(
                "SELECT h.motivo, h.estado FROM handoffs h "
                "JOIN conversaciones c ON c.id = h.conversacion_id WHERE c.codigo = :c"
            ),
            {"c": session_id},
        )
    ).one()
    assert fila.motivo == "fallback_x3"
    assert fila.estado == "pendiente"


# ------------------------------------------------------------------ FAQ interina


async def test_faq_fulltext_con_seed(api_client, fake_tickets):
    session_id, headers = await _crear_sesion(api_client)
    data = await _enviar(
        api_client, session_id, headers, texto="¿cómo me conecto al wifi del campus?"
    )
    mensajes = data["mensajes"]
    assert "WiFi" in mensajes[0]["texto"]  # contenido textual del artículo seed
    assert mensajes[0]["meta"]["fuentesKb"], "debe citar fuentes KB"
    assert len(mensajes) == 1


async def test_faq_rerank_por_etiquetas(api_client, fake_tickets):
    """prd/06 §3: el bonus por etiquetas prioriza el artículo correcto."""
    session_id, headers = await _crear_sesion(api_client)
    data = await _enviar(
        api_client, session_id, headers, texto="olvidé mi contraseña del correo"
    )
    assert "Recuperación de contraseña" in data["mensajes"][0]["texto"]


async def test_faq_sin_match_informa_limitacion(api_client, fake_tickets):
    session_id, headers = await _crear_sesion(api_client)
    data = await _enviar(
        api_client, session_id, headers, texto="no puedo zzkqx wwyyzz qqqppp"
    )
    assert data["mensajes"][0]["texto"] == textos.KB_SIN_RESPUESTA


async def test_info_ctic_devuelve_articulo(api_client, fake_tickets):
    session_id, headers = await _crear_sesion(api_client)
    data = await _enviar(api_client, session_id, headers, opcionId="info_ctic")
    assert "FIIS" in data["mensajes"][0]["texto"]
    assert data["mensajes"][0]["meta"]["fuentesKb"]


# ------------------------------------------------------------- RN-09 / RF-09


async def test_cierre_por_inactividad(api_client, sesion):
    from app.services.sesiones import cerrar_conversaciones_inactivas

    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, texto="hola")

    # retro-datar la actividad > 15 minutos (RN-09)
    await sesion.execute(
        sql_text(
            "UPDATE conversaciones SET iniciada_at = NOW() - INTERVAL 20 MINUTE "
            "WHERE codigo = :c"
        ),
        {"c": session_id},
    )
    await sesion.execute(
        sql_text(
            "UPDATE mensajes m JOIN conversaciones c ON c.id = m.conversacion_id "
            "SET m.created_at = NOW() - INTERVAL 20 MINUTE WHERE c.codigo = :c"
        ),
        {"c": session_id},
    )
    await sesion.commit()

    cerradas = await cerrar_conversaciones_inactivas(sesion)
    assert cerradas >= 1
    fila = (
        await sesion.execute(
            sql_text("SELECT estado, motivo_cierre FROM conversaciones WHERE codigo = :c"),
            {"c": session_id},
        )
    ).one()
    assert fila.estado == "cerrada"
    assert fila.motivo_cierre == "timeout"

    r = await api_client.post(
        "/api/chat/mensajes",
        json={"sessionId": session_id, "texto": "hola"},
        headers=headers,
    )
    assert r.status_code == 409


async def test_latencia_y_auditoria_qa07(api_client, sesion):
    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, texto="hola")

    filas = (
        await sesion.execute(
            sql_text(
                "SELECT m.emisor, m.intent, m.confianza, m.latencia_ms FROM mensajes m "
                "JOIN conversaciones c ON c.id = m.conversacion_id "
                "WHERE c.codigo = :c ORDER BY m.id"
            ),
            {"c": session_id},
        )
    ).all()
    usuarios = [f for f in filas if f.emisor == "usuario"]
    bots = [f for f in filas if f.emisor == "bot"]
    assert usuarios[0].intent == "saludo"
    assert usuarios[0].confianza is not None
    assert all(b.latencia_ms is not None for b in bots[1:]), "latencia_ms registrado (RF-09)"

    # auditoría QA-07/QA-08: ahora protegida con el JWT del staff (cookie panel_token)
    from tests.conftest import token_staff

    r = await api_client.get(f"/api/chat/conversaciones/{session_id}/mensajes")
    assert r.status_code == 401
    r = await api_client.get(
        f"/api/chat/conversaciones/{session_id}/mensajes",
        cookies={"panel_token": token_staff("tecnico")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == len(filas)
    assert any(m["latenciaMs"] is not None for m in data["mensajes"])
