"""Jerarquía de errores de aplicación y handlers de excepciones FastAPI.

Todos los errores salen con el envelope estándar de prd/04 §2.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.envelope import ErrorDetail, fail

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Ocurrió un error interno."


class AppError(Exception):
    """Error base de la aplicación; se traduce al envelope de error."""

    code: int = 500

    def __init__(
        self,
        message: str,
        errors: list[ErrorDetail] | list[dict[str, str]] | None = None,
        code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.errors = [
            e if isinstance(e, ErrorDetail) else ErrorDetail(**e) for e in (errors or [])
        ]
        if code is not None:
            self.code = code


class ValidationAppError(AppError):
    """400 — datos inválidos."""

    code = 400


class UnauthorizedError(AppError):
    """401 — no autenticado."""

    code = 401


class ForbiddenError(AppError):
    """403 — sin permiso."""

    code = 403


class NotFoundError(AppError):
    """404 — recurso no encontrado."""

    code = 404


class ConflictError(AppError):
    """409 — conflicto de estado."""

    code = 409


class BusinessRuleError(AppError):
    """422 — regla de negocio violada."""

    code = 422


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Traduce AppError al envelope de error estándar."""
    return fail(exc.code, exc.message, exc.errors)


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Traduce errores de validación de FastAPI a 400 con errors[{field, description}]."""
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in err.get("loc", ()) if part != "body") or "body",
            description=str(err.get("msg", "Valor inválido.")),
        )
        for err in exc.errors()
    ]
    return fail(400, "Los datos enviados son inválidos.", details)


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 genérico: el detalle va solo a los logs (prd/04 §2)."""
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return fail(500, INTERNAL_ERROR_MESSAGE)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los handlers de excepciones sobre la aplicación."""
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_error_handler)
