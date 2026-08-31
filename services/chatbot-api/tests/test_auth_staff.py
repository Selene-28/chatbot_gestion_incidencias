"""Unit: validación del JWT del staff (require_staff / require_admin)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.auth_staff import (
    StaffActor,
    actor_desde_token,
    require_admin,
    require_staff,
)
from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError


def _token(rol: str = "tecnico", sub: str = "7", exp_delta: timedelta | None = None) -> str:
    payload: dict = {"sub": sub, "rol": rol}
    if exp_delta is not None:
        payload["exp"] = datetime.now(UTC) + exp_delta
    return jwt.encode(payload, get_settings().JWT_SECRET, algorithm="HS256")


class _RequestFake:
    """Doble mínimo de fastapi.Request: solo expone ``cookies``."""

    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = cookies


# ------------------------------------------------------------- actor_desde_token


def test_actor_desde_token_valido():
    actor = actor_desde_token(_token(rol="admin", sub="42"))
    assert actor == StaffActor(id=42, rol="admin")


def test_actor_sin_token_401():
    with pytest.raises(UnauthorizedError):
        actor_desde_token(None)


def test_actor_token_expirado_401():
    token = _token(exp_delta=timedelta(hours=-1))
    with pytest.raises(UnauthorizedError):
        actor_desde_token(token)


def test_actor_firma_invalida_401():
    token = jwt.encode({"sub": "1", "rol": "admin"}, "otro-secreto", algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        actor_desde_token(token)


def test_actor_rol_desconocido_401():
    with pytest.raises(UnauthorizedError):
        actor_desde_token(_token(rol="alumno"))


def test_actor_sub_no_numerico_401():
    with pytest.raises(UnauthorizedError):
        actor_desde_token(_token(sub="no-numero"))


# --------------------------------------------------------- require_staff / admin


async def test_require_staff_devuelve_actor():
    req = _RequestFake({"panel_token": _token(rol="tecnico", sub="3")})
    actor = await require_staff(req)  # type: ignore[arg-type]
    assert actor.id == 3 and actor.rol == "tecnico"


async def test_require_staff_sin_cookie_401():
    with pytest.raises(UnauthorizedError):
        await require_staff(_RequestFake({}))  # type: ignore[arg-type]


async def test_require_admin_ok():
    actor = await require_admin(StaffActor(id=1, rol="admin"))
    assert actor.rol == "admin"


async def test_require_admin_rechaza_tecnico():
    with pytest.raises(ForbiddenError):
        await require_admin(StaffActor(id=2, rol="tecnico"))
