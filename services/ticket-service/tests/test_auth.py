"""Pruebas de autenticación del staff (tarea 2.5): login, cookie y roles.

El dominio (app.models / app.services.tickets, tarea 2.4) se desarrolla en
paralelo: aquí se mockean los puntos de acceso a datos (_buscar_staff,
_cargar_staff), por lo que estas pruebas no requieren MySQL ni el dominio.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Annotated, Any

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api.auth import router as auth_router
from app.api.panel import router as panel_router
from app.core import deps
from app.core.config import get_settings
from app.core.security import JWT_ALGORITHM, create_access_token, hash_password
from app.main import create_app
from app.panel import consultas

PASSWORD = "secreta123"
PASSWORD_HASH = hash_password(PASSWORD)  # una sola vez: Argon2 es costoso a propósito


def _staff(rol: str = "tecnico", activo: bool = True, con_password: bool = True) -> Any:
    return SimpleNamespace(
        id=7,
        nombre="Carlos Ramírez",
        correo="tecnico1@ctic.local",
        rol=rol,
        password_hash=PASSWORD_HASH if con_password else None,
        activo=activo,
    )


@pytest.fixture()
def app_auth() -> FastAPI:
    """App con los routers de auth y panel JSON (main.py los cablea aparte)."""
    app = create_app()
    app.include_router(auth_router)
    app.include_router(panel_router)

    # Ruta ad-hoc para probar require_admin (aún no hay endpoints admin reales).
    @app.get("/api/prueba-admin")
    async def solo_admin(usuario: Annotated[Any, Depends(deps.require_admin)]) -> dict:
        return {"rol": usuario.rol}

    return app


@pytest.fixture()
def cliente(app_auth: FastAPI) -> TestClient:
    return TestClient(app_auth, raise_server_exceptions=False)


def _mock_busqueda(monkeypatch: pytest.MonkeyPatch, usuario: Any) -> None:
    async def buscar(session: Any, correo: str) -> Any:
        return usuario if usuario and correo == usuario.correo else None

    monkeypatch.setattr(auth_api, "_buscar_staff", buscar)
    monkeypatch.setattr(auth_api, "RETARDO_LOGIN_FALLIDO_S", 0)


# --------------------------------------------------------------------------- #
# POST /api/auth/login
# --------------------------------------------------------------------------- #


def test_login_ok_setea_cookie_httponly_sin_token_en_body(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_busqueda(monkeypatch, _staff())
    r = cliente.post(
        "/api/auth/login", json={"correo": "tecnico1@ctic.local", "password": PASSWORD}
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["success"] is True
    assert cuerpo["data"] == {"rol": "tecnico", "nombre": "Carlos Ramírez"}

    set_cookie = r.headers["set-cookie"]
    assert "panel_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    # En dev COOKIE_SECURE=False: sin flag Secure
    assert "secure" not in set_cookie.lower()
    # El JWT viaja solo en la cookie, nunca en el body
    token = cliente.cookies.get("panel_token")
    assert token and token not in r.text


def test_login_credenciales_malas_401_generico(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_busqueda(monkeypatch, _staff())
    # Contraseña incorrecta y correo inexistente: el mismo mensaje genérico
    for payload in (
        {"correo": "tecnico1@ctic.local", "password": "incorrecta"},
        {"correo": "noexiste@ctic.local", "password": PASSWORD},
    ):
        r = cliente.post("/api/auth/login", json=payload)
        assert r.status_code == 401
        assert r.json()["message"] == "Credenciales inválidas."
        assert "set-cookie" not in r.headers


def test_login_rechaza_staff_inactivo_y_rol_usuario(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for usuario in (_staff(activo=False), _staff(rol="usuario"), _staff(con_password=False)):
        _mock_busqueda(monkeypatch, usuario)
        r = cliente.post(
            "/api/auth/login", json={"correo": usuario.correo, "password": PASSWORD}
        )
        assert r.status_code == 401
        assert r.json()["message"] == "Credenciales inválidas."


# --------------------------------------------------------------------------- #
# POST /api/auth/logout
# --------------------------------------------------------------------------- #


def test_logout_borra_cookie(cliente: TestClient) -> None:
    r = cliente.post("/api/auth/logout")
    assert r.status_code == 200
    set_cookie = r.headers["set-cookie"].lower()
    assert "panel_token=" in set_cookie
    assert 'max-age=0' in set_cookie or "expires=" in set_cookie


# --------------------------------------------------------------------------- #
# require_staff / require_admin
# --------------------------------------------------------------------------- #


def test_require_staff_rechaza_sin_cookie(cliente: TestClient) -> None:
    r = cliente.get("/api/panel/tecnicos")
    assert r.status_code == 401
    assert r.json()["success"] is False


def test_require_staff_rechaza_jwt_expirado(cliente: TestClient) -> None:
    vencido = jwt.encode(
        {"sub": "7", "rol": "tecnico", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        get_settings().JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    cliente.cookies.set("panel_token", vencido)
    r = cliente.get("/api/panel/tecnicos")
    assert r.status_code == 401


def test_require_staff_rechaza_firma_invalida(cliente: TestClient) -> None:
    ajeno = jwt.encode(
        {"sub": "7", "rol": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "otro-secreto-que-no-es-el-del-servicio",
        algorithm=JWT_ALGORITHM,
    )
    cliente.cookies.set("panel_token", ajeno)
    r = cliente.get("/api/panel/tecnicos")
    assert r.status_code == 401


def test_require_staff_acepta_tecnico_valido(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tecnico = _staff()

    async def cargar(session: Any, usuario_id: int) -> Any:
        return tecnico if usuario_id == tecnico.id else None

    async def tecnicos(session: Any) -> list:
        return [tecnico]

    monkeypatch.setattr(deps, "_cargar_staff", cargar)
    monkeypatch.setattr(consultas, "listar_tecnicos", tecnicos)
    cliente.cookies.set("panel_token", create_access_token("7", "tecnico"))
    r = cliente.get("/api/panel/tecnicos")
    assert r.status_code == 200
    assert r.json()["data"]["items"][0]["nombre"] == "Carlos Ramírez"


def test_require_admin_rechaza_tecnico(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tecnico = _staff(rol="tecnico")

    async def cargar(session: Any, usuario_id: int) -> Any:
        return tecnico

    monkeypatch.setattr(deps, "_cargar_staff", cargar)
    cliente.cookies.set("panel_token", create_access_token("7", "tecnico"))
    r = cliente.get("/api/prueba-admin")
    assert r.status_code == 403
    assert r.json()["success"] is False


def test_require_admin_acepta_admin(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _staff(rol="admin")

    async def cargar(session: Any, usuario_id: int) -> Any:
        return admin

    monkeypatch.setattr(deps, "_cargar_staff", cargar)
    cliente.cookies.set("panel_token", create_access_token("7", "admin"))
    r = cliente.get("/api/prueba-admin")
    assert r.status_code == 200
    assert r.json() == {"rol": "admin"}
