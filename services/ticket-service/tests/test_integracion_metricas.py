"""Integración del endpoint de métricas de tickets (RF-14, consumido por chatbot-api).

GET /api/metricas/tickets?desde&hasta → ticketsPorEstado, calificacionProm, encuestas.
"""

import uuid

import pytest

pytestmark = pytest.mark.integration

_RANGO = {"desde": "2020-01-01", "hasta": "2100-12-31"}


def _cuerpo(**extra) -> dict:
    datos = {
        "nombre": "Ana Torres",
        "correo": f"met{uuid.uuid4().hex[:10]}@unac.edu.pe",
        "area": "Sistemas",
        "categoria": "Correo Institucional",
        "descripcion": "No puedo acceder a mi correo institucional.",
        "prioridad": "Media",
        "origen": "chatbot",
    }
    datos.update(extra)
    return datos


async def test_metricas_requiere_api_key(api_client) -> None:
    # sin la cabecera X-Api-Key → 401
    r = await api_client.get("/api/metricas/tickets", params=_RANGO, headers={"X-Api-Key": ""})
    assert r.status_code == 401


async def test_metricas_cuenta_estados_y_satisfaccion(api_client) -> None:
    # registra un ticket y una encuesta, luego consulta las métricas
    reg = await api_client.post("/api/incidencias", json=_cuerpo())
    ticket_id = reg.json()["data"]["ticketId"]
    await api_client.post("/api/encuesta", json={"ticketId": ticket_id, "calificacion": 4})

    r = await api_client.get("/api/metricas/tickets", params=_RANGO)
    assert r.status_code == 200
    data = r.json()["data"]

    assert data["ticketsPorEstado"].get("Registrado", 0) >= 1
    assert data["encuestas"] >= 1
    assert 1.0 <= data["calificacionProm"] <= 5.0


async def test_metricas_rango_vacio_degrada_a_neutro(api_client) -> None:
    # un rango sin datos devuelve estructura neutra, no error
    r = await api_client.get(
        "/api/metricas/tickets", params={"desde": "1999-01-01", "hasta": "1999-01-02"}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["ticketsPorEstado"] == {}
    assert data["encuestas"] == 0
    assert data["calificacionProm"] is None
