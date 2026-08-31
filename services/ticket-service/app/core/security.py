"""Seguridad base: hash Argon2id, JWT HS256 y validación de API key de servicio."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import Header

from app.core.config import get_settings
from app.core.errors import UnauthorizedError

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = timedelta(hours=8)  # prd/04 §1: JWT staff expira a las 8 h

# Argon2id es el modo por defecto de argon2-cffi
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hashea una contraseña con Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña contra su hash Argon2id."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False


def create_access_token(sub: str, rol: str) -> str:
    """Crea un JWT HS256 con claims sub y rol, expiración de 8 horas."""
    now = datetime.now(UTC)
    payload = {"sub": sub, "rol": rol, "iat": now, "exp": now + JWT_EXPIRATION}
    return jwt.encode(payload, get_settings().JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Valida y decodifica un JWT; lanza UnauthorizedError si es inválido o expiró."""
    try:
        return jwt.decode(token, get_settings().JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("La sesión ha expirado. Inicie sesión nuevamente.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Credenciales inválidas.") from exc


async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
) -> None:
    """Dependencia FastAPI: valida el header X-Api-Key de servicios (prd/04 §1)."""
    if x_api_key != get_settings().TICKETS_API_KEY:
        raise UnauthorizedError("Credenciales de servicio inválidas.")
