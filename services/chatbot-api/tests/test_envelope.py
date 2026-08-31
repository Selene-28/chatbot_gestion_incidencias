"""Forma exacta del envelope estándar (prd/04 §2)."""

from app.core.envelope import DEFAULT_OK_MESSAGE, FieldError, fail, ok


def test_ok_forma_exacta_con_defaults():
    envelope = ok({"ticketId": "INC-2026-0001"})
    assert envelope == {
        "success": True,
        "code": 200,
        "message": DEFAULT_OK_MESSAGE,
        "data": {"ticketId": "INC-2026-0001"},
    }
    assert set(envelope.keys()) == {"success", "code", "message", "data"}


def test_ok_sin_data_devuelve_objeto_vacio():
    envelope = ok()
    assert envelope["data"] == {}
    assert envelope["success"] is True
    assert envelope["code"] == 200


def test_ok_con_code_y_message_personalizados():
    envelope = ok({"estado": "Registrado"}, message="La incidencia fue registrada.", code=201)
    assert envelope["code"] == 201
    assert envelope["message"] == "La incidencia fue registrada."


def test_fail_forma_exacta():
    envelope = fail(
        400,
        "Los datos enviados son inválidos.",
        errors=[{"field": "correo", "description": "El correo institucional es obligatorio."}],
    )
    assert envelope == {
        "success": False,
        "code": 400,
        "message": "Los datos enviados son inválidos.",
        "errors": [{"field": "correo", "description": "El correo institucional es obligatorio."}],
    }
    assert set(envelope.keys()) == {"success", "code", "message", "errors"}


def test_fail_sin_errors_devuelve_lista_vacia():
    envelope = fail(500, "Ocurrió un error interno.")
    assert envelope["errors"] == []


def test_fail_acepta_modelos_field_error():
    envelope = fail(
        422,
        "Regla de negocio no satisfecha.",
        errors=[FieldError(field="calificacion", description="Debe estar entre 1 y 5.")],
    )
    assert envelope["errors"] == [
        {"field": "calificacion", "description": "Debe estar entre 1 y 5."}
    ]
