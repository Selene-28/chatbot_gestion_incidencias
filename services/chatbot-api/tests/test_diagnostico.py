"""F-05 · Diagnóstico guiado: recorrido de los 4 árboles, QA-04 y pre-llenado
de F-02 (sin BD, a través del Orquestador con el cliente de tickets en memoria).
"""

from typing import Any

import pytest

from app.dialogo import textos
from app.dialogo.engine import Deps
from app.dialogo.flujos.diagnostico import ARBOL_POR_INTENT, ARBOLES
from app.dialogo.manager import Orquestador
from app.dialogo.tipos import Entrada
from app.models import Conversacion
from tests.fakes import FakeTicketsClient


class SesionStub:
    """Reemplaza AsyncSession donde solo se necesita .add()."""

    def __init__(self) -> None:
        self.agregados: list[Any] = []

    def add(self, obj: Any) -> None:
        self.agregados.append(obj)


@pytest.fixture()
def conv() -> Conversacion:
    return Conversacion(id=1, codigo="33333333-3333-4333-8333-333333333333")


@pytest.fixture()
def tickets() -> FakeTicketsClient:
    return FakeTicketsClient()


@pytest.fixture()
def deps(tickets: FakeTicketsClient) -> Deps:
    return Deps(session=SesionStub(), tickets=tickets)  # type: ignore[arg-type]


@pytest.fixture()
def bot() -> Orquestador:
    return Orquestador()


async def _decir(bot, conv, deps, texto: str):
    return (await bot.procesar(conv, Entrada(texto=texto), deps)).mensajes


async def _pulsar(bot, conv, deps, opcion: str):
    return (await bot.procesar(conv, Entrada(opcion_id=opcion), deps)).mensajes


# ------------------------------------------------------ configuración estática


def test_arboles_definidos_para_las_4_categorias() -> None:
    assert set(ARBOLES) == {"internet", "aula_virtual", "correo", "software"}
    categorias = {a.categoria for a in ARBOLES.values()}
    assert categorias == {
        "Internet/WiFi",
        "Aula Virtual",
        "Correo Institucional",
        "Software Institucional",
    }


def test_intents_de_diagnostico_mapean_a_arboles() -> None:
    assert ARBOL_POR_INTENT == {
        "problema_internet": "internet",
        "problema_aula_virtual": "aula_virtual",
        "problema_software": "software",
    }


def test_destinos_de_los_arboles_existen() -> None:
    """Integridad: toda rama apunta a un nodo definido en su árbol."""
    from app.dialogo.flujos.diagnostico import Pregunta

    for arbol in ARBOLES.values():
        assert arbol.inicio in arbol.nodos
        for nodo in arbol.nodos.values():
            if isinstance(nodo, Pregunta):
                for rama in nodo.ramas:
                    assert rama.destino in arbol.nodos, (arbol.clave, rama.id)


# ------------------------------------------------- árbol Internet/WiFi (PRD)


async def test_internet_wifi_no_ve_red_resuelto_feliz(bot, conv, deps) -> None:
    mensajes = await _decir(bot, conv, deps, "no funciona el wifi")
    assert conv.flujo_activo == "diagnostico"
    assert "WiFi o cable" in mensajes[0].texto
    assert [o.id for o in mensajes[0].opciones] == ["wifi", "cable"]

    mensajes = await _pulsar(bot, conv, deps, "wifi")
    assert "red «UNAC»" in mensajes[0].texto

    mensajes = await _pulsar(bot, conv, deps, "red_no")
    assert "Olvida la red" in mensajes[0].texto  # pasos del PRD
    assert mensajes[1].texto == "¿Se resolvió el problema con estos pasos?"

    mensajes = await _pulsar(bot, conv, deps, "resuelto_si")
    assert "Me alegra" in mensajes[0].texto  # cierre feliz
    assert mensajes[1].opciones is not None  # menú principal
    assert conv.flujo_activo is None
    # la atención cuenta para la encuesta F-08 al despedirse
    assert conv.flujo_contexto["sesion"]["atencion"] is True
    turno = await bot.procesar(conv, Entrada(texto="adiós"), deps)
    assert turno.mensajes[0].tipo == "encuesta"


