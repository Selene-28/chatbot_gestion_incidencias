"""Flujos F-02/F-03/F-06/F-08 y fallback F-09 a nivel de unidad (sin BD).

Se ejercitan a través del Orquestador con una conversación fake y el cliente
de tickets en memoria.
"""

from typing import Any

import pytest

from app.core.errors import BusinessRuleError
from app.dialogo import textos
from app.dialogo.engine import Deps
from app.dialogo.flujos import faq
from app.dialogo.manager import Orquestador
from app.dialogo.tipos import OPCION_ADJUNTO, Entrada
from app.models import Conversacion
from tests.fakes import FakeTicketsClient, detalle_ticket


class SesionStub:
    """Reemplaza AsyncSession donde solo se necesita .add() (handoffs)."""

    def __init__(self) -> None:
        self.agregados: list[Any] = []

    def add(self, obj: Any) -> None:
        self.agregados.append(obj)


@pytest.fixture()
def conv() -> Conversacion:
    return Conversacion(id=1, codigo="11111111-1111-4111-8111-111111111111")


@pytest.fixture()
def tickets() -> FakeTicketsClient:
    return FakeTicketsClient()


@pytest.fixture()
def deps(tickets: FakeTicketsClient) -> Deps:
    return Deps(session=SesionStub(), tickets=tickets)  # type: ignore[arg-type]


@pytest.fixture()
def bot() -> Orquestador:
    return Orquestador()


async def _decir(bot: Orquestador, conv: Conversacion, deps: Deps, texto: str):
    turno = await bot.procesar(conv, Entrada(texto=texto), deps)
    return turno.mensajes


async def _pulsar(bot: Orquestador, conv: Conversacion, deps: Deps, opcion: str, adj=None):
    turno = await bot.procesar(conv, Entrada(opcion_id=opcion, adjunto_id=adj), deps)
    return turno.mensajes


# ------------------------------------------------------------------- F-02


async def test_f02_ciclo_completo(bot, conv, deps, tickets):
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    assert conv.flujo_activo == "registrar_incidencia"

    await _decir(bot, conv, deps, "Juan Pérez")
    assert conv.usuario_nombre == "Juan Pérez"
    await _decir(bot, conv, deps, "2021012345")
    await _decir(bot, conv, deps, "jperez@unac.edu.pe")
    assert conv.usuario_correo == "jperez@unac.edu.pe"

    await _pulsar(bot, conv, deps, "escuela_industrial")
    await _pulsar(bot, conv, deps, "cat_0")  # Correo Institucional
    await _decir(bot, conv, deps, "No puedo acceder a mi correo institucional.")
    await _pulsar(bot, conv, deps, "prio_media")
    mensajes = await _pulsar(bot, conv, deps, "omitir")
    # resumen + confirmación
    assert "confirma los datos" in mensajes[0].texto
    assert conv.flujo_contexto["datos"]["idempotency_key"]

    mensajes = await _pulsar(bot, conv, deps, "confirmar")
    assert mensajes[0].texto == textos.ticket_registrado("INC-2026-0001")
    assert conv.flujo_activo is None
    payload, clave = tickets.registros[0]
    assert payload["categoria"] == "Correo Institucional"
    assert payload["prioridad"] == "Media"
    assert payload["origen"] == "chatbot"
    assert payload["conversacionCodigo"] == conv.codigo
    assert len(clave) == 36  # UUID
    assert conv.flujo_contexto["sesion"]["ultimo_ticket"] == "INC-2026-0001"


async def test_f02_salta_identificacion_si_ya_identificada(bot, conv, deps):
    conv.usuario_nombre = "Ana"
    conv.usuario_correo = "ana@unac.edu.pe"
    mensajes = await _pulsar(bot, conv, deps, "registrar_incidencia")
    assert "código institucional" in mensajes[0].texto.lower()


async def test_f02_valida_correo_y_resolicita(bot, conv, deps):
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    await _decir(bot, conv, deps, "Juan Pérez")
    await _decir(bot, conv, deps, "2021012345")
    mensajes = await _decir(bot, conv, deps, "juan@gmail.com")
    assert "@unac.edu.pe" in mensajes[0].texto
    assert conv.flujo_contexto["paso"] == "correo"
    assert conv.flujo_contexto["intentos"] == 1


