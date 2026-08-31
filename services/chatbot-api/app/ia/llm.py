"""Wrapper del SDK oficial `anthropic` (prd/06 §2-§3, §6) — CONTRATO COMPARTIDO.

Este módulo es la ÚNICA puerta hacia la API de Claude. Expone:

- ``llm_disponible()``  — False si no hay API key o el circuit breaker está abierto.
- ``clasificar(...)``   — structured outputs (JSON garantizado) para el router capa 2.
- ``generar_stream(...)`` — streaming de texto para la generación RAG.
- ``estado_llm()``      — "configured" | "degraded" | "disabled" para /healthz.

Degradación (prd/06 §6): toda excepción de la API (RateLimitError, APIStatusError,
APIConnectionError, ...) se mapea a ``LlmNoDisponible``; tras 3 fallos consecutivos
el circuit breaker se abre 60 s (medio-abierto después: se permite 1 intento).

NO usar ``temperature``: retirado en los modelos actuales; la consistencia (RN-07)
viene del prompt estricto y de las respuestas ancladas a artículos.
"""

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.core.config import get_settings

logger = logging.getLogger("app.ia.llm")

# Circuit breaker (prd/06 §6): 3 fallos consecutivos → abierto 60 s
FALLOS_PARA_ABRIR = 3
SEGUNDOS_ABIERTO = 60.0

_client: anthropic.AsyncAnthropic | None = None
_fallos_consecutivos = 0
_abierto_hasta = 0.0  # time.monotonic() hasta el cual el breaker está abierto
_tokens_consumidos = 0  # acumulado de tokens (input+output) para métricas (RF-14)


class LlmNoDisponible(Exception):
    """El LLM no puede atender: sin key, breaker abierto o error de la API."""


# ------------------------------------------------------------------ estado


def _hay_key() -> bool:
    return bool(get_settings().ANTHROPIC_API_KEY)


def _breaker_abierto() -> bool:
    """True mientras dura la ventana de apertura (medio-abierto al expirar)."""
    return time.monotonic() < _abierto_hasta


def llm_disponible() -> bool:
    """False si no hay key configurada o el circuit breaker está abierto."""
    return _hay_key() and not _breaker_abierto()


def estado_llm() -> str:
    """Estado para /healthz: configured | degraded (breaker abierto) | disabled."""
    if not _hay_key():
        return "disabled"
    if _breaker_abierto():
        return "degraded"
    return "configured"


def _registrar_fallo() -> None:
    global _fallos_consecutivos, _abierto_hasta
    _fallos_consecutivos += 1
    if _fallos_consecutivos >= FALLOS_PARA_ABRIR:
        _abierto_hasta = time.monotonic() + SEGUNDOS_ABIERTO
        logger.warning(
            "Circuit breaker LLM abierto por %.0f s tras %d fallos consecutivos",
            SEGUNDOS_ABIERTO,
            _fallos_consecutivos,
        )


def _registrar_exito() -> None:
    global _fallos_consecutivos, _abierto_hasta
    _fallos_consecutivos = 0
    _abierto_hasta = 0.0


def reset_estado() -> None:
    """Reinicia cliente y breaker (tests y cambios de configuración)."""
    global _client, _fallos_consecutivos, _abierto_hasta
    _client = None
    _fallos_consecutivos = 0
    _abierto_hasta = 0.0


def tokens_consumidos() -> int:
    """Total acumulado de tokens LLM (input+output) desde el arranque (RF-14).

    Alimenta ``tokensLlm`` de /api/metricas/resumen; es 0 mientras no haya key
    (sin llamadas al LLM). El contador es best-effort en el proceso vivo.
    """
    return _tokens_consumidos


def _sumar_tokens(respuesta: Any) -> None:
    """Suma los tokens de una respuesta de la API (tolerante a dobles de prueba)."""
    global _tokens_consumidos
    try:
        uso = respuesta.usage
        _tokens_consumidos += int(uso.input_tokens) + int(uso.output_tokens)
    except (AttributeError, TypeError, ValueError):  # dobles de prueba sin usage
        return


def _get_client() -> anthropic.AsyncAnthropic:
    """Cliente async singleton (la key viene de settings, nunca hardcodeada)."""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=get_settings().ANTHROPIC_API_KEY)
    return _client


def _verificar_disponible() -> None:
    if not _hay_key():
        raise LlmNoDisponible("ANTHROPIC_API_KEY no configurada")
    if _breaker_abierto():
        raise LlmNoDisponible("circuit breaker abierto")


def _bloques_system(system: str) -> list[Any]:
    """System como bloque cacheable (prompt caching: lo estable va primero).

    Devuelve ``list[Any]`` a propósito: el bloque coincide con el ``TextBlockParam``
    del SDK sin acoplar este wrapper a sus tipos internos.
    """
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


# ------------------------------------------------------------------ llamadas


async def clasificar(
    system: str,
    user: str,
    schema: dict,
    *,
    model: str | None = None,
    max_tokens: int = 50,
) -> dict:
    """Clasificación con structured outputs: devuelve el JSON parseado.

    Usa ``settings.LLM_MODEL_ROUTER`` por defecto (modelo económico, prd/06 §2).
    Lanza ``LlmNoDisponible`` si no hay key, el breaker está abierto o la API falla.
    """
    _verificar_disponible()
    try:
        respuesta = await _get_client().messages.create(
            model=model or get_settings().LLM_MODEL_ROUTER,
            max_tokens=max_tokens,
            system=_bloques_system(system),
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except (
        anthropic.RateLimitError,
        anthropic.APIStatusError,
        anthropic.APIConnectionError,
    ) as exc:
        _registrar_fallo()
        raise LlmNoDisponible(f"error de la API del LLM: {exc.__class__.__name__}") from exc

    _registrar_exito()
    _sumar_tokens(respuesta)
    texto = next((b.text for b in respuesta.content if b.type == "text"), None)
    if texto is None:
        raise LlmNoDisponible("respuesta del LLM sin bloque de texto")
    try:
        resultado: dict = json.loads(texto)
    except json.JSONDecodeError as exc:  # no debería ocurrir con structured outputs
        raise LlmNoDisponible("respuesta del LLM no es JSON válido") from exc
    return resultado


async def generar_stream(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 400,
) -> AsyncIterator[str]:
    """Generación en streaming: cede fragmentos de texto según llegan.

    Usa ``settings.LLM_MODEL`` por defecto (prd/06 §5). Lanza ``LlmNoDisponible``
    si no hay key, el breaker está abierto o la API falla (incluso a mitad de stream).
    """
    _verificar_disponible()
    try:
        async with _get_client().messages.stream(
            model=model or get_settings().LLM_MODEL,
            max_tokens=max_tokens,
            system=_bloques_system(system),
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for texto in stream.text_stream:
                yield texto
            try:  # el uso solo está disponible al cerrar el stream
                _sumar_tokens(await stream.get_final_message())
            except (AttributeError, TypeError):  # dobles de prueba sin final message
                pass
    except (
        anthropic.RateLimitError,
        anthropic.APIStatusError,
        anthropic.APIConnectionError,
    ) as exc:
        _registrar_fallo()
        raise LlmNoDisponible(f"error de la API del LLM: {exc.__class__.__name__}") from exc
    _registrar_exito()
