"""Motor genérico de máquinas de estado conversacionales (Dialog Manager).

El estado vive SOLO en la BD (`conversaciones.flujo_activo` + `flujo_contexto`
JSON), por lo que un flujo en curso sobrevive a reinicios del servicio
(criterio 3.2). Estructura de `flujo_contexto`:

    {
      "paso":     "descripcion",     # paso actual del flujo activo
      "datos":    { ... },           # datos parciales capturados por el flujo
      "intentos": 0,                 # entradas inválidas seguidas en el paso
      "sesion":   { ... }            # contexto de sesión que SOBREVIVE al flujo
    }                                #  (último ticket, encuesta ofrecida, etc.)

Entrada inválida: el flujo re-solicita el dato; al 3.er intento inválido en el
MISMO paso el motor abandona el flujo y lanza `FallbackDeFlujo` para que el
orquestador dispare el fallback global F-09.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.dialogo.tipos import Entrada, MensajeBot
from app.models import Conversacion

logger = logging.getLogger("app.dialogo.engine")

MAX_INTENTOS_INVALIDOS = 3


class FallbackDeFlujo(Exception):
    """Tres entradas inválidas seguidas en un paso: abandonar y disparar F-09."""


@dataclass
class Deps:
    """Dependencias que el motor inyecta a los flujos."""

    session: AsyncSession
    tickets: Any  # TicketsClient (Any para permitir dobles de prueba)


@dataclass
class Resultado:
    """Salida de un paso de flujo."""

    mensajes: list[MensajeBot] = field(default_factory=list)
    paso: str | None = None  # siguiente paso; None mantiene el actual
    terminar: bool = False  # el flujo terminó (éxito o cancelación)
    invalida: bool = False  # la entrada no fue válida para el paso
    # Encadenamiento: al terminar, iniciar este flujo con datos pre-llenados
    # (F-05 → F-02: el diagnóstico pre-llena el registro de incidencia).
    siguiente_flujo: str | None = None
    siguiente_datos: dict[str, Any] | None = None


class Flujo(Protocol):
    """Contrato de una máquina de estados conversacional."""

    nombre: str

    async def iniciar(
        self, conv: Conversacion, ctx: dict[str, Any], deps: Deps
    ) -> Resultado: ...

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado: ...


def contexto_de(conv: Conversacion) -> dict[str, Any]:
    """Contexto de flujo normalizado (copia mutable del JSON persistido)."""
    crudo = dict(conv.flujo_contexto or {})
    return {
        "paso": crudo.get("paso"),
        "datos": dict(crudo.get("datos") or {}),
        "intentos": int(crudo.get("intentos") or 0),
        "sesion": dict(crudo.get("sesion") or {}),
    }


def sesion_de(conv: Conversacion) -> dict[str, Any]:
    """Contexto de sesión (parte de flujo_contexto que sobrevive a los flujos)."""
    return contexto_de(conv)["sesion"]


def guardar_sesion(conv: Conversacion, sesion: dict[str, Any]) -> None:
    """Actualiza solo la parte de sesión del contexto persistido."""
    ctx = contexto_de(conv)
    ctx["sesion"] = sesion
    conv.flujo_contexto = ctx


class Engine:
    """Ejecuta flujos registrados sobre el estado persistido de la conversación."""

    def __init__(self, flujos: list[Flujo]) -> None:
        self._flujos: dict[str, Flujo] = {f.nombre: f for f in flujos}

    def flujo(self, nombre: str) -> Flujo:
        """Devuelve un flujo registrado por nombre."""
        return self._flujos[nombre]

    async def iniciar(
        self,
        conv: Conversacion,
        nombre: str,
        deps: Deps,
        datos_iniciales: dict[str, Any] | None = None,
    ) -> list[MensajeBot]:
        """Activa un flujo (descarta cualquier flujo previo, preserva la sesión)."""
        flujo = self._flujos[nombre]
        ctx = contexto_de(conv)
        ctx.update({"paso": None, "datos": dict(datos_iniciales or {}), "intentos": 0})
        resultado = await flujo.iniciar(conv, ctx, deps)
        self._aplicar(conv, nombre, ctx, resultado)
        return resultado.mensajes

    async def procesar(self, conv: Conversacion, entrada: Entrada, deps: Deps) -> list[MensajeBot]:
        """Procesa la entrada del usuario en el paso actual del flujo activo."""
        nombre = conv.flujo_activo
        if not nombre or nombre not in self._flujos:
            raise FallbackDeFlujo(f"flujo desconocido o inactivo: {nombre!r}")
        flujo = self._flujos[nombre]
        ctx = contexto_de(conv)
        paso = ctx["paso"] or ""

        resultado = await flujo.procesar(conv, paso, entrada, ctx, deps)

        if resultado.invalida:
            ctx["intentos"] += 1
            if ctx["intentos"] >= MAX_INTENTOS_INVALIDOS:
                logger.info(
                    "Flujo %s abandonado en paso %s tras %d entradas inválidas (conv %s)",
                    nombre,
                    paso,
                    ctx["intentos"],
                    conv.codigo,
                )
                self.cancelar(conv)
                raise FallbackDeFlujo(f"{MAX_INTENTOS_INVALIDOS} entradas inválidas en {paso}")
            self._aplicar(conv, nombre, ctx, Resultado(paso=ctx["paso"]))
            return resultado.mensajes

        ctx["intentos"] = 0
        self._aplicar(conv, nombre, ctx, resultado)
        # Encadenamiento F-05 → F-02: al terminar, arranca el siguiente flujo
        # con los datos pre-llenados (la sesión se preserva en _aplicar).
        if resultado.terminar and resultado.siguiente_flujo:
            siguientes = await self.iniciar(
                conv, resultado.siguiente_flujo, deps, resultado.siguiente_datos
            )
            return resultado.mensajes + siguientes
        return resultado.mensajes

    def cancelar(self, conv: Conversacion) -> None:
        """Descarta el flujo activo y sus datos parciales; preserva la sesión."""
        sesion = sesion_de(conv)
        conv.flujo_activo = None
        conv.flujo_contexto = {"paso": None, "datos": {}, "intentos": 0, "sesion": sesion}

    def _aplicar(
        self, conv: Conversacion, nombre: str, ctx: dict[str, Any], resultado: Resultado
    ) -> None:
        """Persiste el nuevo estado del flujo en la conversación."""
        if resultado.terminar:
            self.cancelar(conv)
            # los flujos pueden haber actualizado la sesión dentro de ctx
            conv.flujo_contexto = {
                "paso": None,
                "datos": {},
                "intentos": 0,
                "sesion": ctx["sesion"],
            }
            return
        if resultado.paso is not None:
            ctx["paso"] = resultado.paso
        conv.flujo_activo = nombre
        # asignación completa: garantiza que SQLAlchemy detecte el cambio del JSON
        conv.flujo_contexto = {
            "paso": ctx["paso"],
            "datos": ctx["datos"],
            "intentos": ctx["intentos"],
            "sesion": ctx["sesion"],
        }
