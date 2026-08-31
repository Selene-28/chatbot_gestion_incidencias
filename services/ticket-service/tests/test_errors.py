"""Pruebas de la jerarquía de errores y de los handlers de excepciones."""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import (
    AppError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationAppError,
)
from app.main import create_app


@pytest.mark.parametrize(
    ("exc_class", "expected_code"),
    [
        (ValidationAppError, 400),
        (UnauthorizedError, 401),
        (ForbiddenError, 403),
        (NotFoundError, 404),
        (ConflictError, 409),
        (BusinessRuleError, 422),
    ],
)
def test_codigos_de_la_jerarquia(exc_class: type[AppError], expected_code: int) -> None:
    assert exc_class("mensaje").code == expected_code
    assert issubclass(exc_class, AppError)


def _app_con_rutas() -> TestClient:
    app = create_app()

    class Encuesta(BaseModel):
        calificacion: int

    @app.get("/no-existe-recurso")
    async def not_found() -> None:
        raise NotFoundError("La incidencia no fue encontrada.")

    @app.get("/conflicto")
    async def conflicto() -> None:
        raise ConflictError(
            "La incidencia ya fue calificada.",
            errors=[{"field": "ticketId", "description": "Ya existe una encuesta."}],
        )

    @app.post("/validado")
    async def validado(payload: Encuesta) -> dict:
        return {"ok": True}

    @app.get("/explota")
    async def explota() -> None:
        raise RuntimeError("detalle sensible que no debe filtrarse")

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_devuelve_envelope() -> None:
    client = _app_con_rutas()
    response = client.get("/no-existe-recurso")
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": 404,
        "message": "La incidencia no fue encontrada.",
        "errors": [],
    }


def test_app_error_con_detalle_de_campos() -> None:
    client = _app_con_rutas()
    response = client.get("/conflicto")
    assert response.status_code == 409
    body = response.json()
    assert body["errors"] == [{"field": "ticketId", "description": "Ya existe una encuesta."}]


def test_validacion_de_request_devuelve_400_con_campos() -> None:
    client = _app_con_rutas()
    response = client.post("/validado", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 400
    assert body["message"] == "Los datos enviados son inválidos."
    assert body["errors"], "debe reportar al menos un error de campo"
    error = body["errors"][0]
    assert error["field"] == "calificacion"
    assert error["description"]


def test_error_no_controlado_devuelve_500_generico() -> None:
    client = _app_con_rutas()
    response = client.get("/explota")
    assert response.status_code == 500
    body = response.json()
    assert body == {
        "success": False,
        "code": 500,
        "message": "Ocurrió un error interno.",
        "errors": [],
    }
    # El detalle interno jamás viaja al cliente
    assert "sensible" not in response.text
