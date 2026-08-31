"""Clasificador LLM (capa 2, prd/06 §2): esquema, umbral, degradación y ruteo.

Todos los tests usan el doble `tests.llm_falso` (la API key real es un
placeholder); el camino sin LLM debe comportarse exactamente como la capa 1.
"""

from typing import Any

import pytest

from app.core.config import get_settings
from app.dialogo import clasificador, textos
from app.dialogo.clasificador import (
    ESQUEMA,
    INTENTS,
    PROMPT_SISTEMA,
    clasificar_intencion,
)
from app.dialogo.engine import Deps
from app.dialogo.manager import Orquestador
from app.dialogo.tipos import Entrada, texto_plano
from app.models import Conversacion
from tests.llm_falso import llm_falso, sin_modulo_llm  # noqa: F401 (fixtures)

# Frase que la capa 1 NO reconoce (sin keywords ni patrones)
FRASE_AMBIGUA = "me aparece un aviso raro al ingresar desde el pabellon B"


# ------------------------------------------------------------------ esquema


def test_esquema_tiene_los_16_intents_de_prd01() -> None:
    esperados = {
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
    }
    assert set(INTENTS) == esperados
    assert len(INTENTS) == 16
    assert ESQUEMA["properties"]["intent"]["enum"] == list(INTENTS)


def test_esquema_es_estricto() -> None:
    assert ESQUEMA["additionalProperties"] is False
    assert set(ESQUEMA["required"]) == {"intent", "confianza"}
    confianza = ESQUEMA["properties"]["confianza"]
    assert confianza["type"] == "number"
    assert confianza["minimum"] == 0
    assert confianza["maximum"] == 1


async def test_llamada_usa_prompt_esquema_y_modelo_router(llm_falso) -> None:  # noqa: F811
    resultado = await clasificar_intencion("¿me ayudas?", [])
    assert resultado is not None
    llamada = llm_falso.llamadas[0]
    assert llamada["system"] == PROMPT_SISTEMA
    assert "Eres el clasificador de intenciones" in llamada["system"]
    assert '→ "fuera_de_alcance"' in llamada["system"]
    assert llamada["schema"] is ESQUEMA
    assert llamada["model"] == get_settings().LLM_MODEL_ROUTER
    assert llamada["max_tokens"] == clasificador.MAX_TOKENS_ROUTER


# ---------------------------------------------------------------- historial


async def test_historial_ultimos_3_turnos_en_el_prompt(llm_falso) -> None:  # noqa: F811
    historial = [
        "Usuario: turno viejo 1",
        "Bot: turno viejo 2",
        "Usuario: hola",
        "Bot: bienvenida al CTIC",
        "Usuario: gracias",
    ]
    await clasificar_intencion("mensaje actual", historial)
    user = llm_falso.llamadas[0]["user"]
    assert user.startswith("Historial breve: ")
    assert user.endswith("\nMensaje: mensaje actual")
    assert "Usuario: hola" in user
    assert "Bot: bienvenida al CTIC" in user
    assert "Usuario: gracias" in user
    assert "turno viejo 1" not in user  # solo los últimos 3
    assert "turno viejo 2" not in user


async def test_sin_historial_lo_indica(llm_falso) -> None:  # noqa: F811
    await clasificar_intencion("mensaje", [])
    assert "(sin historial)" in llm_falso.llamadas[0]["user"]


# ------------------------------------------------------------------- umbral


async def test_umbral_055_bajo_se_trata_como_no_comprendida(llm_falso) -> None:  # noqa: F811
    llm_falso.respuesta = {"intent": "faq_general", "confianza": 0.54}
    resultado = await clasificar_intencion("algo", [])
    assert resultado is not None
    assert resultado.intent == "no_comprendida"
    assert resultado.confianza == 0.54


async def test_umbral_055_exacto_pasa(llm_falso) -> None:  # noqa: F811
    llm_falso.respuesta = {"intent": "recuperar_correo", "confianza": 0.55}
    resultado = await clasificar_intencion("algo", [])
    assert resultado is not None
    assert resultado.intent == "recuperar_correo"


# -------------------------------------------------------------- degradación


async def test_llm_no_disponible_devuelve_none(llm_falso) -> None:  # noqa: F811
    llm_falso.excepcion = llm_falso.LlmNoDisponible("sin crédito")
    assert await clasificar_intencion("algo", []) is None


async def test_llm_reporta_no_disponible_no_llama(llm_falso) -> None:  # noqa: F811
    llm_falso.disponible = False
    assert await clasificar_intencion("algo", []) is None
    assert llm_falso.llamadas == []


async def test_sin_modulo_llm_devuelve_none(sin_modulo_llm) -> None:  # noqa: F811
    assert await clasificar_intencion("algo", []) is None
    assert clasificador.llm_activo() is False


@pytest.mark.parametrize(
    "respuesta",
    [
        {"intent": "intent_inexistente", "confianza": 0.9},
        {"intent": "faq_general", "confianza": "alta"},
        {"intent": "faq_general", "confianza": 1.5},
        {"intent": "faq_general", "confianza": -0.1},
        {"intent": "faq_general"},
        {"confianza": 0.9},
        ["faq_general", 0.9],
        None,
    ],
)
async def test_respuesta_invalida_devuelve_none(llm_falso, respuesta) -> None:  # noqa: F811
    llm_falso.respuesta = respuesta
    assert await clasificar_intencion("algo", []) is None


