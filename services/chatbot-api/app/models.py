"""Modelos SQLAlchemy 2 de chatbot_db (espejo exacto del DDL de alembic).

Tablas: conversaciones, mensajes, kb_articulos, handoffs
(prd/03 §3 + migración 0003: session_token_hash).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Valores de los ENUM del DDL (fuente única para validaciones)
CANALES: tuple[str, ...] = ("web_widget",)
ESTADOS_BOT: tuple[str, ...] = ("ACTIVE", "PAUSED")
ESTADOS_CONVERSACION: tuple[str, ...] = ("abierta", "cerrada")
EMISORES: tuple[str, ...] = ("usuario", "bot", "agente")
ESTADOS_HANDOFF: tuple[str, ...] = ("pendiente", "atendido", "cerrado", "expirado")


class Base(DeclarativeBase):
    """Base declarativa del servicio."""


class Conversacion(Base):
    """Sesión de chat del widget (una fila por sessionId)."""

    __tablename__ = "conversaciones"

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    codigo: Mapped[str] = mapped_column(
        mysql.CHAR(36), nullable=False, unique=True, comment="UUID v4 = sessionId del widget"
    )
    session_token_hash: Mapped[str | None] = mapped_column(
        mysql.CHAR(64), nullable=True, unique=True
    )
    usuario_correo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    usuario_nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    canal: Mapped[str] = mapped_column(
        mysql.ENUM(*CANALES), nullable=False, server_default=text("'web_widget'")
    )
    estado_bot: Mapped[str] = mapped_column(
        mysql.ENUM(*ESTADOS_BOT), nullable=False, server_default=text("'ACTIVE'")
    )
    estado: Mapped[str] = mapped_column(
        mysql.ENUM(*ESTADOS_CONVERSACION), nullable=False, server_default=text("'abierta'")
    )
    fallback_consecutivos: Mapped[int] = mapped_column(
        mysql.TINYINT(unsigned=True), nullable=False, server_default=text("0")
    )
    flujo_activo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    flujo_contexto: Mapped[dict[str, Any] | None] = mapped_column(mysql.JSON, nullable=True)
    iniciada_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    finalizada_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_cierre: Mapped[str | None] = mapped_column(String(30), nullable=True)

    mensajes: Mapped[list["Mensaje"]] = relationship(
        back_populates="conversacion", cascade="all, delete-orphan", order_by="Mensaje.id"
    )
    handoffs: Mapped[list["Handoff"]] = relationship(
        back_populates="conversacion", cascade="all, delete-orphan", order_by="Handoff.id"
    )


class Mensaje(Base):
    """Mensaje individual de una conversación (RF-09: auditoría completa)."""

    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    conversacion_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("conversaciones.id", ondelete="CASCADE"),
        nullable=False,
    )
    emisor: Mapped[str] = mapped_column(mysql.ENUM(*EMISORES), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confianza: Mapped[float | None] = mapped_column(mysql.DECIMAL(4, 3), nullable=True)
    latencia_ms: Mapped[int | None] = mapped_column(mysql.INTEGER(unsigned=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=3), nullable=False, server_default=text("CURRENT_TIMESTAMP(3)")
    )

    conversacion: Mapped[Conversacion] = relationship(back_populates="mensajes")


class KbArticulo(Base):
    """Artículo de la base de conocimiento (fuente del índice RAG y del FULLTEXT)."""

    __tablename__ = "kb_articulos"

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    contenido: Mapped[str] = mapped_column(mysql.MEDIUMTEXT, nullable=False)
    categoria: Mapped[str] = mapped_column(String(80), nullable=False)
    etiquetas: Mapped[str | None] = mapped_column(String(300), nullable=True)
    activo: Mapped[bool] = mapped_column(
        mysql.BOOLEAN, nullable=False, server_default=text("TRUE")
    )
    version: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("1")
    )
    updated_by: Mapped[int | None] = mapped_column(mysql.BIGINT(unsigned=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )


class Handoff(Base):
    """Solicitud de traspaso a agente humano (F-07)."""

    __tablename__ = "handoffs"

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    conversacion_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("conversaciones.id", ondelete="CASCADE"),
        nullable=False,
    )
    motivo: Mapped[str] = mapped_column(String(40), nullable=False)
    ticket_codigo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agente_id: Mapped[int | None] = mapped_column(mysql.BIGINT(unsigned=True), nullable=True)
    estado: Mapped[str] = mapped_column(
        mysql.ENUM(*ESTADOS_HANDOFF), nullable=False, server_default=text("'pendiente'")
    )
    solicitado_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    atendido_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cerrado_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    conversacion: Mapped[Conversacion] = relationship(back_populates="handoffs")
