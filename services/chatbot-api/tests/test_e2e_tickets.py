"""E2E opcional: F-02 completo contra el ticket-service REAL en localhost:8001.

Autoskip si el ticket-service no responde. Crea un ticket real en la BD de
desarrollo del ticket-service (origen `chatbot`).
"""

import os
import re
from pathlib import Path

import httpx
import pytest

from app.clients.tickets import TicketsClient
from app.dialogo import textos

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

TICKET_SERVICE_URL = os.environ.get("E2E_TICKETS_URL", "http://localhost:8001")


def _api_key_real() -> str:
    env_file = Path(__file__).resolve().parents[3] / ".env"
    if env_file.exists():
        for linea in env_file.read_text().splitlines():
            if linea.startswith("TICKETS_API_KEY="):
                return linea.split("=", 1)[1].strip()
    return "cambiar"


def _ticket_service_disponible() -> bool:
    try:
        r = httpx.get(f"{TICKET_SERVICE_URL}/healthz", timeout=2)
        return r.status_code == 200 and r.json().get("db") == "ok"
    except Exception:
        return False


@pytest.fixture()
def tickets_reales(monkeypatch):  # type: ignore[no-untyped-def]
    if not _ticket_service_disponible():
        pytest.skip(f"ticket-service no disponible en {TICKET_SERVICE_URL}; se omite E2E")
    cliente = TicketsClient(base_url=TICKET_SERVICE_URL, api_key=_api_key_real())
    monkeypatch.setattr("app.api.chat.get_tickets_client", lambda: cliente)
    return cliente


async def test_f02_e2e_sin_mocks(api_client, tickets_reales):
    r = await api_client.post("/api/chat/sesiones", json={"canal": "web_widget"})
    assert r.status_code == 201
    data = r.json()["data"]
    session_id = data["sessionId"]
    headers = {"X-Session-Token": data["sessionToken"]}

    async def enviar(**campos):
        respuesta = await api_client.post(
            "/api/chat/mensajes", json={"sessionId": session_id, **campos}, headers=headers
        )
        assert respuesta.status_code == 200, respuesta.text
        return respuesta.json()["data"]

    await enviar(opcionId="registrar_incidencia")
    await enviar(texto="Prueba E2E Chatbot")
    await enviar(texto="2021012345")
    await enviar(texto="e2e.chatbot@unac.edu.pe")
    await enviar(opcionId="escuela_sistemas")
    await enviar(opcionId="cat_7")  # Otros
    await enviar(texto="Incidencia de prueba E2E generada por la suite del chatbot.")
    await enviar(opcionId="prio_baja")
    data = await enviar(opcionId="omitir")
    assert "confirma los datos" in data["mensajes"][0]["texto"]

    data = await enviar(opcionId="confirmar")
    texto_final = data["mensajes"][0]["texto"]
    match = re.search(r"INC-\d{4}-\d{4}", texto_final)
    assert match, f"no se encontró código de ticket en: {texto_final}"
    ticket_id = match.group(0)
    assert texto_final == textos.ticket_registrado(ticket_id)

    # verificación cruzada: el ticket existe en el ticket-service real (API-02)
    detalle = await tickets_reales.consultar_ticket(ticket_id, "e2e.chatbot@unac.edu.pe")
    assert detalle["ticketId"] == ticket_id
    assert detalle["estado"] == "Registrado"