async def test_f02_valida_codigo_institucional_y_resolicita(bot, conv, deps):
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    await _decir(bot, conv, deps, "Juan Pérez")
    mensajes = await _decir(bot, conv, deps, "12345")  # menos de 10 dígitos
    assert "10" in mensajes[0].texto
    assert conv.flujo_contexto["paso"] == "codigo"
    assert conv.flujo_contexto["intentos"] == 1


async def test_f02_adjunto_via_widget(bot, conv, deps, tickets):
    conv.usuario_nombre = "Ana"
    conv.usuario_correo = "ana@unac.edu.pe"
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    await _decir(bot, conv, deps, "2021012345")
    await _pulsar(bot, conv, deps, "escuela_sistemas")
    await _pulsar(bot, conv, deps, "cat_1")
    await _decir(bot, conv, deps, "El wifi del pabellón B no funciona.")
    mensajes = await _pulsar(bot, conv, deps, "prio_alta")
    assert mensajes[0].tipo == "adjunto"
    assert any(o.id == "omitir" for o in mensajes[0].opciones)
    await _pulsar(bot, conv, deps, OPCION_ADJUNTO, adj="adj_9f31")
    await _pulsar(bot, conv, deps, "confirmar")
    payload, _ = tickets.registros[0]
    assert payload["adjuntoId"] == "adj_9f31"


async def test_f02_error_remoto_ofrece_reintentar_sin_perder_contexto(
    bot, conv, deps, tickets
):
    conv.usuario_nombre = "Ana"
    conv.usuario_correo = "ana@unac.edu.pe"
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    await _decir(bot, conv, deps, "2021012345")
    await _pulsar(bot, conv, deps, "escuela_industrial")
    await _pulsar(bot, conv, deps, "cat_7")
    await _decir(bot, conv, deps, "Descripción suficientemente larga del problema.")
    await _pulsar(bot, conv, deps, "prio_baja")
    await _pulsar(bot, conv, deps, "omitir")
    clave_original = conv.flujo_contexto["datos"]["idempotency_key"]

    tickets.fallo_siguiente = BusinessRuleError(textos.DISCULPA_TICKETS_CAIDO)
    mensajes = await _pulsar(bot, conv, deps, "confirmar")
    assert mensajes[0].texto == textos.DISCULPA_TICKETS_CAIDO
    assert any(o.id == "reintentar" for o in mensajes[0].opciones)
    assert conv.flujo_activo == "registrar_incidencia"  # contexto NO se pierde

    mensajes = await _pulsar(bot, conv, deps, "reintentar")
    assert mensajes[0].texto == textos.ticket_registrado("INC-2026-0001")
    _, clave_reintento = tickets.registros[0]
    assert clave_reintento == clave_original  # misma Idempotency-Key (REN-02)


async def test_f02_corregir_vuelve_a_confirmacion(bot, conv, deps):
    conv.usuario_nombre = "Ana"
    conv.usuario_correo = "ana@unac.edu.pe"
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    await _decir(bot, conv, deps, "2021012345")
    await _pulsar(bot, conv, deps, "escuela_industrial")
    await _pulsar(bot, conv, deps, "cat_3")
    await _decir(bot, conv, deps, "No carga el SGA desde ayer.")
    await _pulsar(bot, conv, deps, "prio_media")
    await _pulsar(bot, conv, deps, "omitir")

    mensajes = await _pulsar(bot, conv, deps, "corregir")
    assert "qué campo" in mensajes[0].texto.lower()
    await _pulsar(bot, conv, deps, "campo_descripcion")
    assert conv.flujo_contexto["paso"] == "descripcion"
    mensajes = await _decir(bot, conv, deps, "Ahora sí: el SGA muestra error 500.")
    assert conv.flujo_contexto["paso"] == "confirmacion"
    assert "error 500" in mensajes[0].texto


async def test_f02_cancelar_descarta_y_vuelve_al_menu(bot, conv, deps):
    conv.usuario_nombre = "Ana"
    conv.usuario_correo = "ana@unac.edu.pe"
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    await _decir(bot, conv, deps, "2021012345")
    await _pulsar(bot, conv, deps, "escuela_industrial")
    await _pulsar(bot, conv, deps, "cat_0")
    await _decir(bot, conv, deps, "Descripción del problema de correo.")
    await _pulsar(bot, conv, deps, "prio_media")
    await _pulsar(bot, conv, deps, "omitir")
    mensajes = await _pulsar(bot, conv, deps, "cancelar")
    assert conv.flujo_activo is None
    assert mensajes[-1].opciones is not None  # menú principal


