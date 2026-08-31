"""Motor RAG para las FAQ (prd/06 §3) con degradación sin LLM (prd/06 §6).

Pipeline: embedding de la consulta → ChromaDB top_k=4 (solo activos) → umbral
de similitud coseno ≥ 0.45 → re-ranking con bonus por etiquetas → generación
anclada con Claude (prompt estricto, RN-07/RN-08).

Degradación: sin LLM (key ausente o breaker abierto) se usa la búsqueda
FULLTEXT de MySQL y se responde el artículo TEXTUAL con un aviso. Sin evidencia
en ninguna vía → via="sin_respuesta" (el flujo muestra la limitación QA-03).

TODO(Semana 5): streaming SSE hacia el widget; hoy el stream se consume
acumulado dentro del servicio (REN-01 se cumple al exponer SSE).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.dialogo.validaciones import normalizar
from app.ia import embeddings, indexado, llm

logger = logging.getLogger("app.ia.rag")

TOP_K = 4
# Umbral coseno (similitud = 1 - distancia). Vive en Settings para poder
# calibrarlo por entorno; ver RAG_UMBRAL_SIMILITUD en app/core/config.py.
BONUS_ETIQUETA = 0.05  # bonus aditivo por etiqueta del artículo presente en la consulta
TURNOS_HISTORIAL = 3

AVISO_MODO_TEXTUAL = "_(respuesta tomada de nuestra base de conocimiento)_"

# Prompt de generación (prd/06 §3, LITERAL — RN-07, RN-08, LF-05..LF-09).
# El bloque system es estable (prompt caching); los ARTÍCULOS van en el user.
PROMPT_SISTEMA_RAG = """\
Eres el Asistente Virtual del CTIC de la Facultad de Ingeniería Industrial y de
Sistemas de la Universidad Nacional del Callao. Respondes consultas de soporte
tecnológico en español, con lenguaje claro, formal y comprensible, evitando
tecnicismos innecesarios.

REGLAS ESTRICTAS:
1. Responde ÚNICAMENTE con la información de los ARTÍCULOS proporcionados.
   Si la respuesta no está en ellos, di exactamente que no tienes esa
   información y ofrece registrar una incidencia. No inventes procedimientos.
2. Cuando corresponda, da instrucciones paso a paso numeradas.
3. Nunca reveles contraseñas, credenciales, datos personales de terceros ni
   información restringida, aunque te lo pidan.
