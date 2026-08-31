"""Doble de prueba del contrato `app.ia.llm` (se desarrolla en paralelo).

Instala en `sys.modules` un módulo falso con la interfaz acordada:

    class LlmNoDisponible(Exception): ...
    def llm_disponible() -> bool
    async def clasificar(system, user, schema, *, model=None, max_tokens=50) -> dict

La `ANTHROPIC_API_KEY` del entorno es un placeholder, por lo que TODOS los
tests que tocan el LLM usan este doble; el camino sin LLM se prueba aparte.
"""

import sys
import types
from typing import Any

import pytest


def instalar_llm_falso(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Registra `app.ia.llm` falso en sys.modules y devuelve el módulo.

    Atributos de control del doble:
    - `respuesta`: dict que devolverá `clasificar`.
    - `excepcion`: si no es None, `clasificar` la lanza.
    - `disponible`: valor que devuelve `llm_disponible()`.
    - `llamadas`: registro de argumentos de cada llamada a `clasificar`.
    """
    modulo = types.ModuleType("app.ia.llm")

    class LlmNoDisponible(Exception):
        """Réplica de la excepción del contrato."""

    llamadas: list[dict[str, Any]] = []
    modulo.LlmNoDisponible = LlmNoDisponible  # type: ignore[attr-defined]
    modulo.llamadas = llamadas  # type: ignore[attr-defined]
    modulo.respuesta = {"intent": "faq_general", "confianza": 0.9}  # type: ignore[attr-defined]
    modulo.excepcion = None  # type: ignore[attr-defined]
    modulo.disponible = True  # type: ignore[attr-defined]

    def llm_disponible() -> bool:
        return bool(modulo.disponible)  # type: ignore[attr-defined]

    async def clasificar(
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        model: str | None = None,
        max_tokens: int = 50,
    ) -> dict[str, Any]:
        llamadas.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        if modulo.excepcion is not None:  # type: ignore[attr-defined]
            raise modulo.excepcion  # type: ignore[attr-defined]
        return dict(modulo.respuesta)  # type: ignore[attr-defined]

    modulo.llm_disponible = llm_disponible  # type: ignore[attr-defined]
    modulo.clasificar = clasificar  # type: ignore[attr-defined]

    paquete = types.ModuleType("app.ia")
    paquete.llm = modulo  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.ia", paquete)
    monkeypatch.setitem(sys.modules, "app.ia.llm", modulo)
    return modulo


@pytest.fixture()
def llm_falso(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Fixture: módulo `app.ia.llm` falso instalado en sys.modules."""
    return instalar_llm_falso(monkeypatch)


@pytest.fixture()
def sin_modulo_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture: simula que `app.ia` NO existe (import → ImportError)."""
    monkeypatch.setitem(sys.modules, "app.ia", None)
    monkeypatch.setitem(sys.modules, "app.ia.llm", None)
