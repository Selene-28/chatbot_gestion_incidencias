"""Cliente HTTP async hacia el ticket-service (contratos API-01..API-03, API-06).

- Base: settings.TICKETS_API_BASE_URL · Auth: header X-Api-Key (el widget
  NUNCA conoce esta clave; este servicio actúa de proxy).
- Timeout 5 s con 1 reintento SOLO para GET (prd/04 §5).
- Traduce los errores remotos a AppError locales:
    403 → ForbiddenError · 404 → NotFoundError · 409 → ConflictError ·
    400 → ValidationAppError · red caída/5xx → BusinessRuleError 422 con la
    disculpa de REN-05.
"""

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.dialogo.textos import DISCULPA_TICKETS_CAIDO

logger = logging.getLogger("app.clients.tickets")

TIMEOUT_S = 5.0
REINTENTOS_GET = 1


class TicketsClient:
    """Cliente del ticket-service con traducción de errores a AppError."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.TICKETS_API_BASE_URL).rstrip("/")
        self._api_key = api_key or settings.TICKETS_API_KEY
        self._timeout = timeout
        self._transport = transport  # inyectable en tests (httpx.MockTransport)

    # ------------------------------------------------------------------ interno

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"X-Api-Key": self._api_key}
        if extra:
            headers.update(extra)
        return headers

    async def _request(
        self,
        metodo: str,
        ruta: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ejecuta la petición (con 1 reintento solo para GET) y valida el envelope."""
        intentos = 1 + (REINTENTOS_GET if metodo == "GET" else 0)
        ultima_exc: Exception | None = None
        for intento in range(intentos):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url, timeout=self._timeout, transport=self._transport
                ) as client:
                    respuesta = await client.request(
                        metodo,
                        ruta,
                        json=json,
                        params=params,
                        headers=self._headers(headers),
                        files=files,
                    )
                return self._interpretar(respuesta)
            except httpx.HTTPError as exc:
                ultima_exc = exc
                logger.warning(
                    "Fallo de red hacia ticket-service (%s %s, intento %d/%d): %s",
                    metodo,
                    ruta,
                    intento + 1,
                    intentos,
                    exc,
                )
        raise BusinessRuleError(DISCULPA_TICKETS_CAIDO) from ultima_exc

    def _interpretar(self, respuesta: httpx.Response) -> dict[str, Any]:
        """Valida el envelope remoto; traduce errores a AppError locales."""
        try:
            cuerpo = respuesta.json()
        except ValueError:
            cuerpo = {}
        if respuesta.status_code < 400 and cuerpo.get("success"):
            return cuerpo.get("data") or {}

        mensaje = cuerpo.get("message") or ""
        errores = cuerpo.get("errors") or []
        codigo = respuesta.status_code
        if codigo in (401, 403):
            raise ForbiddenError(mensaje or None)
        if codigo == 404:
            raise NotFoundError(mensaje or None)
        if codigo == 409:
            raise ConflictError(mensaje or None)
        if codigo == 400:
            raise ValidationAppError(mensaje or None, errors=errores)
        if codigo == 422:
            raise BusinessRuleError(mensaje or None)
        logger.error(
            "Respuesta inesperada del ticket-service (%d): %s", codigo, mensaje or cuerpo
        )
        raise BusinessRuleError(DISCULPA_TICKETS_CAIDO)

    # ----------------------------------------------------------------- contratos

    async def registrar_incidencia(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        """API-01: crea una incidencia; devuelve {'ticketId', 'estado'}."""
        return await self._request(
            "POST",
            "/api/incidencias",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )

    async def consultar_ticket(self, codigo: str, correo: str) -> dict[str, Any]:
        """API-02: detalle de un ticket; RN-03 valida propiedad por correo."""
        return await self._request(
            "GET", f"/api/incidencias/{codigo}", params={"correo": correo}
        )

    async def listar_por_correo(self, correo: str) -> list[dict[str, Any]]:
        """API-02 (por correo): hasta 10 tickets del propietario, fecha desc."""
        data = await self._request("GET", "/api/incidencias", params={"correo": correo})
        return list(data.get("items") or [])

    async def escalar(self, codigo: str, motivo: str, correo: str) -> dict[str, Any]:
        """API-03: escala un ticket al personal técnico."""
        return await self._request(
            "PUT",
            "/api/incidencias/escalar",
            json={"ticketId": codigo, "motivo": motivo, "correo": correo},
        )

    async def registrar_encuesta(
        self,
        calificacion: int,
        comentario: str | None = None,
        ticket_id: str | None = None,
        conversacion_codigo: str | None = None,
    ) -> dict[str, Any]:
        """API-06: registra la encuesta (ticketId o conversacionCodigo, RN-04)."""
        return await self._request(
            "POST",
            "/api/encuesta",
            json={
                "ticketId": ticket_id,
                "conversacionCodigo": conversacion_codigo,
                "calificacion": calificacion,
                "comentario": comentario,
            },
        )

    async def resumen_metricas(self, desde: str, hasta: str) -> dict[str, Any]:
        """Métricas del lado de tickets para /api/metricas/resumen (RF-14).

        Devuelve ``ticketsPorEstado`` (conteo por estado), ``calificacionProm`` y
        ``encuestas`` (vista v_satisfaccion de tickets_db) en el rango de fechas.

        TODO(ticket-service): expone ``GET /api/metricas/tickets?desde&hasta``.
        Mientras no exista, la llamada devolverá 404 y el endpoint de métricas
        degrada a valores neutros (ticketsPorEstado={}, encuestas=0).
        """
        return await self._request(
            "GET", "/api/metricas/tickets", params={"desde": desde, "hasta": hasta}
        )

    async def subir_adjunto(self, filename: str, content: bytes, mime: str) -> dict[str, Any]:
        """API-01b: sube un adjunto previo al registro; devuelve {'adjuntoId'}."""
        return await self._request(
            "POST",
            "/api/incidencias/adjuntos",
            files={"file": (filename, content, mime)},
        )


_client: TicketsClient | None = None


def get_tickets_client() -> TicketsClient:
    """Singleton perezoso del cliente (los tests lo reemplazan vía monkeypatch)."""
    global _client
    if _client is None:
        _client = TicketsClient()
    return _client


def reset_tickets_client() -> None:
    """Descarta el singleton (útil al cambiar settings en tests)."""
    global _client
    _client = None


__all__ = [
    "AppError",
    "TicketsClient",
    "get_tickets_client",
    "reset_tickets_client",
]
