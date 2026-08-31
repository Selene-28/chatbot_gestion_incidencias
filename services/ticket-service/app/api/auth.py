"""Autenticación del staff del panel de agentes (prd/04 §1, RF-11).

- Login con correo/contraseña (Argon2id) → JWT HS256 (sub=id, rol, exp 8 h)
  en cookie HttpOnly SameSite=Lax; el token nunca viaja en el body.
- Contra fuerza bruta: retardo fijo ante fallo y mensaje genérico que no
  revela si el correo existe (prd/02 §7).
"""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import ROLES_STAFF, clear_panel_cookie, set_panel_cookie
from app.core.envelope import ok
from app.core.errors import UnauthorizedError
from app.core.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Retardo fijo (~0.5 s) ante credenciales inválidas: encarece la fuerza bruta
# y uniformiza el tiempo de respuesta (evita enumeración de correos por timing).
RETARDO_LOGIN_FALLIDO_S = 0.5
MENSAJE_CREDENCIALES_INVALIDAS = "Credenciales inválidas."

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class LoginRequest(BaseModel):
    """Cuerpo de POST /api/auth/login."""

    correo: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=1, max_length=128)


async def _buscar_staff(session: AsyncSession, correo: str) -> Any:
    """Busca el usuario por correo. Import diferido: app.models es de la tarea 2.4."""
    from sqlalchemy import select

    from app.models import Usuario

    return await session.scalar(select(Usuario).where(Usuario.correo == correo))


async def autenticar_staff(session: AsyncSession, correo: str, password: str) -> Any:
    """Valida credenciales de staff; lanza 401 genérico si algo no cuadra.

    El mensaje es siempre el mismo (correo inexistente, contraseña incorrecta,
    usuario inactivo o sin rol de staff) para no filtrar información.
    """
    usuario = await _buscar_staff(session, correo)
    password_hash = getattr(usuario, "password_hash", None) or ""
    password_ok = bool(password_hash) and verify_password(password, password_hash)
    es_staff = (
        usuario is not None and bool(usuario.activo) and usuario.rol in ROLES_STAFF
    )
    if not (password_ok and es_staff):
        await asyncio.sleep(RETARDO_LOGIN_FALLIDO_S)
        raise UnauthorizedError(MENSAJE_CREDENCIALES_INVALIDAS)
    return usuario


@router.post("/login")
async def login(body: LoginRequest, session: SessionDep) -> JSONResponse:
    """Emite el JWT del panel como cookie HttpOnly; el body solo lleva rol y nombre."""
    usuario = await autenticar_staff(session, body.correo, body.password)
    token = create_access_token(str(usuario.id), usuario.rol)
    respuesta = ok({"rol": usuario.rol, "nombre": usuario.nombre}, "Inicio de sesión correcto.")
    set_panel_cookie(respuesta, token)
    return respuesta


@router.post("/logout")
async def logout() -> JSONResponse:
    """Cierra la sesión del panel eliminando la cookie."""
    respuesta = ok({}, "Sesión cerrada correctamente.")
    clear_panel_cookie(respuesta)
    return respuesta
