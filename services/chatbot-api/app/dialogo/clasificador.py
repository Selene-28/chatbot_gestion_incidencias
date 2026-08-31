"""Clasificador LLM — CAPA 2 del router de intenciones (prd/06 §2, tarea 4.2).

Solo se consulta cuando la capa 1 (reglas) no decide y el mensaje es texto
libre. Llamada corta a la API de Claude con structured outputs (JSON Schema
con `enum` de los 16 intents de prd/01 §2) a través de `app.ia.llm`.

Degradación silenciosa (prd/06 §6): si el LLM no está disponible, la llamada
falla o el JSON devuelto no cumple el esquema, se retorna None y el diálogo
sigue solo con la capa 1 (el mensaje alimenta el fallback F-09).
"""

import logging
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from app.core.config import get_settings
from app.dialogo.router import UMBRAL_CONFIANZA

logger = logging.getLogger("app.dialogo.clasificador")

MAX_TOKENS_ROUTER = 50  # prd/06 §5: max_tokens acotado para el router
TURNOS_HISTORIAL = 3  # prd/06 §2: últimos 3 turnos como contexto

# Los 16 intents de la matriz de prd/01 §2 (orden de la tabla)
INTENTS: tuple[str, ...] = (
    "registrar_incidencia",
    "consultar_estado",
    "faq_general",
    "recuperar_correo",
    "problema_internet",
    "problema_aula_virtual",
    "problema_software",
    "info_ctic",
    "escalar_incidencia",
    "contactar_soporte",
    "finalizar",
    "saludo",
    "agradecimiento",
    "despedida",
    "no_comprendida",
    "fuera_de_alcance",
)

# Prompt del sistema EXACTO de prd/06 §2
PROMPT_SISTEMA = (
    "Eres el clasificador de intenciones del Asistente Virtual del CTIC de la\n"
    "Universidad Nacional del Callao. Clasifica el mensaje del usuario en UNA de las\n"
    "intenciones del esquema. El dominio es exclusivamente soporte tecnológico\n"
    "universitario (correo institucional, WiFi, aula virtual, software institucional,\n"
    'tickets de soporte). Si el mensaje no pertenece al dominio → "fuera_de_alcance".\n'
    'Si es ininteligible o ambiguo → "no_comprendida".'
)

# JSON Schema para structured outputs (garantiza JSON válido, prd/06 §2)
ESQUEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "confianza": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["intent", "confianza"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Clasificacion:
    """Resultado de la capa 2: intención + confianza [0,1]."""

    intent: str
    confianza: float


def _modulo_llm() -> ModuleType:
    """Import diferido de `app.ia.llm` (se desarrolla en paralelo, tarea 4.x)."""
    from app.ia import llm

    return llm


def llm_activo() -> bool:
    """True si el cliente LLM existe y reporta disponibilidad (API key, etc.)."""
    try:
        return bool(_modulo_llm().llm_disponible())
    except Exception:  # ImportError incluido: sin módulo LLM → solo capa 1
        return False


def prompt_usuario(texto: str, historial: list[str]) -> str:
    """Mensaje de usuario del clasificador: historial breve + mensaje actual."""
    turnos = [t.strip() for t in historial[-TURNOS_HISTORIAL:] if t.strip()]
    breve = " | ".join(turnos) if turnos else "(sin historial)"
    return f"Historial breve: {breve}\nMensaje: {texto}"


def _validar(data: Any) -> Clasificacion | None:
    """Valida el dict devuelto por el LLM contra el esquema; None si no cumple."""
    if not isinstance(data, dict):
        return None
    intent = data.get("intent")
    confianza = data.get("confianza")
    if intent not in INTENTS:
        return None
    if isinstance(confianza, bool) or not isinstance(confianza, (int, float)):
        return None
    confianza = float(confianza)
    if not 0.0 <= confianza <= 1.0:
        return None
    return Clasificacion(intent=str(intent), confianza=confianza)


async def clasificar_intencion(texto: str, historial: list[str]) -> Clasificacion | None:
    """Clasifica texto libre con el LLM (capa 2).

    - None si el LLM no está disponible o la respuesta no cumple el esquema
      (degradación silenciosa a capa 1, prd/06 §6).
    - Confianza < 0.55 → se trata como `no_comprendida` (alimenta F-09).
    """
    try:
        llm = _modulo_llm()
    except ImportError:
        return None

    try:
        if not llm.llm_disponible():
            return None
        data = await llm.clasificar(
            PROMPT_SISTEMA,
            prompt_usuario(texto, historial),
            ESQUEMA,
            model=get_settings().LLM_MODEL_ROUTER,
            max_tokens=MAX_TOKENS_ROUTER,
        )
    except llm.LlmNoDisponible:
        logger.info("LLM no disponible para clasificar; se degrada a capa 1")
        return None
    except Exception:  # noqa: BLE001 — el diálogo nunca debe caerse por el LLM
        logger.warning("Fallo inesperado del clasificador LLM; se degrada a capa 1")
        return None

    resultado = _validar(data)
    if resultado is None:
        logger.warning("Respuesta del clasificador LLM fuera de esquema: %r", data)
        return None
    if resultado.confianza < UMBRAL_CONFIANZA:
        return Clasificacion(intent="no_comprendida", confianza=resultado.confianza)
    return resultado
