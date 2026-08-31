"""Autenticación del staff en chatbot-api (prd/04 §1).

El JWT del staff lo EMITE ``ticket-service`` (login del panel) y viaja en la
cookie HttpOnly ``panel_token`` (HS256, claims ``sub`` = id de usuario,
``rol`` ∈ {tecnico, admin}, exp 8 h, firmado con ``JWT_SECRET``).

Este módulo solo VALIDA esa cookie con el MISMO secreto: no consulta la base de
datos de tickets — confía en la firma del JWT. Devuelve un ``StaffActor`` con el
id y el rol tomados de los claims.
"""

from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError

# Mismo algoritmo y cookie que emite ticket-service (services/ticket-service).
JWT_ALGORITHM = "HS256"
PANEL_COOKIE = "panel_token"
ROLES_STAFF = ("tecnico", "admin")


@dataclass(frozen=True)
class StaffActor:
    """Identidad del staff autenticado, derivada exclusivamente del JWT."""

    id: int
    rol: str


def _decodificar(token: str) -> dict[str, Any]:
    """Valida firma y expiración; 401 si el token es inválido o expiró."""
    try:
        return jwt.decode(token, get_settings().JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("La sesión ha expirado. Inicie sesión nuevamente.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Credenciales inválidas.") from exc


def actor_desde_token(token: str | None) -> StaffActor:
    """Construye el ``StaffActor`` a partir de la cookie ``panel_token``."""
    if not token:
        raise UnauthorizedError("No autenticado. Inicie sesión en el panel.")
    claims = _decodificar(token)
    try:
        usuario_id = int(claims.get("sub") or "")
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Credenciales inválidas.") from exc
    rol = str(claims.get("rol") or "")
    if rol not in ROLES_STAFF:
        raise UnauthorizedError("Credenciales inválidas.")
    return StaffActor(id=usuario_id, rol=rol)


async def require_staff(request: Request) -> StaffActor:
    """Dependencia FastAPI: staff autenticado (tecnico|admin) o 401."""
    return actor_desde_token(request.cookies.get(PANEL_COOKIE))


async def require_admin(
    staff: Annotated[StaffActor, Depends(require_staff)],
) -> StaffActor:
    """Dependencia FastAPI: además del staff, exige rol admin (403 si no)."""
    if staff.rol != "admin":
        raise ForbiddenError("Se requiere rol administrador para esta operación.")
    return staff


__all__ = [
    "PANEL_COOKIE",
    "StaffActor",
    "actor_desde_token",
    "require_admin",
    "require_staff",
]
