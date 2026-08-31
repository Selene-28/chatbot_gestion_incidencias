"""Exception handlers: AppError, validación de Pydantic y errores no controlados."""

from app.core.errors import (
    AppError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationAppError,
)


def test_jerarquia_de_codigos_por_defecto():
    assert ValidationAppError().code == 400
    assert UnauthorizedError().code == 401
    assert ForbiddenError().code == 403
    assert NotFoundError().code == 404
    assert ConflictError().code == 409
    assert BusinessRuleError().code == 422
    assert AppError().code == 500
    assert isinstance(NotFoundError(), AppError)


def test_app_error_con_mensaje_personalizado(client):
    response = client.get("/_test/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body == {
        "success": False,
        "code": 404,
        "message": "La incidencia no fue encontrada.",
        "errors": [],
    }


def test_app_error_con_mensaje_por_defecto(client):
    response = client.get("/_test/conflict")
    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 409
    assert body["errors"] == []


def test_validacion_pydantic_devuelve_field_description(client):
    # Falta "correo" y "calificacion" no es entero
    response = client.post("/_test/validacion", json={"calificacion": "no-numero"})
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 400
    campos = {error["field"] for error in body["errors"]}
    assert campos == {"correo", "calificacion"}
    for error in body["errors"]:
        assert set(error.keys()) == {"field", "description"}
        assert error["description"]


def test_excepcion_no_controlada_devuelve_500_generico(client):
    response = client.get("/_test/boom")
    assert response.status_code == 500
    body = response.json()
    assert body == {
        "success": False,
        "code": 500,
        "message": "Ocurrió un error interno.",
        "errors": [],
    }
    # El detalle interno no debe filtrarse en la respuesta
    assert "detalle interno" not in response.text