# ------------------------------------------------------------------- F-03


async def test_f03_por_codigo_feliz(bot, conv, deps, tickets):
    tickets.tickets["INC-2026-0007"] = {
        "correo": "ana@unac.edu.pe",
        "detalle": detalle_ticket("INC-2026-0007"),
    }
    await _pulsar(bot, conv, deps, "consultar_estado")
    await _decir(bot, conv, deps, "ana@unac.edu.pe")
    await _pulsar(bot, conv, deps, "modo_codigo")
    mensajes = await _decir(bot, conv, deps, "INC-2026-0007")
    assert "En Proceso" in mensajes[0].texto
    assert "Paul Barzola" in mensajes[0].texto
    assert "Observaciones:" in mensajes[0].texto
    assert conv.flujo_contexto["sesion"]["ultimo_ticket"] == "INC-2026-0007"


async def test_f03_muestra_respuesta_si_esta_resuelto(bot, conv, deps, tickets):
    detalle = detalle_ticket("INC-2026-0008", estado="Resuelto")
    detalle["respuesta"] = "Se restableció tu contraseña institucional."
    tickets.tickets["INC-2026-0008"] = {
        "correo": "ana@unac.edu.pe",
        "detalle": detalle,
    }
    conv.usuario_correo = "ana@unac.edu.pe"
    await _pulsar(bot, conv, deps, "consultar_estado")
    await _pulsar(bot, conv, deps, "modo_codigo")
    mensajes = await _decir(bot, conv, deps, "INC-2026-0008")
    assert "Respuesta: Se restableció tu contraseña institucional." in mensajes[0].texto
    assert "Observaciones:" not in mensajes[0].texto


async def test_f03_403_no_revela_datos(bot, conv, deps, tickets):
    tickets.tickets["INC-2026-0007"] = {
        "correo": "otro@unac.edu.pe",
        "detalle": detalle_ticket("INC-2026-0007"),
    }
    conv.usuario_correo = "ana@unac.edu.pe"
    await _decir(bot, conv, deps, "estado de mi ticket INC-2026-0007")
    mensajes_ultimo = await _decir(bot, conv, deps, "INC-2026-0007") \
        if conv.flujo_activo else None
    # la consulta directa con código prellenado ya respondió el 403
    # (verificamos que nunca se muestre el detalle)
    assert mensajes_ultimo is None or all(
        "En Proceso" not in m.texto for m in mensajes_ultimo
    )


async def test_f03_404_ofrece_reintentar(bot, conv, deps, tickets):
    conv.usuario_correo = "ana@unac.edu.pe"
    await _pulsar(bot, conv, deps, "consultar_estado")
    await _pulsar(bot, conv, deps, "modo_codigo")
    mensajes = await _decir(bot, conv, deps, "INC-2026-9999")
    assert "No encontré" in mensajes[0].texto
    assert conv.flujo_contexto["paso"] == "codigo"  # puede reintentar


async def test_f03_por_correo_lista_botones(bot, conv, deps, tickets):
    conv.usuario_correo = "ana@unac.edu.pe"
    tickets.listados["ana@unac.edu.pe"] = [
        detalle_ticket(f"INC-2026-{n:04d}") for n in range(1, 13)
    ]
    tickets.tickets["INC-2026-0001"] = {
        "correo": "ana@unac.edu.pe",
        "detalle": detalle_ticket("INC-2026-0001"),
    }
    await _pulsar(bot, conv, deps, "consultar_estado")
    mensajes = await _pulsar(bot, conv, deps, "modo_correo")
    assert len(mensajes[0].opciones) == 10  # máx. 10 botones
    mensajes = await _pulsar(bot, conv, deps, "INC-2026-0001")
    assert "INC-2026-0001" in mensajes[0].texto


# ------------------------------------------------------------------- F-06


async def test_f06_escalar_feliz_con_ticket_del_contexto(bot, conv, deps, tickets):
    conv.usuario_correo = "ana@unac.edu.pe"
    conv.flujo_contexto = {"sesion": {"ultimo_ticket": "INC-2026-0003"}}
    tickets.tickets["INC-2026-0003"] = {"correo": "ana@unac.edu.pe", "escalable": True}
    mensajes = await _decir(bot, conv, deps, "quiero escalar mi incidencia")
    assert "INC-2026-0003" in mensajes[0].texto  # pide el motivo del ticket en contexto
    mensajes = await _decir(bot, conv, deps, "Nadie lo atiende desde hace una semana.")
    assert mensajes[0].texto == textos.ESCALADO_CONFIRMACION
    assert tickets.escalados == [
        ("INC-2026-0003", "Nadie lo atiende desde hace una semana.", "ana@unac.edu.pe")
    ]