async def test_error_inesperado_devuelve_none(llm_falso) -> None:  # noqa: F811
    llm_falso.excepcion = RuntimeError("boom interno del SDK")
    assert await clasificar_intencion("algo", []) is None


# --------------------------------------------- integración con el orquestador


class _SesionStub:
    """Reemplaza AsyncSession donde solo se necesita .add() (handoffs)."""

    def __init__(self) -> None:
        self.agregados: list[Any] = []

    def add(self, obj: Any) -> None:
        self.agregados.append(obj)


@pytest.fixture()
def conv() -> Conversacion:
    return Conversacion(id=1, codigo="22222222-2222-4222-8222-222222222222")


@pytest.fixture()
def deps() -> Deps:
    from tests.fakes import FakeTicketsClient

    return Deps(session=_SesionStub(), tickets=FakeTicketsClient())  # type: ignore[arg-type]


@pytest.fixture()
def bot() -> Orquestador:
    return Orquestador()


async def test_capa1_decide_sin_llamar_al_llm(bot, conv, deps, llm_falso) -> None:  # noqa: F811
    turno = await bot.procesar(conv, Entrada(texto="hola"), deps)
    assert turno.intent == "saludo"
    assert turno.via == "regla"
    assert llm_falso.llamadas == []  # capa 1 primero: el LLM no se consulta
    assert turno.mensajes[0].meta["via"] == "regla"


async def test_capa2_rutea_problema_internet_a_diagnostico(
    bot, conv, deps, llm_falso  # noqa: F811
) -> None:
    llm_falso.respuesta = {"intent": "problema_internet", "confianza": 0.91}
    turno = await bot.procesar(conv, Entrada(texto=FRASE_AMBIGUA), deps)
    assert llm_falso.llamadas, "la capa 2 debió consultarse"
    assert turno.intent == "problema_internet"
    assert turno.via == "llm"
    assert conv.flujo_activo == "diagnostico"
    assert "WiFi o cable" in turno.mensajes[0].texto
    assert turno.mensajes[0].meta == {
        "via": "llm",
        "intent": "problema_internet",
        "confianza": 0.91,
    }
    # el síntoma original queda en el contexto para la descripción compuesta
    assert conv.flujo_contexto["datos"]["sintoma"] == FRASE_AMBIGUA


async def test_capa2_rutea_recuperar_correo_a_faq(
    bot, conv, deps, llm_falso, monkeypatch  # noqa: F811
) -> None:
    consultas: list[tuple[str, str]] = []

    async def fake_faq(session, consulta, intent, confianza):
        consultas.append((consulta, intent))
        return [texto_plano("Procedimiento de recuperación de contraseña.")]

    monkeypatch.setattr("app.dialogo.manager.responder_faq", fake_faq)
    llm_falso.respuesta = {"intent": "recuperar_correo", "confianza": 0.94}
    texto = "ya no logro ingresar al buzon desde ayer"
    turno = await bot.procesar(conv, Entrada(texto=texto), deps)
    assert turno.intent == "recuperar_correo"
    assert consultas == [(texto, "recuperar_correo")]
    assert turno.mensajes[0].meta["via"] == "llm"


async def test_capa2_fuera_de_alcance_responde_lf01(bot, conv, deps, llm_falso) -> None:  # noqa: F811
    llm_falso.respuesta = {"intent": "fuera_de_alcance", "confianza": 0.97}
    turno = await bot.procesar(conv, Entrada(texto="cuando son las matriculas de verano"), deps)
    assert turno.intent == "fuera_de_alcance"
    assert turno.mensajes[0].texto == textos.FUERA_DE_ALCANCE  # texto oficial LF-01
    assert conv.fallback_consecutivos == 0


async def test_capa2_confianza_baja_alimenta_fallback(bot, conv, deps, llm_falso) -> None:  # noqa: F811
    llm_falso.respuesta = {"intent": "faq_general", "confianza": 0.30}
    turno = await bot.procesar(conv, Entrada(texto=FRASE_AMBIGUA), deps)
    assert turno.intent == "no_comprendida"
    assert turno.mensajes[0].texto == textos.FALLO_1
    assert conv.fallback_consecutivos == 1


async def test_llm_caido_la_conversacion_sigue_con_capa1(
    bot, conv, deps, llm_falso  # noqa: F811
) -> None:
    llm_falso.excepcion = llm_falso.LlmNoDisponible("API caída")
    turno = await bot.procesar(conv, Entrada(texto=FRASE_AMBIGUA), deps)
    assert turno.mensajes[0].texto == textos.FALLO_1  # F-09, como sin LLM
    # y el siguiente mensaje comprendido por reglas funciona con normalidad
    turno = await bot.procesar(conv, Entrada(texto="hola"), deps)
    assert turno.mensajes[0].texto == textos.BIENVENIDA
    assert conv.fallback_consecutivos == 0


async def test_sin_modulo_llm_la_conversacion_sigue(bot, conv, deps, sin_modulo_llm) -> None:  # noqa: F811
    turno = await bot.procesar(conv, Entrada(texto=FRASE_AMBIGUA), deps)
    assert turno.mensajes[0].texto == textos.FALLO_1