async def test_internet_portal_no_resuelto_prellena_f02(bot, conv, deps, tickets) -> None:
    sintoma = "no tengo internet en el aula 204"
    await _decir(bot, conv, deps, sintoma)
    await _pulsar(bot, conv, deps, "wifi")
    mensajes = await _pulsar(bot, conv, deps, "red_si")
    assert "no puedes navegar" in mensajes[0].texto

    mensajes = await _pulsar(bot, conv, deps, "navega_no")
    assert "portal cautivo" in mensajes[0].texto

    # No se resolvió → F-02 encadenado con datos pre-llenados
    mensajes = await _pulsar(bot, conv, deps, "resuelto_no")
    assert "Registremos una incidencia" in mensajes[0].texto
    assert conv.flujo_activo == "registrar_incidencia"
    assert "nombre completo" in mensajes[1].texto  # arranca en identificación
    datos = conv.flujo_contexto["datos"]
    assert datos["categoria"] == "Internet/WiFi"
    assert "Diagnóstico guiado" in datos["descripcion"]

    # identificación y escuela: pasos NO cubiertos por el diagnóstico
    await _decir(bot, conv, deps, "Ana Torres")
    await _decir(bot, conv, deps, "2021012345")
    mensajes = await _decir(bot, conv, deps, "atorres@unac.edu.pe")
    assert "escuela" in mensajes[0].texto.lower() or "perteneces" in mensajes[0].texto

    # tras la escuela se saltan categoría y descripción (ya cubiertas) → prioridad
    mensajes = await _pulsar(bot, conv, deps, "escuela_sistemas")
    assert "prioridad" in mensajes[0].texto.lower()
    assert all("categoría" not in m.texto.lower() for m in mensajes)

    mensajes = await _pulsar(bot, conv, deps, "prio_media")
    assert mensajes[0].tipo == "adjunto"
    mensajes = await _pulsar(bot, conv, deps, "omitir")
    resumen = mensajes[0].texto
    assert "confirma los datos" in resumen
    assert "Internet/WiFi" in resumen

    mensajes = await _pulsar(bot, conv, deps, "confirmar")
    assert mensajes[0].texto == textos.ticket_registrado("INC-2026-0001")
    payload, _clave = tickets.registros[0]
    assert payload["categoria"] == "Internet/WiFi"
    descripcion = payload["descripcion"]
    # la descripción compuesta refleja la ruta del árbol y lo ya intentado
    assert f"«{sintoma}»" in descripcion
    assert "conexión por WiFi" in descripcion
    assert "autentica pero no navega" in descripcion
    assert "portal cautivo" in descripcion


async def test_internet_rama_cable(bot, conv, deps) -> None:
    await _decir(bot, conv, deps, "no tengo internet")
    mensajes = await _pulsar(bot, conv, deps, "cable")
    assert "cable" in mensajes[0].texto
    assert "punto de red" in mensajes[0].texto
    mensajes = await _pulsar(bot, conv, deps, "resuelto_si")
    assert conv.flujo_activo is None


async def test_internet_rama_credenciales(bot, conv, deps) -> None:
    await _decir(bot, conv, deps, "el internet no funciona")
    await _pulsar(bot, conv, deps, "wifi")
    await _pulsar(bot, conv, deps, "red_si")
    mensajes = await _pulsar(bot, conv, deps, "conecta_no")
    assert "credenciales institucionales" in mensajes[0].texto


# --------------------------------------------------------- árbol Aula Virtual


async def test_aula_virtual_tres_ramas_qa04(bot, deps) -> None:
    """QA-04: la respuesta CAMBIA según lo respondido."""
    respuestas: dict[str, str] = {}
    for opcion in ("aula_credenciales", "aula_cursos", "aula_carga"):
        conv = Conversacion(id=9, codigo="44444444-4444-4444-8444-444444444444")
        mensajes = await _decir(bot, conv, deps, "no puedo entrar al aula virtual")
        assert conv.flujo_activo == "diagnostico"
        assert conv.flujo_contexto["datos"]["arbol"] == "aula_virtual"
        assert [o.id for o in mensajes[0].opciones] == [
            "aula_credenciales",
            "aula_cursos",
            "aula_carga",
        ]
        mensajes = await bot.procesar(conv, Entrada(opcion_id=opcion), deps)
        respuestas[opcion] = mensajes.mensajes[0].texto
    assert "SGA" in respuestas["aula_credenciales"]
    assert "matrícula" in respuestas["aula_cursos"]
    assert "caché" in respuestas["aula_carga"]
    assert len(set(respuestas.values())) == 3  # tres respuestas distintas


async def test_aula_virtual_no_resuelto_prellena_su_categoria(bot, conv, deps) -> None:
    await _decir(bot, conv, deps, "el aula virtual no carga")
    await _pulsar(bot, conv, deps, "aula_carga")
    await _pulsar(bot, conv, deps, "resuelto_no")
    assert conv.flujo_activo == "registrar_incidencia"
    datos = conv.flujo_contexto["datos"]
    assert datos["categoria"] == "Aula Virtual"
    assert "la plataforma no carga" in datos["descripcion"]