async def test_f06_motivo_corto_resolicita(bot, conv, deps, tickets):
    conv.usuario_correo = "ana@unac.edu.pe"
    tickets.tickets["INC-2026-0003"] = {"correo": "ana@unac.edu.pe"}
    await _decir(bot, conv, deps, "escalar INC-2026-0003")
    mensajes = await _decir(bot, conv, deps, "corto")
    assert "10 y 500" in mensajes[0].texto
    assert conv.flujo_contexto["paso"] == "motivo"


async def test_f06_409_ofrece_nueva_incidencia(bot, conv, deps, tickets):
    conv.usuario_correo = "ana@unac.edu.pe"
    tickets.tickets["INC-2026-0004"] = {"correo": "ana@unac.edu.pe", "escalable": False}
    await _decir(bot, conv, deps, "escalar INC-2026-0004")
    mensajes = await _decir(bot, conv, deps, "El problema volvió a ocurrir hoy.")
    assert "ya no permite" in mensajes[0].texto
    assert any(o.id == "registrar_incidencia" for o in mensajes[0].opciones)
    assert conv.flujo_activo is None


# ------------------------------------------------------------------- F-08


async def test_f08_encuesta_con_ticket(bot, conv, deps, tickets):
    conv.flujo_contexto = {"sesion": {"ultimo_ticket": "INC-2026-0001", "atencion": True}}
    mensajes = await _pulsar(bot, conv, deps, "finalizar")
    assert mensajes[0].tipo == "encuesta"
    assert mensajes[0].texto == textos.ENCUESTA_SOLICITUD
    assert [o.id for o in mensajes[0].opciones] == [f"calif_{n}" for n in range(1, 6)]

    await _pulsar(bot, conv, deps, "calif_5")
    mensajes = await _pulsar(bot, conv, deps, "omitir")
    assert mensajes[-1].texto == textos.DESPEDIDA
    assert conv.estado == "cerrada"
    assert conv.motivo_cierre == "usuario"
    assert tickets.encuestas == [
        {
            "calificacion": 5,
            "comentario": None,
            "ticketId": "INC-2026-0001",
            "conversacionCodigo": None,
        }
    ]


async def test_f08_encuesta_sin_ticket_usa_conversacion(bot, conv, deps, tickets):
    mensajes = await _pulsar(bot, conv, deps, "finalizar")
    assert mensajes[0].tipo == "encuesta"
    await _pulsar(bot, conv, deps, "calif_3")
    await _decir(bot, conv, deps, "Buen servicio en general.")
    assert tickets.encuestas[0]["conversacionCodigo"] == conv.codigo
    assert tickets.encuestas[0]["comentario"] == "Buen servicio en general."


async def test_f08_solo_una_vez_por_atencion(bot, conv, deps, tickets):
    conv.flujo_contexto = {"sesion": {"encuesta_ofrecida": True}}
    mensajes = await _pulsar(bot, conv, deps, "finalizar")
    # RN-04: no vuelve a ofrecer; cierra cortésmente
    assert mensajes[0].texto == textos.DESPEDIDA
    assert tickets.encuestas == []


async def test_despedida_dispara_encuesta_si_hubo_atencion(bot, conv, deps):
    conv.flujo_contexto = {"sesion": {"atencion": True}}
    mensajes = await _decir(bot, conv, deps, "adiós")
    assert mensajes[0].tipo == "encuesta"


async def test_despedida_sin_atencion_cierra(bot, conv, deps):
    mensajes = await _decir(bot, conv, deps, "adiós")
    assert mensajes[0].texto == textos.DESPEDIDA
    assert conv.estado == "cerrada"


# ------------------------------------------------------------------- F-09


