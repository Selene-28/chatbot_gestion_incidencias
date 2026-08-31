"""Router de intenciones CAPA 1 (reglas): ≥25 frases con tildes y mayúsculas."""

import pytest

from app.dialogo.router import UMBRAL_CONFIANZA, IntentDetectado, detectar

CASOS: list[tuple[str, str]] = [
    # saludo (anclado)
    ("Hola", "saludo"),
    ("BUENOS DÍAS", "saludo"),
    ("buenas tardes!!", "saludo"),
    ("  ¡Hola!  ", "saludo"),
    # agradecimiento
    ("Gracias", "agradecimiento"),
    ("Muchas GRACIAS por todo", "agradecimiento"),
    # despedida
    ("Adiós", "despedida"),
    ("hasta luego", "despedida"),
    ("chau!", "despedida"),
    # finalizar
    ("quiero finalizar", "finalizar"),
    ("eso es todo", "finalizar"),
    # registrar incidencia
    ("Quiero registrar una incidencia", "registrar_incidencia"),
    ("necesito REPORTAR un problema", "registrar_incidencia"),
    ("quiero crear un ticket", "registrar_incidencia"),
    ("deseo reportar que no funciona la impresora", "registrar_incidencia"),
    # consultar estado (regex INC-AAAA-NNNN y keywords)
    ("INC-2026-0001", "consultar_estado"),
    ("¿cómo va mi incidencia inc-2026-0031?", "consultar_estado"),
    ("quiero saber el estado de mi ticket", "consultar_estado"),
    ("Estado de mi incidencia por favor", "consultar_estado"),
    # escalar
    ("quiero escalar mi incidencia", "escalar_incidencia"),
    ("por favor ESCALAR el caso", "escalar_incidencia"),
    # contactar soporte
    ("necesito hablar con una persona", "contactar_soporte"),
    ("quiero contactar con soporte", "contactar_soporte"),
    ("puedo hablar con un agente?", "contactar_soporte"),
    # info CTIC
    ("¿Cuál es el horario de atención?", "info_ctic"),
    ("¿dónde queda el CTIC?", "info_ctic"),
    ("teléfono del CTIC", "info_ctic"),
    # diagnóstico F-05 (problemas obvios, Semana 4)
    ("No puedo entrar al aula virtual", "problema_aula_virtual"),
    ("el WIFI no funciona en mi pabellón", "problema_internet"),
    ("tengo un problema con el internet", "problema_internet"),
    ("no tengo internet en el laboratorio", "problema_internet"),
    ("no funciona el wifi", "problema_internet"),
    ("el aula virtual no carga desde ayer", "problema_aula_virtual"),
    ("me sale un error en el SGA", "problema_software"),
    ("el Turnitin falla al subir mi archivo", "problema_software"),
    # recuperar_correo (prd/06 §2: "contraseña" + "correo")
    ("olvidé mi contraseña del correo institucional", "recuperar_correo"),
    ("quiero restablecer la clave de mi correo", "recuperar_correo"),
    # FAQ (keywords normalizadas)
    ("¿Cómo me conecto a la red del campus?", "faq_general"),
    # no comprendida
    ("asdfgh qwerty", "no_comprendida"),
    ("zzz", "no_comprendida"),
    ("", "no_comprendida"),
]


@pytest.mark.parametrize(("frase", "esperado"), CASOS)
def test_router_capa1(frase: str, esperado: str) -> None:
    resultado = detectar(frase)
    assert resultado.intent == esperado, f"{frase!r} → {resultado.intent} (≠ {esperado})"


def test_confianza_sobre_umbral_para_comprendidas() -> None:
    for frase, esperado in CASOS:
        resultado = detectar(frase)
        if esperado != "no_comprendida":
            assert resultado.confianza >= UMBRAL_CONFIANZA


def test_no_comprendida_confianza_cero() -> None:
    assert detectar("xyzzy plugh").confianza == 0.0


def test_saludo_no_roba_mensajes_con_contenido() -> None:
    """'hola' + problema debe enrutar al problema, no al saludo."""
    assert detectar("hola, no puedo entrar a mi correo").intent == "faq_general"


def test_punto_de_extension_llm() -> None:
    """Capa 2 (Semana 4): si las reglas no deciden, se consulta el clasificador."""
    llamado = {}

    def clasificador(texto: str) -> IntentDetectado:
        llamado["texto"] = texto
        return IntentDetectado("faq_general", 0.8)

    resultado = detectar("frase totalmente ambigua xyz", clasificador_llm=clasificador)
    assert llamado["texto"] == "frase totalmente ambigua xyz"
    assert resultado.intent == "faq_general"


def test_punto_de_extension_llm_bajo_umbral() -> None:
    resultado = detectar(
        "frase ambigua xyz",
        clasificador_llm=lambda _t: IntentDetectado("faq_general", 0.3),
    )
    assert resultado.intent == "no_comprendida"
