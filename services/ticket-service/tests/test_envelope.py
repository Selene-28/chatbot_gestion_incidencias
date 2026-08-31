"""Pruebas del envelope estándar (prd/04 §2)."""

import json

from app.core.envelope import ErrorDetail, ErrorEnvelope, SuccessEnvelope, fail, ok


def _body(response) -> dict:
    return json.loads(response.body)


def test_ok_por_defecto() -> None:
    response = ok()
    assert response.status_code == 200
    assert _body(response) == {
        "success": True,
        "code": 200,
        "message": "Operación realizada correctamente.",
        "data": {},
    }


def test_ok_con_data_y_codigo_201() -> None:
    response = ok(
        {"ticketId": "INC-2026-0001", "estado": "Registrado"},
        message="La incidencia fue registrada correctamente.",
        code=201,
    )
    assert response.status_code == 201
    body = _body(response)
    assert body["success"] is True
    assert body["code"] == 201
    assert body["message"] == "La incidencia fue registrada correctamente."
    assert body["data"] == {"ticketId": "INC-2026-0001", "estado": "Registrado"}


def test_fail_con_errores_de_campo() -> None:
    response = fail(
        400,
        "Los datos enviados son inválidos.",
        [{"field": "correo", "description": "El correo institucional es obligatorio."}],
    )
    assert response.status_code == 400
    assert _body(response) == {
        "success": False,
        "code": 400,
        "message": "Los datos enviados son inválidos.",
        "errors": [
            {"field": "correo", "description": "El correo institucional es obligatorio."}
        ],
    }


def test_fail_sin_errores() -> None:
    response = fail(500, "Ocurrió un error interno.")
    body = _body(response)
    assert body["success"] is False
    assert body["errors"] == []


def test_fail_acepta_modelos_error_detail() -> None:
    detail = ErrorDetail(field="calificacion", description="Debe estar entre 1 y 5.")
    body = _body(fail(422, "Regla de negocio violada.", [detail]))
    assert body["errors"][0] == {"field": "calificacion", "description": "Debe estar entre 1 y 5."}


def test_modelos_tipados() -> None:
    exito = SuccessEnvelope(code=200, message="OK", data={"x": 1})
    error = ErrorEnvelope(code=404, message="No encontrado.")
    assert exito.success is True
    assert error.success is False
    assert error.errors == []
