"""Envelope estándar de respuestas según `prd/04-api.md` §2 (contrato DRS).

Éxito:  {"success": true,  "code": 200, "message": "...", "data": {...}}
Error:  {"success": false, "code": 400, "message": "...",
         "errors": [{"field": "...", "description": "..."}]}
"""

from typing import Any

from pydantic import BaseModel

DEFAULT_OK_MESSAGE = "Operación realizada correctamente."


class FieldError(BaseModel):
    """Detalle de un error de validación asociado a un campo."""

    field: str
    description: str


class SuccessEnvelope(BaseModel):
    """Envelope de éxito del DRS."""

    success: bool = True
    code: int = 200
    message: str = DEFAULT_OK_MESSAGE
    data: Any = None


class ErrorEnvelope(BaseModel):
    """Envelope de error del DRS."""

    success: bool = False
    code: int
    message: str
    errors: list[FieldError] = []


def ok(
    data: Any = None,
    message: str = DEFAULT_OK_MESSAGE,
    code: int = 200,
) -> dict[str, Any]:
    """Construye el envelope de éxito como dict listo para serializar."""
    if data is None:
        data = {}
    return SuccessEnvelope(code=code, message=message, data=data).model_dump()


def fail(
    code: int,
    message: str,
    errors: list[FieldError] | list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Construye el envelope de error como dict listo para serializar."""
    parsed = [e if isinstance(e, FieldError) else FieldError(**e) for e in (errors or [])]
    return ErrorEnvelope(code=code, message=message, errors=parsed).model_dump()