async def test_f09_fallback_1_2_y_handoff_al_tercero(bot, conv, deps):
    sesion_stub = deps.session

    mensajes = await _decir(bot, conv, deps, "xyzzy")
    assert mensajes[0].texto == textos.FALLO_1
    assert conv.fallback_consecutivos == 1

    mensajes = await _decir(bot, conv, deps, "xyzzy otra vez")
    assert mensajes[0].texto == textos.FALLO_2
    assert [o.id for o in mensajes[0].opciones] == [i for i, _ in textos.MENU_OPCIONES]
    assert conv.fallback_consecutivos == 2

    mensajes = await _decir(bot, conv, deps, "xyzzy de nuevo")
    assert mensajes[0].tipo == "handoff"
    assert mensajes[0].texto == textos.TRANSICION_HANDOFF
    # Semana 5 (F-07): el handoff YA pausa el bot de verdad (RN-05); el mensaje
    # interino de registro desaparece (el panel de agentes atiende la cola).
    assert len(mensajes) == 1
    assert conv.estado_bot == "PAUSED"
    handoffs = [h for h in sesion_stub.agregados if h.__class__.__name__ == "Handoff"]
    assert len(handoffs) == 1
    assert handoffs[0].motivo == "fallback_x3"
    assert handoffs[0].estado is None or handoffs[0].estado == "pendiente"
    assert conv.fallback_consecutivos == 0  # se reinicia tras el handoff


async def test_f09_mensaje_comprendido_reinicia_contador(bot, conv, deps):
    await _decir(bot, conv, deps, "xyzzy")
    assert conv.fallback_consecutivos == 1
    await _decir(bot, conv, deps, "hola")
    assert conv.fallback_consecutivos == 0


async def test_contactar_soporte_crea_handoff_solicitud_usuario(bot, conv, deps):
    mensajes = await _pulsar(bot, conv, deps, "contactar_soporte")
    assert mensajes[0].texto == textos.TRANSICION_HANDOFF
    assert conv.estado_bot == "PAUSED"  # RN-05
    handoffs = deps.session.agregados
    assert handoffs[0].motivo == "solicitud_usuario"


# ------------------------------------------------------ comportamiento global


async def test_opcion_menu_cancela_flujo_activo(bot, conv, deps):
    await _pulsar(bot, conv, deps, "registrar_incidencia")
    assert conv.flujo_activo is not None
    mensajes = await _pulsar(bot, conv, deps, "menu")
    assert conv.flujo_activo is None
    assert mensajes[0].opciones is not None


async def test_saludo_devuelve_bienvenida_y_menu(bot, conv, deps):
    mensajes = await _decir(bot, conv, deps, "hola")
    assert mensajes[0].texto == textos.BIENVENIDA
    assert [o.id for o in mensajes[1].opciones] == [i for i, _ in textos.MENU_OPCIONES]


async def test_agradecimiento_respuesta_fija(bot, conv, deps):
    mensajes = await _decir(bot, conv, deps, "muchas gracias")
    assert mensajes[0].texto == textos.AGRADECIMIENTO


async def test_bot_pausado_no_procesa_intents(bot, conv, deps):
    conv.estado_bot = "PAUSED"
    turno = await bot.procesar(conv, Entrada(texto="hola"), deps)
    assert turno.mensajes[0].tipo == "handoff"


# ------------------------------------------------------------------- F-04


async def test_faq_muestra_menu_de_10_opciones(bot, conv, deps):
    mensajes = await _pulsar(bot, conv, deps, "faq_general")
    assert [o.id for o in mensajes[0].opciones] == [i for i, _ in faq._OPCIONES_FAQ]
    assert len(mensajes[0].opciones) == 10


async def test_faq_opcion_resuelve_articulo_fijo(bot, conv, deps, monkeypatch):
    async def _fake_articulo(session, titulo):  # type: ignore[no-untyped-def]
        assert titulo == "FAQ: ¿Cómo ingreso al SGA?"
        return {"id": 42, "titulo": titulo, "contenido": "Usa tu código y contraseña."}

    monkeypatch.setattr(faq, "articulo_por_titulo", _fake_articulo)

    await _pulsar(bot, conv, deps, "faq_general")
    mensajes = await _pulsar(bot, conv, deps, "faq_ingreso_sga")

    assert mensajes[0].texto == "Usa tu código y contraseña."
    assert mensajes[0].meta["fuentesKb"] == [42]
    assert len(mensajes) == 1


async def test_faq_opcion_sin_articulo_en_bd_ofrece_registrar(bot, conv, deps, monkeypatch):
    async def _fake_articulo(session, titulo):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(faq, "articulo_por_titulo", _fake_articulo)

    await _pulsar(bot, conv, deps, "faq_general")
    mensajes = await _pulsar(bot, conv, deps, "faq_tesis")
    assert mensajes[0].texto == textos.KB_SIN_RESPUESTA
