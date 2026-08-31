"""Pruebas de seguridad: Argon2id, JWT HS256 y API key de servicio."""

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    require_api_key,
    verify_password,
)
from app.main import create_app

# --- Argon2id ---


def test_hash_y_verificacion_correcta() -> None:
    hashed = hash_password("cambiar123")
    assert hashed.startswith("$argon2id$")  # variante Argon2id, no i/d
    assert verify_password("cambiar123", hashed) is True


def test_verificacion_rechaza_password_incorrecta() -> None:
    hashed = hash_password("cambiar123")
    assert verify_password("otra-clave", hashed) is False


def test_verificacion_tolera_hash_corrupto() -> None:
    assert verify_password("cambiar123", "no-es-un-hash") is False


def test_hashes_distintos_por_salt() -> None:
    assert hash_password("cambiar123") != hash_password("cambiar123")


# --- JWT ---


def test_jwt_crea_y_valida_claims() -> None:
    token = create_access_token(sub="admin@ctic.local", rol="admin")
    claims = decode_access_token(token)
    assert claims["sub"] == "admin@ctic.local"
    assert claims["rol"] == "admin"
    # Expiración ~8 horas
    vida = claims["exp"] - claims["iat"]
    assert vida == 8 * 3600


def test_jwt_expirado_lanza_unauthorized() -> None:
    ahora = datetime.now(UTC)
    token = pyjwt.encode(
        {"sub": "x", "rol": "tecnico", "iat": ahora - timedelta(hours=9),
         "exp": ahora - timedelta(hours=1)},
        get_settings().JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)


def test_jwt_con_firma_invalida_lanza_unauthorized() -> None:
    token = pyjwt.encode(
        {"sub": "x", "rol": "admin"},
        "otro-secreto-igualmente-largo-para-hs256-xx",
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)


# --- API key de servicio (X-Api-Key) ---


def _app_protegida() -> TestClient:
    app = create_app()

    @app.get("/protegido", dependencies=[Depends(require_api_key)])
    async def protegido() -> dict:
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_api_key_correcta_permite_acceso() -> None:
    client = _app_protegida()
    response = client.get(
        "/protegido", headers={"X-Api-Key": get_settings().TICKETS_API_KEY}
    )
    assert response.status_code == 200


def test_api_key_incorrecta_devuelve_401_con_envelope() -> None:
    client = _app_protegida()
    response = client.get("/protegido", headers={"X-Api-Key": "clave-erronea"})
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["code"] == 401
    assert body["message"]


def test_api_key_ausente_devuelve_401() -> None:
    client = _app_protegida()
    response = client.get("/protegido")
    assert response.status_code == 401
    assert response.json()["success"] is False
