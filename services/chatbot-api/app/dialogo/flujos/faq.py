"""FAQ (F-04): motor RAG con degradación FULLTEXT (prd/06 §3 y §6).

Semana 4: el corazón de la FAQ es `app.ia.rag.responder_faq` (embeddings +
ChromaDB + generación anclada con Claude). Sin LLM (key ausente o breaker
abierto) degrada al FULLTEXT de MySQL con el artículo textual + aviso.

El contrato del flujo:
- cuando hay evidencia: solo el texto completo de la respuesta (sin botones
  adicionales que oculten o empujen el contenido);
- limitación QA-03 + ofrecer registrar incidencia cuando no la hay;
- `meta.fuentesKb` (IDs de artículos) para auditoría de fundamentación y
  `meta.via` ("rag" | "fulltext" | "sin_respuesta") para el análisis de calidad.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dialogo import textos
from app.dialogo.engine import Deps, Resultado
from app.dialogo.tipos import Entrada, MensajeBot, con_opciones
from app.ia import rag
from app.ia.rag import buscar_articulo
from app.models import Conversacion, KbArticulo, Mensaje

CATEGORIA_INFO_CTIC = "Información CTIC"
CONSULTA_INFO_CTIC = "horario atención contacto ubicación teléfono CTIC"

_OPCIONES_SIN_RESPUESTA: list[tuple[str, str]] = [
    ("registrar_incidencia", "📝 Registrar incidencia"),
    ("menu", "Volver al menú"),
]

# Menú de botones del F-04 ("❓ Preguntas frecuentes"). Cada opción resuelve
# de forma directa (sin RAG) contra el artículo de la KB con ese título
# exacto — ver los artículos "FAQ: ..." en app/scripts/datos_kb.py.
_OPCIONES_FAQ: list[tuple[str, str]] = [
    ("faq_horario", "¿Cuál es el horario de atención?"),
    ("faq_comunicados", "¿Dónde puedo encontrar los comunicados oficiales?"),
    ("faq_matricula", "¿Cómo realizo mi matrícula?"),
    ("faq_no_matricula", "¿Qué hago si no puedo matricularme?"),
    ("faq_rectificacion", "¿Cómo solicito una rectificación de matrícula?"),
    ("faq_ingreso_sga", "¿Cómo ingreso al SGA?"),
    ("faq_clave_sga", "Olvidé mi contraseña del SGA"),
    ("faq_funciones_sga", "¿Qué puedo hacer desde el SGA?"),
    ("faq_constancia", "¿Cómo solicito una constancia de estudios?"),
    ("faq_tesis", "¿Dónde presento mi proyecto de tesis?"),
]

_TITULO_KB_POR_OPCION: dict[str, str] = {
    "faq_horario": "FAQ: ¿Cuál es el horario de atención?",
    "faq_comunicados": "FAQ: ¿Dónde puedo encontrar los comunicados oficiales?",
    "faq_matricula": "FAQ: ¿Cómo realizo mi matrícula?",
    "faq_no_matricula": "FAQ: ¿Qué hago si no puedo matricularme?",
    "faq_rectificacion": "FAQ: ¿Cómo solicito una rectificación de matrícula?",
    "faq_ingreso_sga": "FAQ: ¿Cómo ingreso al SGA?",
    "faq_clave_sga": "FAQ: Olvidé mi contraseña del SGA",
    "faq_funciones_sga": "FAQ: ¿Qué puedo hacer desde el SGA?",
    "faq_constancia": "FAQ: ¿Cómo solicito una constancia de estudios?",
    "faq_tesis": "FAQ: ¿Dónde presento mi proyecto de tesis?",
}


async def articulo_por_titulo(session: AsyncSession, titulo: str) -> dict[str, Any] | None:
    """Artículo activo de la KB con título exacto (para menús de botones fijos)."""
    fila = (
        (
            await session.execute(
                select(KbArticulo.id, KbArticulo.titulo, KbArticulo.contenido)
                .where(KbArticulo.activo.is_(True), KbArticulo.titulo == titulo)
                .limit(1)
            )
        )
        .mappings()
        .first()
    )
    return dict(fila) if fila else None


async def articulo_info_ctic(session: AsyncSession) -> dict[str, Any] | None:
    """Artículo de información del CTIC (por categoría; FULLTEXT como respaldo)."""
    fila = (
        (
            await session.execute(
                select(KbArticulo.id, KbArticulo.titulo, KbArticulo.contenido)
                .where(KbArticulo.activo.is_(True), KbArticulo.categoria == CATEGORIA_INFO_CTIC)
                .order_by(KbArticulo.updated_at.desc())
                .limit(1)
            )
        )
        .mappings()
        .first()
    )
    if fila:
        return dict(fila)
    return await buscar_articulo(session, CONSULTA_INFO_CTIC)


async def _historial_reciente(session: AsyncSession, conv: Conversacion) -> list[str]:
    """Últimos turnos de texto del usuario (para preguntas de seguimiento)."""
    filas = (
        (
            await session.execute(
                select(Mensaje.contenido)
                .where(Mensaje.conversacion_id == conv.id, Mensaje.emisor == "usuario")
                .order_by(Mensaje.id.desc())
                .limit(rag.TURNOS_HISTORIAL)
            )
        )
        .scalars()
        .all()
    )
    return list(reversed(filas))


def _respuesta_con_texto(
    texto: str, fuentes_kb: list[int], via: str, intent: str, confianza: float
) -> list[MensajeBot]:
    """Respuesta con evidencia: solo el texto completo del artículo."""
    return [
        MensajeBot(
            tipo="texto",
            texto=texto,
            meta={
                "intent": intent,
                "confianza": confianza,
                "fuentesKb": fuentes_kb,
                "via": via,
            },
        ),
    ]


def _respuesta_sin_articulo(intent: str, confianza: float) -> list[MensajeBot]:
    """Limitación QA-03 + oferta de registrar incidencia."""
    return [
        con_opciones(
            textos.KB_SIN_RESPUESTA,
            _OPCIONES_SIN_RESPUESTA,
            meta={"intent": intent, "confianza": confianza, "via": "sin_respuesta"},
        )
    ]


async def responder_faq(
    session: AsyncSession,
    consulta: str,
    intent: str,
    confianza: float,
    historial: list[str] | None = None,
) -> list[MensajeBot]:
    """Resuelve una consulta FAQ/info_ctic contra la base de conocimiento."""
    if intent == "info_ctic":
        articulo = await articulo_info_ctic(session)
        if articulo:
            return _respuesta_con_texto(
                str(articulo["contenido"]),
                [int(articulo["id"])],
                "fulltext",
                intent,
                confianza,
            )
        return _respuesta_sin_articulo(intent, confianza)

    respuesta = await rag.responder_faq(session, consulta, historial or [])
    if respuesta.via == "sin_respuesta":
        return _respuesta_sin_articulo(intent, confianza)
    return _respuesta_con_texto(
        respuesta.texto, respuesta.fuentes_kb, respuesta.via, intent, confianza
    )


class FlujoFaq:
    """Mini-flujo para el botón '❓ Preguntas frecuentes': muestra el menú de
    preguntas y responde con el artículo de la KB correspondiente."""

    nombre = "faq"

    async def iniciar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        """Muestra el menú de preguntas frecuentes."""
        return Resultado(
            mensajes=[con_opciones("¿Sobre qué tema quieres saber más?", _OPCIONES_FAQ)],
            paso="consulta",
        )

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        """Resuelve la opción elegida contra su artículo fijo de la KB.

        Si en vez de pulsar un botón el usuario escribe texto libre, se
        mantiene compatibilidad con el buscador RAG/FULLTEXT anterior.
        """
        titulo = _TITULO_KB_POR_OPCION.get(entrada.opcion_id or "")
        if titulo:
            articulo = await articulo_por_titulo(deps.session, titulo)
            if articulo:
                mensajes = _respuesta_con_texto(
                    str(articulo["contenido"]),
                    [int(articulo["id"])],
                    "fulltext",
                    "faq_general",
                    1.0,
                )
                return Resultado(mensajes=mensajes, terminar=True)
            return Resultado(mensajes=_respuesta_sin_articulo("faq_general", 1.0), terminar=True)

        if not entrada.texto:
            return Resultado(
                mensajes=[
                    con_opciones("Por favor, elige una de las opciones.", _OPCIONES_FAQ)
                ],
                invalida=True,
            )
        historial = await _historial_reciente(deps.session, conv)
        mensajes = await responder_faq(
            deps.session, entrada.texto, "faq_general", 1.0, historial=historial
        )
        return Resultado(mensajes=mensajes, terminar=True)
