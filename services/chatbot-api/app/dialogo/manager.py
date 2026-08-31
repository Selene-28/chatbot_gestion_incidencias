"""Orquestador del diálogo — implementa F-01 (enrutamiento general) y F-09
(fallback) de prd/05.

Por cada mensaje entrante:
1. Bot PAUSED → el mensaje queda para el agente humano (RN-05; panel Semana 5).
2. Botón global "menu" → cancela el flujo activo y muestra el menú.
3. Flujo activo → Dialog Manager (engine); 3 entradas inválidas → fallback.
4. Sin flujo: opcionId de menú → inicia flujo; texto libre → router de
   intenciones (Capa 1 reglas; si no decide, Capa 2 clasificador LLM con los
   últimos 3 turnos como historial); social → respuesta fija; FAQ → base de
   conocimiento; problema_* → diagnóstico F-05; no_comprendida → fallback F-09.

La vía de clasificación (`regla` | `llm`) y la confianza quedan registradas en
el `meta` del primer mensaje del bot. Todo mensaje comprendido reinicia
`fallback_consecutivos`.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select

from app.dialogo import clasificador, router, textos
from app.dialogo.engine import Deps, Engine, FallbackDeFlujo, guardar_sesion, sesion_de
from app.dialogo.flujos import crear_engine
from app.dialogo.flujos.diagnostico import ARBOL_POR_INTENT
from app.dialogo.flujos.faq import responder_faq
from app.dialogo.flujos.menu import (
    agradecimiento,
    bienvenida_con_menu,
    despedida,
    fuera_de_alcance,
    menu_principal,
)
from app.dialogo.tipos import Entrada, MensajeBot, con_opciones, texto_plano
from app.dialogo.validaciones import extraer_ticket
from app.models import Conversacion, Handoff, Mensaje
from app.services import sesiones

logger = logging.getLogger("app.dialogo.manager")

_OPCIONES_INTERINO = [
    ("registrar_incidencia", "📝 Registrar incidencia"),
    ("menu", "Volver al menú"),
]


@dataclass
class Turno:
    """Resultado de procesar un mensaje del usuario."""

    mensajes: list[MensajeBot]
    intent: str | None = None
    confianza: float | None = None
    via: str | None = None  # cómo se clasificó el intent: "regla" | "llm"
    # RN-05: durante el handoff (bot PAUSED) el mensaje del usuario se persiste y
    # se enruta al agente, pero el bot NO genera respuesta que deba almacenarse.
    persistir_bot: bool = True


class Orquestador:
    """Punto de entrada único del diálogo (usado por la capa API)."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or crear_engine()

    async def procesar(self, conv: Conversacion, entrada: Entrada, deps: Deps) -> Turno:
        """Procesa un turno completo según F-01."""
        # RN-05: bot pausado → el mensaje del usuario se enruta al agente humano.
        # El bot solo devuelve un acuse (que NO se persiste como respuesta del bot);
        # el agente ve el mensaje del usuario por el respaldo de polling del panel.
        if conv.estado_bot == "PAUSED":
            return Turno(
                mensajes=[
                    MensajeBot(
                        tipo="handoff",
                        texto="Tu mensaje fue enviado al agente del CTIC que atiende "
                        "esta conversación. Un momento, por favor...",
                    )
                ],
                persistir_bot=False,
            )

        # F-07: el handoff expiró sin atención (RN-09) → el bot ya volvió a ACTIVE;
        # se disculpa y ofrece registrar la incidencia en esta próxima interacción.
        if sesion_de(conv).get("handoff_expirado"):
            guardar_sesion(conv, {**sesion_de(conv), "handoff_expirado": False})
            self.engine.cancelar(conv)
            conv.fallback_consecutivos = 0
            return Turno(
                mensajes=[con_opciones(textos.HANDOFF_EXPIRADO, _OPCIONES_INTERINO)],
                intent="handoff_expirado",
            )

        # Escape global: volver al menú cancela cualquier flujo en curso
        if entrada.opcion_id == "menu":
            self.engine.cancelar(conv)
            conv.fallback_consecutivos = 0
            return Turno(mensajes=[menu_principal()], intent="menu", confianza=1.0)

        if conv.flujo_activo:
            intent_flujo = conv.flujo_activo
            try:
                mensajes = await self.engine.procesar(conv, entrada, deps)
            except FallbackDeFlujo:
                return await self._fallback(conv, deps)
            conv.fallback_consecutivos = 0
            return Turno(mensajes=mensajes, intent=intent_flujo)

        if entrada.opcion_id:
            return await self._opcion_global(conv, entrada, deps)

        texto = entrada.texto or ""
        detectado = router.detectar(texto)  # Capa 1: reglas (gratis, < 5 ms)
        if detectado.intent == "no_comprendida" and texto.strip():
            # Capa 2: clasificador LLM, solo si las reglas no deciden (prd/06 §2)
            detectado = await self._clasificar_capa2(conv, texto, deps) or detectado
        if (
            detectado.intent == "no_comprendida"
            or detectado.confianza < router.UMBRAL_CONFIANZA
        ):
            return await self._fallback(conv, deps)
        conv.fallback_consecutivos = 0
        mensajes = await self._despachar_intent(
            conv, detectado.intent, detectado.confianza, texto, deps
        )
        self._anotar_via(mensajes, detectado)
        return Turno(
            mensajes=mensajes,
            intent=detectado.intent,
            confianza=detectado.confianza,
            via=detectado.via,
        )

    # ---------------------------------------------------------------- capa 2

    async def _clasificar_capa2(
        self, conv: Conversacion, texto: str, deps: Deps
    ) -> router.IntentDetectado | None:
        """Consulta el clasificador LLM con los últimos 3 turnos como contexto."""
        if not clasificador.llm_activo():
            return None  # sin LLM: degradación silenciosa a capa 1 (prd/06 §6)
        historial = await self._historial_breve(conv, deps)
        resultado = await clasificador.clasificar_intencion(texto, historial)
        if resultado is None:
            return None
        return router.IntentDetectado(resultado.intent, resultado.confianza, via="llm")

    @staticmethod
    async def _historial_breve(conv: Conversacion, deps: Deps) -> list[str]:
        """Últimos turnos usuario/bot de la conversación (para el prompt)."""
        try:
            filas = (
                await deps.session.execute(
                    select(Mensaje.emisor, Mensaje.contenido)
                    .where(Mensaje.conversacion_id == conv.id)
                    .order_by(Mensaje.id.desc())
                    .limit(clasificador.TURNOS_HISTORIAL)
                )
            ).all()
        except Exception:  # noqa: BLE001 — el historial es opcional, nunca bloquea
            return []
        return [
            f"{'Usuario' if emisor == 'usuario' else 'Bot'}: {contenido[:200]}"
            for emisor, contenido in reversed(filas)
        ]

    @staticmethod
    def _anotar_via(mensajes: list[MensajeBot], detectado: router.IntentDetectado) -> None:
        """Registra en meta del primer mensaje la vía (regla|llm) y la confianza."""
        if not mensajes:
            return
        mensajes[0].meta = {
            **(mensajes[0].meta or {}),
            "via": detectado.via,
            "intent": detectado.intent,
            "confianza": detectado.confianza,
        }

    # -------------------------------------------------------------- opciones

    async def _opcion_global(self, conv: Conversacion, entrada: Entrada, deps: Deps) -> Turno:
        """Botones válidos fuera de un flujo (menú principal y follow-ups)."""
        opcion = entrada.opcion_id or ""
        if opcion in router.INTENTS_DE_MENU:
            conv.fallback_consecutivos = 0
            mensajes = await self._despachar_intent(conv, opcion, 1.0, "", deps)
            return Turno(mensajes=mensajes, intent=opcion, confianza=1.0)
        if opcion == "kb_util_si":
            conv.fallback_consecutivos = 0
            return Turno(
                mensajes=[texto_plano("¡Me alegra haberte ayudado!"), menu_principal()],
                intent="faq_general",
                confianza=1.0,
            )
        if opcion == "kb_util_no":
            conv.fallback_consecutivos = 0
            mensajes = [
                texto_plano(
                    "Lamento que la información no haya resuelto tu problema. "
                    "Registremos una incidencia para que un técnico te ayude."
                )
            ]
            mensajes += await self.engine.iniciar(conv, "registrar_incidencia", deps)
            return Turno(mensajes=mensajes, intent="registrar_incidencia", confianza=1.0)
        if opcion == "finalizar":
            conv.fallback_consecutivos = 0
            mensajes = await self.engine.iniciar(conv, "encuesta", deps)
            return Turno(mensajes=mensajes, intent="finalizar", confianza=1.0)
        # opción desconocida fuera de contexto → no comprendida (F-09)
        return await self._fallback(conv, deps)

    # --------------------------------------------------------------- intents

    async def _despachar_intent(
        self, conv: Conversacion, intent: str, confianza: float, texto: str, deps: Deps
    ) -> list[MensajeBot]:
        """Ejecuta la acción asociada a un intent comprendido (tabla prd/01 §2)."""
        if intent == "registrar_incidencia":
            return await self.engine.iniciar(conv, "registrar_incidencia", deps)

        if intent == "consultar_estado":
            datos = {}
            codigo = extraer_ticket(texto)
            if codigo:
                datos["codigo"] = codigo
            return await self.engine.iniciar(conv, "consultar_estado", deps, datos)

        if intent == "escalar_incidencia":
            datos = {}
            codigo = extraer_ticket(texto)
            if codigo:
                datos["codigo"] = codigo
            return await self.engine.iniciar(conv, "escalar_incidencia", deps, datos)

        if intent == "contactar_soporte":
            return await self._handoff(conv, deps, motivo="solicitud_usuario")

        if intent in ARBOL_POR_INTENT:
            # problema_internet / problema_aula_virtual / problema_software → F-05
            datos_diagnostico = {"arbol": ARBOL_POR_INTENT[intent]}
            if texto:
                datos_diagnostico["sintoma"] = texto
            return await self.engine.iniciar(conv, "diagnostico", deps, datos_diagnostico)

        if intent == "recuperar_correo":
            # RAG→Flujo (prd/01 §2): procedimiento desde la base de conocimiento
            consulta = texto or "recuperar contraseña del correo institucional"
            return await responder_faq(deps.session, consulta, intent, confianza)

        if intent == "faq_general":
            if not texto:
                # botón del menú: pedir la consulta (mini-flujo FAQ)
                return await self.engine.iniciar(conv, "faq", deps)
            return await responder_faq(deps.session, texto, intent, confianza)

        if intent == "info_ctic":
            return await responder_faq(deps.session, texto, intent, confianza)

        if intent == "saludo":
            return bienvenida_con_menu()

        if intent == "agradecimiento":
            return agradecimiento()

        if intent == "despedida":
            sesion = sesion_de(conv)
            if sesion.get("atencion") and not sesion.get("encuesta_ofrecida"):
                return await self.engine.iniciar(conv, "encuesta", deps)
            sesiones.marcar_cierre(conv, motivo="usuario")
            return despedida()

        if intent == "finalizar":
            return await self.engine.iniciar(conv, "encuesta", deps)

        if intent == "fuera_de_alcance":
            return fuera_de_alcance()

        logger.warning("Intent sin manejador: %s", intent)
        return [texto_plano(textos.FALLO_1)]

    # -------------------------------------------------------------- fallback

    async def _fallback(self, conv: Conversacion, deps: Deps) -> Turno:
        """F-09: fallo 1 → fallo 2 + menú → handoff (fallback_x3)."""
        conv.fallback_consecutivos = int(conv.fallback_consecutivos or 0) + 1
        nivel = conv.fallback_consecutivos
        if nivel == 1:
            mensajes = [texto_plano(textos.FALLO_1)]
        elif nivel == 2:
            mensajes = [con_opciones(textos.FALLO_2, textos.MENU_OPCIONES)]
        else:
            mensajes = await self._handoff(conv, deps, motivo="fallback_x3")
        return Turno(mensajes=mensajes, intent="no_comprendida", confianza=0.0)

    async def _handoff(self, conv: Conversacion, deps: Deps, motivo: str) -> list[MensajeBot]:
        """F-07: pausa el bot (RN-05) y crea el handoff pendiente para el panel.

        Los disparadores (``fallback_x3``, ``solicitud_usuario``) ponen el bot en
        PAUSED de verdad: a partir de aquí los mensajes del usuario se enrutan al
        agente humano. El panel lista la cola con los últimos 20 mensajes y, si
        nadie atiende en 10 minutos, el handoff expira (RN-09, ver sesiones.py).
        """
        handoff = Handoff(
            conversacion_id=conv.id,
            motivo=motivo,
            ticket_codigo=sesion_de(conv).get("ultimo_ticket"),
        )
        deps.session.add(handoff)
        # RN-05: el bot se pausa; se abandona cualquier flujo activo para que los
        # mensajes del usuario queden disponibles al agente (no al motor de intenciones).
        self.engine.cancelar(conv)
        conv.estado_bot = "PAUSED"
        conv.fallback_consecutivos = 0
        return [MensajeBot(tipo="handoff", texto=textos.TRANSICION_HANDOFF)]


_orquestador: Orquestador | None = None


def get_orquestador() -> Orquestador:
    """Singleton del orquestador (el motor de flujos no guarda estado propio)."""
    global _orquestador
    if _orquestador is None:
        _orquestador = Orquestador()
    return _orquestador
