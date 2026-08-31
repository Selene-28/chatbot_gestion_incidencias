"""Dependencias FastAPI de autenticación del panel de agentes (staff).

El JWT del staff viaja en la cookie HttpOnly ``panel_token`` (prd/04 §1).
La cookie usa SameSite=Lax como mitigación CSRF: el navegador no la adjunta
en POST/PATCH originados desde otros sitios (prd/02 §7).

Nota de tipos: los parámetros inyectados por FastAPI se anotan como ``Any``
porque ``app.models`` (tarea 2.4) se desarrolla en paralelo y el import se
difiere al tiempo de ejecución; FastAPI no puede resolver forward refs de un
módulo aún inexistente.
"""

import os
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import JWT_EXPIRATION, decode_access_token

if TYPE_CHECKING:  # solo para tipado estático; en runtime el import es diferido
    from app.models import Usuario

PANEL_COOKIE = "panel_token"
ROLES_STAFF = ("tecnico", "admin")
LOGIN_URL = "/panel/login"


def cookie_secure() -> bool:
    """Flag ``Secure`` de la cookie del panel (True en producción tras HTTPS).

    TODO: mover a ``Settings`` (app/core/config.py) cuando el módulo deje de
    estar congelado por el trabajo en paralelo; mientras tanto se toma de la
    variable de entorno COOKIE_SECURE (default False en desarrollo).
    """
    valor = getattr(get_settings(), "COOKIE_SECURE", None)
    if valor is None:
        valor = os.environ.get("COOKIE_SECURE", "false")
    return str(valor).strip().lower() in ("1", "true", "yes", "on")


def set_panel_cookie(response: Response, token: str) -> None:
    """Adjunta el JWT como cookie HttpOnly SameSite=Lax (nunca va en el body)."""
    response.set_cookie(
        PANEL_COOKIE,
        token,
        max_age=int(JWT_EXPIRATION.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        path="/",
    )


def clear_panel_cookie(response: Response) -> None:
    """Elimina la cookie del panel (logout)."""
    response.delete_cookie(
        PANEL_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
    )


async def _cargar_staff(session: AsyncSession, usuario_id: int) -> "Usuario | None":
    """Carga el usuario por id. Import diferido: app.models es de la tarea 2.4."""
    from app.models import Usuario

    return await session.get(Usuario, usuario_id)


async def _autenticar_por_cookie(request: Request, session: AsyncSession) -> "Usuario":
    """Valida la cookie ``panel_token`` y devuelve el staff activo; 401 si no."""
    token = request.cookies.get(PANEL_COOKIE)
    if not token:
        raise UnauthorizedError("No autenticado. Inicie sesión en el panel.")
    claims: dict[str, Any] = decode_access_token(token)  # 401 si firma/exp inválidas
    try:
        usuario_id = int(claims.get("sub") or "")
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Credenciales inválidas.") from exc
    usuario = await _cargar_staff(session, usuario_id)
    if usuario is None or not usuario.activo or usuario.rol not in ROLES_STAFF:
        raise UnauthorizedError("Credenciales inválidas.")
    return usuario


async def require_staff(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Any:
    """Dependencia JSON: staff autenticado (tecnico|admin) o 401 UnauthorizedError."""
    return await _autenticar_por_cookie(request, session)


async def staff_opcional(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Any:
    """Variante para rutas HTML: devuelve None en lugar de lanzar 401.

    La ruta HTML decide la respuesta apta para navegador: redirect 303 a
    /panel/login (o HX-Redirect si la petición viene de htmx).
    """
    try:
        return await _autenticar_por_cookie(request, session)
    except UnauthorizedError:
        return None


async def require_admin(usuario: Annotated[Any, Depends(require_staff)]) -> Any:
    """Dependencia JSON: además del staff, exige rol admin (403 si no)."""
    if usuario.rol != "admin":
        raise ForbiddenError("Se requiere rol administrador para esta operación.")
    return usuario
