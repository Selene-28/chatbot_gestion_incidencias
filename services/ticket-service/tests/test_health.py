"""Pruebas del endpoint de salud (sin MySQL disponible)."""

from fastapi.testclient import TestClient


def test_healthz_reporta_db_down_sin_mysql(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "down"}