# ------------------------------------------------- árbol Correo institucional


async def test_correo_tres_ramas(bot, deps) -> None:
    esperado = {
        "correo_olvido": "¿Olvidaste tu contraseña?",
        "correo_bloqueo": "15 minutos",
        "correo_recepcion": "spam",
    }
    textos_vistos = set()
    for opcion, fragmento in esperado.items():
        conv = Conversacion(id=9, codigo="55555555-5555-4555-8555-555555555555")
        # el árbol de correo se inicia por engine (sin intent problema_correo)
        mensajes = await bot.engine.iniciar(
            conv, "diagnostico", deps, {"arbol": "correo"}
        )
        assert "correo institucional" in mensajes[0].texto
        mensajes = await _pulsar(bot, conv, deps, opcion)
        assert fragmento in mensajes[0].texto
        textos_vistos.add(mensajes[0].texto)
    assert len(textos_vistos) == 3  # QA-04


async def test_correo_no_resuelto_prellena_su_categoria(bot, conv, deps) -> None:
    await bot.engine.iniciar(conv, "diagnostico", deps, {"arbol": "correo"})
    await _pulsar(bot, conv, deps, "correo_bloqueo")
    await _pulsar(bot, conv, deps, "resuelto_no")
    datos = conv.flujo_contexto["datos"]
    assert datos["categoria"] == "Correo Institucional"
    assert "su cuenta está bloqueada" in datos["descripcion"]


# ---------------------------------------------- árbol Software institucional


async def test_software_cuatro_sistemas_qa04(bot, deps) -> None:
    esperado = {
        "soft_sga": "SGA",
        "soft_office": "office.com",
        "soft_turnitin": "docente",
        "soft_otro": "mensaje de error",
    }
    respuestas = {}
    for opcion, fragmento in esperado.items():
        conv = Conversacion(id=9, codigo="66666666-6666-4666-8666-666666666666")
        mensajes = await _decir(bot, conv, deps, "me sale un error en el sga")
        assert conv.flujo_contexto["datos"]["arbol"] == "software"
        assert [o.id for o in mensajes[0].opciones] == list(esperado)
        mensajes = await _pulsar(bot, conv, deps, opcion)
        assert fragmento in mensajes[0].texto
        respuestas[opcion] = mensajes[0].texto
    assert len(set(respuestas.values())) == 4  # QA-04


async def test_software_no_resuelto_prellena_sistema_elegido(bot, conv, deps) -> None:
    await _decir(bot, conv, deps, "el turnitin falla al subir mi trabajo")
    await _pulsar(bot, conv, deps, "soft_turnitin")
    await _pulsar(bot, conv, deps, "resuelto_no")
    datos = conv.flujo_contexto["datos"]
    assert datos["categoria"] == "Software Institucional"
    assert "Turnitin" in datos["descripcion"]


# ------------------------------------------------------- comportamiento común


async def test_seleccion_de_arbol_cuando_no_hay_categoria(bot, conv, deps) -> None:
    mensajes = await bot.engine.iniciar(conv, "diagnostico", deps)
    assert "¿Con qué servicio tienes problemas?" in mensajes[0].texto
    mensajes = await _pulsar(bot, conv, deps, "arbol_correo")
    assert "correo institucional" in mensajes[0].texto
    assert conv.flujo_contexto["datos"]["arbol"] == "correo"


async def test_respuesta_invalida_resolicita_la_pregunta(bot, conv, deps) -> None:
    await _decir(bot, conv, deps, "no tengo internet")
    mensajes = await _decir(bot, conv, deps, "no sé qué responder aquí")
    assert "selecciona una de las opciones" in mensajes[0].texto
    assert "WiFi o cable" in mensajes[1].texto  # re-solicita la misma pregunta
    assert conv.flujo_contexto["intentos"] == 1
    assert conv.flujo_activo == "diagnostico"


async def test_respuesta_por_texto_equivale_al_boton(bot, conv, deps) -> None:
    await _decir(bot, conv, deps, "no tengo internet")
    mensajes = await _decir(bot, conv, deps, "WiFi")
    assert "red «UNAC»" in mensajes[0].texto
    mensajes = await _pulsar(bot, conv, deps, "red_no")
    mensajes = await _decir(bot, conv, deps, "sí")
    assert conv.flujo_activo is None  # "sí" textual = resuelto


async def test_menu_cancela_el_diagnostico(bot, conv, deps) -> None:
    await _decir(bot, conv, deps, "no tengo internet")
    assert conv.flujo_activo == "diagnostico"
    await _pulsar(bot, conv, deps, "menu")
    assert conv.flujo_activo is None
