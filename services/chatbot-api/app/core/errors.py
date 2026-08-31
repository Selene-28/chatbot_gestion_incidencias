"""Jerarquía de errores de aplicación y exception handlers de FastAPI.

Todos los errores se traducen al envelope estándar de `prd/04-api.md` §2.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.envelope import FieldError, fail

logger = logging.getLogger("app.errors")


class AppError(Exception):
    """Error base de la aplicación: se traduce al envelope de error del DRS."""

    default_code = 500
    default_message = "Ocurrió un error interno."

    def __init__(
        self,
        message: str | None = None,
        errors: list[FieldError] | list[dict[str, str]] | None = None,
        code: int | None = None,
    ) -> None:
        self.code = code if code is not None else self.default_code
        self.message = message if message is not None else self.default_message
        self.errors = errors or []
        super().__init__(self.message)


class ValidationAppError(AppError):
    """400 — los datos enviados son inválidos."""

    default_code = 400
    default_message = "Los datos enviados son inválidos."


class UnauthorizedError(AppError):
    """401 — no autenticado."""

    default_code = 401
    default_message = "Debe autenticarse para realizar esta operación."


class ForbiddenError(AppError):
    """403 — sin permiso."""

    default_code = 403
    default_message = "No tiene permisos para realizar esta operación."


class NotFoundError(AppError):
    """404 — recurso no encontrado."""

    default_code = 404
    default_message = "El recurso solicitado no fue encontrado."


class ConflictError(AppError):
    """409 — conflicto de estado."""

    default_code = 409
    default_message = "La operación entra en conflicto con el estado actual del recurso."


class BusinessRuleError(AppError):
    """422 — regla de negocio no satisfecha."""

    default_code = 422
    default_message = "La operación no cumple las reglas de negocio."


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Traduce AppError (y subclases) al envelope de error con su status HTTP."""
    return JSONResponse(
        status_code=exc.code,
        content=fail(code=exc.code, message=exc.message, errors=exc.errors),
    )


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Traduce los errores de validación de Pydantic a errors[{field, description}].

    El campo se construye desde `loc` omitiendo el prefijo 'body'.
    """
    errors: list[FieldError] = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", []) if part != "body"]
        errors.append(
            FieldError(field=".".join(loc) or "body", description=str(err.get("msg", "")))
        )
    return JSONResponse(
        status_code=400,
        content=fail(code=400, message="Los datos enviados son inválidos.", errors=errors),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Última barrera: 500 con mensaje genérico; el detalle solo va al log."""
    logger.exception("Excepción no controlada en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=fail(code=500, message="Ocurrió un error interno."),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos los handlers de excepciones en la aplicación."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
