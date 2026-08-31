"""Integración F-05 contra MySQL real (chatbot_test), tickets mockeado.

Cubre el criterio de la tarea 4.6: problema_internet → árbol de diagnóstico →
no resuelto → F-02 pre-llenado (sin repreguntar categoría/descripción) →
ticket registrado. También la capa 2 con el LLM falso y el historial desde BD.
"""

from typing import Any

import pytest

from app.dialogo import textos
from tests.llm_falso import llm_falso  # noqa: F401 (fixture)

pytestmark = pytest.mark.integration


async def _crear_sesion(api_client) -> tuple[str, dict[str, str]]:
    r = await api_client.post("/api/chat/sesiones", json={"canal": "web_widget"})
    assert r.status_code == 201
    data = r.json()["data"]
    return data["sessionId"], {"X-Session-Token": data["sessionToken"]}


async def _enviar(api_client, session_id, headers, **campos: Any) -> dict[str, Any]:
    r = await api_client.post(
        "/api/chat/mensajes", json={"sessionId": session_id, **campos}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_diagnostico_no_resuelto_registra_ticket_prellenado(api_client, fake_tickets):
    session_id, headers = await _crear_sesion(api_client)

    # capa 1 rutea el problema obvio al árbol de Internet/WiFi
    sintoma = "no tengo internet en el pabellón B"
    data = await _enviar(api_client, session_id, headers, texto=sintoma)
    assert "WiFi o cable" in data["mensajes"][0]["texto"]
    assert data["mensajes"][0]["meta"]["via"] == "regla"
    assert data["mensajes"][0]["meta"]["intent"] == "problema_internet"

    await _enviar(api_client, session_id, headers, opcionId="wifi")
    data = await _enviar(api_client, session_id, headers, opcionId="red_no")
    assert "Olvida la red" in data["mensajes"][0]["texto"]

    # no se resolvió → F-02 encadenado, pide identificación
    data = await _enviar(api_client, session_id, headers, opcionId="resuelto_no")
    assert "Registremos una incidencia" in data["mensajes"][0]["texto"]
    assert "nombre completo" in data["mensajes"][1]["texto"]

    await _enviar(api_client, session_id, headers, texto="Luis Quispe")
    await _enviar(api_client, session_id, headers, texto="2021012345")
    await _enviar(api_client, session_id, headers, texto="lquispe@unac.edu.pe")
    # tras la escuela salta categoría y descripción (pre-llenadas) → prioridad
    data = await _enviar(api_client, session_id, headers, opcionId="escuela_industrial")
    assert "prioridad" in data["mensajes"][0]["texto"].lower()

    await _enviar(api_client, session_id, headers, opcionId="prio_alta")
    data = await _enviar(api_client, session_id, headers, opcionId="omitir")
    assert "confirma los datos" in data["mensajes"][0]["texto"]
    assert "Internet/WiFi" in data["mensajes"][0]["texto"]

    data = await _enviar(api_client, session_id, headers, opcionId="confirmar")
    assert data["mensajes"][0]["texto"] == textos.ticket_registrado("INC-2026-0001")

    payload, _clave = fake_tickets.registros[0]
    assert payload["categoria"] == "Internet/WiFi"
    assert payload["correo"] == "lquispe@unac.edu.pe"
    assert payload["prioridad"] == "Alta"
    descripcion = payload["descripcion"]
    assert f"«{sintoma}»" in descripcion
    assert "conexión por WiFi" in descripcion
    assert "no ve la red UNAC" in descripcion


async def test_diagnostico_resuelto_cuenta_como_atencion(api_client, fake_tickets):
    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, texto="no puedo entrar al aula virtual")
    await _enviar(api_client, session_id, headers, opcionId="aula_credenciales")
    data = await _enviar(api_client, session_id, headers, opcionId="resuelto_si")
    assert "Me alegra" in data["mensajes"][0]["texto"]

    # al despedirse se ofrece la encuesta F-08 (hubo atención)
    data = await _enviar(api_client, session_id, headers, texto="adiós")
    assert data["mensajes"][0]["tipo"] == "encuesta"


async def test_capa2_llm_clasifica_con_historial_de_bd(
    api_client, fake_tickets, sesion, llm_falso  # noqa: F811
):
    session_id, headers = await _crear_sesion(api_client)
    await _enviar(api_client, session_id, headers, texto="hola")

    llm_falso.respuesta = {"intent": "problema_internet", "confianza": 0.9}
    data = await _enviar(
        api_client, session_id, headers, texto="me aparece un aviso raro en el pabellon"
    )
    # la capa 2 clasificó y el intent nuevo inició el diagnóstico
    assert "WiFi o cable" in data["mensajes"][0]["texto"]
    assert data["mensajes"][0]["meta"]["via"] == "llm"
    # el prompt incluyó el historial real de la conversación (últimos turnos)
    user = llm_falso.llamadas[0]["user"]
    assert user.startswith("Historial breve: ")
    assert "Usuario: hola" in user
    assert user.endswith("Mensaje: me aparece un aviso raro en el pabellon")

    # intent y confianza del turno LLM quedaron auditados en BD (RF-09)
    from sqlalchemy import text as sql_text

    fila = (
        await sesion.execute(
            sql_text(
                "SELECT m.intent, m.confianza FROM mensajes m "
                "JOIN conversaciones c ON c.id = m.conversacion_id "
                "WHERE c.codigo = :c AND m.emisor = 'usuario' ORDER BY m.id DESC LIMIT 1"
            ),
            {"c": session_id},
        )
    ).one()
    assert fila.intent == "problema_internet"
    assert float(fila.confianza) == pytest.approx(0.9)
