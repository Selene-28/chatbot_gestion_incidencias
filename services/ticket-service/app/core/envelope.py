"""Envelope estándar de respuestas según prd/04 §2 (contrato del DRS).

Éxito:  {"success": true,  "code": 200, "message": "...", "data": {...}}
Error:  {"success": false, "code": 400, "message": "...",
         "errors": [{"field": "...", "description": "..."}]}
"""

from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel

DEFAULT_OK_MESSAGE = "Operación realizada correctamente."


class ErrorDetail(BaseModel):
    """Detalle de un error de validación o de negocio."""

    field: str
    description: str


class SuccessEnvelope(BaseModel):
    """Envelope de respuesta exitosa."""

    success: bool = True
    code: int = 200
    message: str = DEFAULT_OK_MESSAGE
    data: dict[str, Any] = {}


class ErrorEnvelope(BaseModel):
    """Envelope de respuesta de error."""

    success: bool = False
    code: int
    message: str
    errors: list[ErrorDetail] = []


def ok(
    data: dict[str, Any] | None = None,
    message: str = DEFAULT_OK_MESSAGE,
    code: int = 200,
) -> JSONResponse:
    """Construye una respuesta exitosa con el envelope estándar."""
    envelope = SuccessEnvelope(code=code, message=message, data=data or {})
    return JSONResponse(status_code=code, content=envelope.model_dump())


def fail(
    code: int,
    message: str,
    errors: list[ErrorDetail] | list[dict[str, str]] | None = None,
) -> JSONResponse:
    """Construye una respuesta de error con el envelope estándar."""
    details = [e if isinstance(e, ErrorDetail) else ErrorDetail(**e) for e in (errors or [])]
    envelope = ErrorEnvelope(code=code, message=message, errors=details)
    return JSONResponse(status_code=code, content=envelope.model_dump())
