"""Gestión de sesiones de chat: creación, autenticación por token, registro
de mensajes (RF-09) y cierre por inactividad (RN-09).

El sessionToken es opaco (`secrets.token_urlsafe(32)`); solo se persiste su
SHA-256 y la comparación se hace por hash en tiempo constante.
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.errors import ConflictError, UnauthorizedError
from app.dialogo import textos
from app.models import Conversacion, Handoff, Mensaje
from app.services import eventos

logger = logging.getLogger("app.services.sesiones")

INACTIVIDAD_MINUTOS = 15  # RN-09
HANDOFF_EXPIRACION_MINUTOS = 10  # F-07: sin atención en 10 min → expirado
INTERVALO_LOOP_S = 60


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def crear_sesion(
    session: AsyncSession, canal: str = "web_widget"
) -> tuple[Conversacion, str]:
    """Crea una conversación (sessionId UUID) y devuelve (conversacion, token)."""
    token = secrets.token_urlsafe(32)
    conv = Conversacion(
        codigo=str(uuid4()),
        session_token_hash=_hash_token(token),
        canal=canal,
    )
    session.add(conv)
    await session.flush()
    return conv, token


async def autenticar(
    session: AsyncSession, session_id: str, token: str | None
) -> Conversacion:
    """Autentica la sesión por sessionId + hash del token.

    401 si el token falta o no coincide; 409 si la conversación ya está cerrada.
    """
    if not token:
        raise UnauthorizedError("Falta el token de sesión (X-Session-Token).")
    conv = (
        await session.execute(select(Conversacion).where(Conversacion.codigo == session_id))
    ).scalar_one_or_none()
    if (
        conv is None
        or not conv.session_token_hash
        or not hmac.compare_digest(conv.session_token_hash, _hash_token(token))
    ):
        raise UnauthorizedError("La sesión de chat no es válida.")
    if conv.estado == "cerrada":
        raise ConflictError(textos.SESION_CERRADA)
    return conv


async def autenticar_por_token(session: AsyncSession, token: str | None) -> Conversacion:
    """Autentica solo por token (endpoints sin sessionId en el cuerpo).

    401 si el token falta o no coincide; 409 si la conversación está cerrada.
    """
    if not token:
        raise UnauthorizedError("Falta el token de sesión (X-Session-Token).")
    conv = (
        await session.execute(
            select(Conversacion).where(Conversacion.session_token_hash == _hash_token(token))
        )
    ).scalar_one_or_none()
    if conv is None:
        raise UnauthorizedError("La sesión de chat no es válida.")
    if conv.estado == "cerrada":
        raise ConflictError(textos.SESION_CERRADA)
    return conv


async def autenticar_stream(
    session: AsyncSession, session_id: str, token: str | None
) -> Conversacion:
    """Autentica una conexión SSE por sessionId + token (query param, no header).

    EventSource no envía cabeceras, por eso el token llega por query. A diferencia
    de ``autenticar`` NO rechaza conversaciones cerradas (el stream puede seguir
    entregando el evento de cierre); 401 solo si el token falta o no coincide.
    """
    if not token:
        raise UnauthorizedError("Falta el token de sesión.")
    conv = (
        await session.execute(select(Conversacion).where(Conversacion.codigo == session_id))
    ).scalar_one_or_none()
    if (
        conv is None
        or not conv.session_token_hash
        or not hmac.compare_digest(conv.session_token_hash, _hash_token(token))
    ):
        raise UnauthorizedError("La sesión de chat no es válida.")
    return conv


def guardar_mensaje(
    session: AsyncSession,
    conv: Conversacion,
    emisor: str,
    contenido: str,
    intent: str | None = None,
    confianza: float | None = None,
    latencia_ms: int | None = None,
) -> Mensaje:
    """Persiste un mensaje de la conversación (RF-09: auditoría completa)."""
    mensaje = Mensaje(
        conversacion_id=conv.id,
        emisor=emisor,
        contenido=contenido,
        intent=intent,
        confianza=confianza,
        latencia_ms=latencia_ms,
    )
    session.add(mensaje)
    return mensaje


def marcar_cierre(conv: Conversacion, motivo: str) -> None:
    """Marca la conversación como cerrada (motivo `usuario` | `timeout`)."""
    conv.estado = "cerrada"
    conv.finalizada_at = datetime.now()
    conv.motivo_cierre = motivo


async def cerrar_conversaciones_inactivas(
    session: AsyncSession, minutos: int = INACTIVIDAD_MINUTOS
) -> int:
    """Cierra conversaciones abiertas sin actividad por más de `minutos` (RN-09).

    Actividad = último mensaje registrado (o el inicio de la conversación si no
    hay mensajes). Los handoffs pendientes de esas conversaciones se marcan
    `expirado` (el panel llega en la Semana 5).
    """
    corte = datetime.now() - timedelta(minutes=minutos)
    resultado = await session.execute(
        sql_text(
            """
            UPDATE conversaciones c
            SET c.estado = 'cerrada',
                c.finalizada_at = NOW(),
                c.motivo_cierre = 'timeout'
            WHERE c.estado = 'abierta'
              AND c.iniciada_at < :corte
              AND NOT EXISTS (
                    SELECT 1 FROM mensajes m
                    WHERE m.conversacion_id = c.id AND m.created_at >= :corte
              )
            """
        ),
        {"corte": corte},
    )
    cerradas = int(getattr(resultado, "rowcount", 0) or 0)
    if cerradas:
        await session.execute(
            sql_text(
                """
                UPDATE handoffs h
                JOIN conversaciones c ON c.id = h.conversacion_id
                SET h.estado = 'expirado', h.cerrado_at = NOW()
                WHERE h.estado = 'pendiente'
                  AND c.estado = 'cerrada' AND c.motivo_cierre = 'timeout'
                """
            )
        )
        logger.info("Cierre por inactividad: %d conversaciones cerradas (RN-09)", cerradas)
    await session.commit()
    return cerradas


async def expirar_handoffs_pendientes(
    session: AsyncSession, minutos: int = HANDOFF_EXPIRACION_MINUTOS
) -> int:
    """F-07: marca `expirado` los handoffs pendientes sin atender por >`minutos`.

    Reactiva el bot (estado_bot='ACTIVE') y deja una marca en la conversación
    (`handoff_expirado`) para que, en la próxima interacción del usuario, el bot
    se disculpe y ofrezca registrar una incidencia (RN-09 / atención asíncrona).
    Además publica el cambio de estado por SSE para los widgets conectados.
    """
    from app.dialogo.engine import guardar_sesion, sesion_de

    corte = datetime.now() - timedelta(minutes=minutos)
    filas = (
        await session.execute(
            select(Handoff, Conversacion)
            .join(Conversacion, Conversacion.id == Handoff.conversacion_id)
            .where(Handoff.estado == "pendiente", Handoff.solicitado_at < corte)
        )
    ).all()
    for handoff, conv in filas:
        handoff.estado = "expirado"
        handoff.cerrado_at = datetime.now()
        conv.estado_bot = "ACTIVE"  # RN-06: el bot retoma la conversación
        guardar_sesion(conv, {**sesion_de(conv), "handoff_expirado": True})
    await session.commit()

    for _handoff, conv in filas:
        await eventos.publicar_estado(conv.codigo, "ACTIVE")
    if filas:
        logger.info(
            "Handoffs expirados por falta de atención (>%d min): %d (F-07)",
            minutos,
            len(filas),
        )
    return len(filas)


async def loop_cierre_inactividad(intervalo_s: int = INTERVALO_LOOP_S) -> None:
    """Tarea periódica: expira handoffs (F-07) y cierra conversaciones (RN-09)."""
    while True:
        await asyncio.sleep(intervalo_s)
        try:
            async with get_session_factory()() as session:
                await expirar_handoffs_pendientes(session)
                await cerrar_conversaciones_inactivas(session)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — el loop no debe morir por un fallo puntual
            logger.exception("Fallo en el cierre periódico por inactividad")
