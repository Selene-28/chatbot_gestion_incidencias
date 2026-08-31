"""Integración (MySQL): /api/metricas/resumen (RF-14, prd/04 §8)."""

import pytest
from sqlalchemy import text as sql_text

from tests.conftest import token_staff

pytestmark = pytest.mark.integration

ADMIN = {"panel_token": token_staff("admin", sub=1)}
STAFF = {"panel_token": token_staff("tecnico", sub=2)}


class _FakeMetricasTickets:
    """Doble del cliente de tickets para las métricas del otro servicio."""

    async def resumen_metricas(self, desde: str, hasta: str) -> dict:
        return {
            "ticketsPorEstado": {"Registrado": 2, "Resuelto": 5},
            "calificacionProm": 4.5,
            "encuestas": 7,
        }


async def _sembrar(sesion) -> None:
    r = await sesion.execute(
        sql_text(
            "INSERT INTO conversaciones (codigo, canal, estado_bot, estado, iniciada_at) "
            "VALUES (UUID(), 'web_widget', 'ACTIVE', 'cerrada', NOW())"
        )
    )
    conv_id = r.lastrowid
    await sesion.execute(
        sql_text(
            "INSERT INTO mensajes (conversacion_id, emisor, contenido, intent, latencia_ms) "
            "VALUES (:c, 'usuario', 'hola', 'saludo', NULL), "
            "(:c, 'bot', 'respuesta', NULL, 850)"
        ),
        {"c": conv_id},
    )
    await sesion.commit()


async def test_resumen_formato_y_datos(api_client, sesion, monkeypatch):
    monkeypatch.setattr(
        "app.api.metricas.get_tickets_client", lambda: _FakeMetricasTickets()
    )
    await _sembrar(sesion)

    r = await api_client.get(
        "/api/metricas/resumen?desde=2000-01-01&hasta=2999-12-31", cookies=ADMIN
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    # forma EXACTA de prd/04 §8
    assert set(data) == {
        "conversaciones",
        "mensajes",
        "tasaAutoservicio",
        "latenciaPromMs",
        "calificacionProm",
        "encuestas",
        "ticketsPorEstado",
        "intentsTop",
        "tokensLlm",
    }
    assert data["conversaciones"] >= 1
    assert data["mensajes"] >= 2
    assert data["latenciaPromMs"] is not None and data["latenciaPromMs"] > 0
    assert isinstance(data["intentsTop"], list)
    assert all({"intent", "total"} <= set(i) for i in data["intentsTop"])
    # provenientes del cliente de tickets (doble)
    assert data["ticketsPorEstado"] == {"Registrado": 2, "Resuelto": 5}
    assert data["calificacionProm"] == 4.5
    assert data["encuestas"] == 7
    # sin API key en tests → contador de tokens en 0
    assert data["tokensLlm"] == 0


async def test_resumen_requiere_admin(api_client):
    r = await api_client.get("/api/metricas/resumen?desde=2026-01-01&hasta=2026-12-31")
    assert r.status_code == 401
    r = await api_client.get(
        "/api/metricas/resumen?desde=2026-01-01&hasta=2026-12-31", cookies=STAFF
    )
    assert r.status_code == 403


async def test_resumen_fecha_invalida_400(api_client):
    r = await api_client.get("/api/metricas/resumen?desde=ayer&hasta=2026-12-31", cookies=ADMIN)
    assert r.status_code == 400
