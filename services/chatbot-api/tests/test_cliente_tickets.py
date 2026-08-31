"""Cliente hacia ticket-service: traducción de errores y política de reintentos."""

import json
from typing import Any

import httpx
import pytest

from app.clients.tickets import TicketsClient
from app.core.errors import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.dialogo.textos import DISCULPA_TICKETS_CAIDO


def _cliente(handler) -> TicketsClient:
    return TicketsClient(
        base_url="http://tickets.test",
        api_key="clave-test",
        transport=httpx.MockTransport(handler),
    )


def _respuesta(code: int, message: str = "err", data: Any = None) -> httpx.Response:
    if code < 400:
        cuerpo = {"success": True, "code": code, "message": message, "data": data or {}}
    else:
        cuerpo = {"success": False, "code": code, "message": message, "errors": []}
    return httpx.Response(code, json=cuerpo)


async def test_registrar_envia_api_key_e_idempotency():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["headers"] = request.headers
        capturado["body"] = json.loads(request.content)
        return _respuesta(201, data={"ticketId": "INC-2026-0001", "estado": "Registrado"})

    data = await _cliente(handler).registrar_incidencia({"nombre": "Ana"}, "clave-idem")
    assert data["ticketId"] == "INC-2026-0001"
    assert capturado["headers"]["X-Api-Key"] == "clave-test"
    assert capturado["headers"]["Idempotency-Key"] == "clave-idem"


@pytest.mark.parametrize(
    ("codigo", "excepcion"),
    [(403, ForbiddenError), (404, NotFoundError), (409, ConflictError), (400, ValidationAppError)],
)
async def test_traduccion_de_errores(codigo: int, excepcion: type[Exception]):
    def handler(request: httpx.Request) -> httpx.Response:
        return _respuesta(codigo, message="mensaje remoto")

    with pytest.raises(excepcion) as exc:
        await _cliente(handler).consultar_ticket("INC-2026-0001", "a@unac.edu.pe")
    assert exc.value.message == "mensaje remoto"  # type: ignore[attr-defined]


async def test_red_caida_disculpa_ren05():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conexión rechazada")

    with pytest.raises(BusinessRuleError) as exc:
        await _cliente(handler).escalar("INC-2026-0001", "motivo suficiente", "a@unac.edu.pe")
    assert exc.value.message == DISCULPA_TICKETS_CAIDO
    assert exc.value.code == 422


async def test_get_reintenta_una_vez():
    intentos = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise httpx.ConnectTimeout("timeout")
        return _respuesta(200, data={"ticketId": "INC-2026-0001"})

    data = await _cliente(handler).consultar_ticket("INC-2026-0001", "a@unac.edu.pe")
    assert data["ticketId"] == "INC-2026-0001"
    assert intentos["n"] == 2  # 1 fallo + 1 reintento (solo GET)


async def test_post_no_reintenta():
    intentos = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        intentos["n"] += 1
        raise httpx.ConnectError("conexión rechazada")

    with pytest.raises(BusinessRuleError):
        await _cliente(handler).registrar_incidencia({}, "clave")
    assert intentos["n"] == 1  # sin reintentos para POST


async def test_5xx_disculpa_generica():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"success": False, "code": 500, "message": "boom"})

    with pytest.raises(BusinessRuleError) as exc:
        await _cliente(handler).registrar_encuesta(5, conversacion_codigo="abc")
    assert exc.value.message == DISCULPA_TICKETS_CAIDO
