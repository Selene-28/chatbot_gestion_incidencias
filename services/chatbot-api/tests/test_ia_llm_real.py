"""Marker `llm`: 1 clasificación y 1 generación REALES contra la API de Claude.

Autoskip si no hay una ANTHROPIC_API_KEY real en el entorno (el placeholder
"cambiar" del .env de desarrollo NO cuenta). La key se captura al importar,
antes de que el conftest la vacíe para el resto de la suite.

Ejecutar con: pytest -m llm
"""

import os

import pytest

from app.core.config import get_settings
from app.ia import llm

# capturada en el import (el fixture de conftest vacía ANTHROPIC_API_KEY después)
_KEY_REAL = os.environ.get("ANTHROPIC_API_KEY", "")

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not _KEY_REAL.startswith("sk-ant-"),
        reason="ANTHROPIC_API_KEY real no configurada (placeholder o ausente)",
    ),
]


@pytest.fixture()
def key_real(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANTHROPIC_API_KEY", _KEY_REAL)
    get_settings.cache_clear()
    llm.reset_estado()
    yield
    llm.reset_estado()
    get_settings.cache_clear()


async def test_clasificacion_real(key_real):
    esquema = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["recuperar_correo", "consultar_estado", "no_comprendida"],
            },
            "confianza": {"type": "number"},
        },
        "required": ["intent", "confianza"],
        "additionalProperties": False,
    }
    resultado = await llm.clasificar(
        "Eres el clasificador de intenciones del Asistente Virtual del CTIC. "
        "Clasifica el mensaje del usuario en UNA de las intenciones del esquema.",
        "olvidé la contraseña de mi correo institucional",
        esquema,
    )
    assert resultado["intent"] == "recuperar_correo"
    assert 0.0 <= float(resultado["confianza"]) <= 1.0


async def test_generacion_real(key_real):
    from app.ia.rag import PROMPT_SISTEMA_RAG

    user = (
        "ARTÍCULOS:\n### Conexión WiFi\nSeleccione la red UNAC-CAMPUS e ingrese su "
        "correo institucional y contraseña.\n\n"
        "Historial breve:\n(sin historial)\n\n"
        "Consulta del usuario: ¿cómo me conecto al wifi?"
    )
    partes = [f async for f in llm.generar_stream(PROMPT_SISTEMA_RAG, user, max_tokens=300)]
    texto = "".join(partes)
    assert "UNAC-CAMPUS" in texto