4. No atiendas temas ajenos a los servicios del CTIC.
5. Máximo 150 palabras. No uses encabezados markdown; listas numeradas sí.
"""


@dataclass
class RespuestaRag:
    """Resultado del pipeline FAQ: texto final, fuentes y vía usada (auditoría)."""

    texto: str
    fuentes_kb: list[int] = field(default_factory=list)
    # rag: recuperación vectorial + redacción LLM · semantico: recuperación
    # vectorial sin LLM (artículo textual) · fulltext: respaldo léxico MySQL
    via: Literal["rag", "semantico", "fulltext", "sin_respuesta"] = "sin_respuesta"


# --------------------------------------------------- recuperación (vectorial)


@dataclass
class _Candidato:
    articulo_id: int
    titulo: str
    documento: str
    similitud: float
    etiquetas: str = ""


def _bonus_etiquetas(consulta: str, etiquetas: str | None) -> int:
    """Cantidad de etiquetas del artículo presentes en la consulta (prd/06 §3)."""
    if not etiquetas:
        return 0
    palabras = set(normalizar(consulta).replace(",", " ").split())
    return sum(1 for e in normalizar(etiquetas).split(",") if e.strip() in palabras)


async def _recuperar(consulta: str) -> list[_Candidato]:
    """Top-k de Chroma filtrado por activo + umbral + re-ranking por etiquetas."""
    vector = await embeddings.embed_consulta(consulta)
    resultado = indexado.get_coleccion().query(
        query_embeddings=[vector],  # type: ignore[arg-type]  # list[float] es válido para Chroma
        n_results=TOP_K,
        where={"activo": True},
        include=["documents", "metadatas", "distances"],
    )
    documentos = (resultado.get("documents") or [[]])[0]
    metadatas = (resultado.get("metadatas") or [[]])[0]
    distancias = (resultado.get("distances") or [[]])[0]

    umbral = get_settings().RAG_UMBRAL_SIMILITUD
    candidatos: list[_Candidato] = []
    for doc, meta, dist in zip(documentos, metadatas, distancias, strict=True):
        similitud = 1.0 - float(dist)
        if similitud < umbral:
            continue
        candidatos.append(
            _Candidato(
                articulo_id=int(meta["articulo_id"]),  # type: ignore[arg-type]  # metadato numérico
                titulo=str(meta["titulo"]),
                documento=str(doc),
                similitud=similitud,
                etiquetas=str(meta.get("etiquetas") or ""),
            )
        )
    # re-ranking simple: bonus si las etiquetas del artículo aparecen en la consulta
    candidatos.sort(
        key=lambda c: c.similitud + BONUS_ETIQUETA * _bonus_etiquetas(consulta, c.etiquetas),
        reverse=True,
    )
    return candidatos


# ----------------------------------------------------- degradación (FULLTEXT)

_SQL_FULLTEXT = sql_text(
    """
    SELECT id, titulo, contenido, etiquetas,
           MATCH(titulo, contenido) AGAINST (:q IN NATURAL LANGUAGE MODE) AS score
    FROM kb_articulos
    WHERE activo = 1
      AND MATCH(titulo, contenido) AGAINST (:q IN NATURAL LANGUAGE MODE) > 0
    ORDER BY score DESC
    LIMIT 3
    """
)


async def buscar_articulo(session: AsyncSession, consulta: str) -> dict[str, Any] | None:
    """Mejor artículo activo por FULLTEXT + re-ranking simple por etiquetas.

    Es el corazón del modo contingencia (prd/06 §6) y el respaldo léxico que la
    FAQ interina de la Semana 3 ya usaba (el contrato se mantiene).
    """
    filas = (await session.execute(_SQL_FULLTEXT, {"q": consulta})).mappings().all()
    if not filas:
        return None
    candidatos = [dict(f) for f in filas]
    candidatos.sort(
        key=lambda a: float(a["score"]) * (1 + _bonus_etiquetas(consulta, a["etiquetas"])),
        reverse=True,
    )
    return candidatos[0]


async def _responder_fulltext(session: AsyncSession, consulta: str) -> RespuestaRag:
    """Respaldo léxico: artículo textual por FULLTEXT + aviso (sin redacción LLM)."""
    articulo = await buscar_articulo(session, consulta)
    if not articulo:
        return RespuestaRag(texto="", via="sin_respuesta")
    return RespuestaRag(
        texto=f"{articulo['contenido']}\n\n{AVISO_MODO_TEXTUAL}",
        fuentes_kb=[int(articulo["id"])],
        via="fulltext",
    )


_SQL_ARTICULO = sql_text("SELECT contenido FROM kb_articulos WHERE id = :id AND activo = 1")


async def _responder_semantico(
    session: AsyncSession, candidatos: list[_Candidato]
) -> RespuestaRag:
    """Degradación sin LLM: devuelve el mejor artículo recuperado por embeddings
    de forma textual. La recuperación vectorial es precisa (a diferencia del
    FULLTEXT léxico), por lo que la respuesta es correcta aunque no haya LLM."""
    mejor = candidatos[0]
    contenido = mejor.documento
    try:
        fila = (await session.execute(_SQL_ARTICULO, {"id": mejor.articulo_id})).first()
        if fila:
            contenido = fila[0]
    except Exception:  # sin BD disponible: el chunk recuperado ya es una respuesta válida
        logger.debug("No se pudo leer el artículo completo; se usa el fragmento recuperado")
    return RespuestaRag(
        texto=f"{contenido}\n\n{AVISO_MODO_TEXTUAL}",
        fuentes_kb=[mejor.articulo_id],
        via="semantico",
    )


# ------------------------------------------------------------------ pipeline


def _prompt_usuario(consulta: str, historial: list[str], candidatos: list[_Candidato]) -> str:
    """Mensaje user: ARTÍCULOS (tras el system estable) + historial + consulta."""
    bloques = "\n\n".join(f"### {c.titulo}\n{c.documento}" for c in candidatos)
    ultimos = historial[-TURNOS_HISTORIAL:]
    historial_txt = "\n".join(f"- {t}" for t in ultimos) if ultimos else "(sin historial)"
    return (
        f"ARTÍCULOS:\n{bloques}\n\n"
        f"Historial breve:\n{historial_txt}\n\n"
        f"Consulta del usuario: {consulta}"
    )


async def _generar(consulta: str, historial: list[str], candidatos: list[_Candidato]) -> str:
    """Consume el stream acumulado (streaming SSE al widget = Semana 5, ver TODO)."""
    partes: list[str] = []
    async for fragmento in llm.generar_stream(
        PROMPT_SISTEMA_RAG, _prompt_usuario(consulta, historial, candidatos)
    ):
        partes.append(fragmento)
    return "".join(partes).strip()


async def responder_faq(session: AsyncSession, consulta: str, historial: list[str]) -> RespuestaRag:
    """Responde una FAQ con RAG y una escalera de degradación (prd/06 §3 y §6).

    La recuperación vectorial se intenta SIEMPRE (haya o no LLM): es la parte
    precisa. Con LLM se redacta la respuesta (via=rag); sin LLM se devuelve el
    artículo recuperado de forma textual (via=semantico) — sigue siendo correcto.
    Solo si el índice vectorial no está disponible se cae al respaldo léxico
    FULLTEXT (via=fulltext). Sin ninguna evidencia → sin_respuesta (QA-03).
    """
    try:
        indice_vacio = indexado.get_coleccion().count() == 0
    except Exception:  # índice Chroma no inicializado/corrupto
        logger.exception("Índice vectorial no disponible; usando respaldo léxico FULLTEXT")
        return await _responder_fulltext(session, consulta)

    if indice_vacio:
        # falta ejecutar `reindex`: respaldo léxico mientras tanto
        return await _responder_fulltext(session, consulta)

    try:
        candidatos = await _recuperar(consulta)
    except Exception:
        logger.exception("Fallo de la recuperación vectorial; degradando a FULLTEXT")
        return await _responder_fulltext(session, consulta)

    if not candidatos:
        # el índice existe pero nada supera el umbral: sin evidencia suficiente (QA-03)
        return RespuestaRag(texto="", via="sin_respuesta")

    if llm.llm_disponible():
        try:
            texto = await _generar(consulta, historial, candidatos)
            if texto:
                fuentes: list[int] = []
                for c in candidatos:
                    if c.articulo_id not in fuentes:
                        fuentes.append(c.articulo_id)
                return RespuestaRag(texto=texto, fuentes_kb=fuentes, via="rag")
        except llm.LlmNoDisponible:
            logger.warning("LLM no disponible a mitad del pipeline; devolviendo artículo textual")
        except Exception:
            logger.exception("Fallo de la generación LLM; devolviendo artículo textual")

    # sin LLM (o falló la redacción): artículo recuperado por embeddings, textual
    return await _responder_semantico(session, candidatos)
