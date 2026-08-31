"""Modelos SQLAlchemy 2 del dominio de tickets.

Mapean EXACTAMENTE las tablas migradas por Alembic (0001, 0003 y 0005):
usuarios, categorias, tickets, ticket_secuencias, ticket_historial,
ticket_adjuntos, encuestas, idempotency_keys y adjuntos_staging.
No se usa autogenerate: la fuente de verdad del DDL son las migraciones.
"""

import enum
from datetime import datetime

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class EstadoTicket(enum.StrEnum):
    """Estados del ciclo de vida de un ticket (RN-02). Valores exactos del ENUM."""

    REGISTRADO = "Registrado"
    ASIGNADO = "Asignado"
    EN_PROCESO = "En Proceso"
    ESCALADO = "Escalado"
    RESUELTO = "Resuelto"
    CERRADO = "Cerrado"


ESTADOS_TICKET: tuple[str, ...] = tuple(e.value for e in EstadoTicket)
# Migrado por 0004: "Escuela" reemplaza al antiguo concepto de "Área".
# Solo existen estos dos valores; los anteriores (Docente/Administrativo/
# Estudiante/Otro) fueron retirados por completo.
AREAS: tuple[str, ...] = (
    "Industrial",
    "Sistemas",
)
PRIORIDADES: tuple[str, ...] = ("Baja", "Media", "Alta")
ROLES: tuple[str, ...] = ("usuario", "tecnico", "admin")
ORIGENES: tuple[str, ...] = ("chatbot", "web")


class Base(DeclarativeBase):
    """Base declarativa del servicio de tickets."""


class Usuario(Base):
    """Usuario final o personal staff (tecnico/admin) — tabla `usuarios`."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    nombre: Mapped[str] = mapped_column(mysql.VARCHAR(120), nullable=False)
    correo: Mapped[str] = mapped_column(mysql.VARCHAR(150), nullable=False, unique=True)
    area: Mapped[str] = mapped_column(
        mysql.ENUM(*AREAS), nullable=False, server_default=text("'Industrial'")
    )
    rol: Mapped[str] = mapped_column(
        mysql.ENUM(*ROLES), nullable=False, server_default=text("'usuario'")
    )
    password_hash: Mapped[str | None] = mapped_column(mysql.VARCHAR(255))
    activo: Mapped[bool] = mapped_column(
        mysql.BOOLEAN(), nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="usuario", foreign_keys="Ticket.usuario_id"
    )
    tickets_asignados: Mapped[list["Ticket"]] = relationship(
        back_populates="tecnico", foreign_keys="Ticket.tecnico_id"
    )


class Categoria(Base):
    """Categoría de incidencia — tabla `categorias`."""

    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), primary_key=True, autoincrement=True
    )
    nombre: Mapped[str] = mapped_column(mysql.VARCHAR(80), nullable=False, unique=True)
    descripcion: Mapped[str | None] = mapped_column(mysql.VARCHAR(255))
    activo: Mapped[bool] = mapped_column(
        mysql.BOOLEAN(), nullable=False, server_default=text("1")
    )

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="categoria")


class Ticket(Base):
    """Incidencia registrada — tabla `tickets`."""

    __tablename__ = "tickets"
    __table_args__ = (
        Index("idx_tickets_estado", "estado"),
        Index("idx_tickets_usuario", "usuario_id"),
        Index("idx_tickets_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    codigo: Mapped[str] = mapped_column(mysql.VARCHAR(20), nullable=False, unique=True)
    usuario_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), ForeignKey("usuarios.id"), nullable=False
    )
    categoria_id: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), ForeignKey("categorias.id"), nullable=False
    )
    subcategoria: Mapped[str | None] = mapped_column(mysql.VARCHAR(120))
    descripcion: Mapped[str] = mapped_column(mysql.TEXT(), nullable=False)
    prioridad: Mapped[str] = mapped_column(
        mysql.ENUM(*PRIORIDADES), nullable=False, server_default=text("'Media'")
    )
    estado: Mapped[str] = mapped_column(
        mysql.ENUM(*ESTADOS_TICKET), nullable=False, server_default=text("'Registrado'")
    )
    tecnico_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True), ForeignKey("usuarios.id")
    )
    origen: Mapped[str] = mapped_column(
        mysql.ENUM(*ORIGENES), nullable=False, server_default=text("'chatbot'")
    )
    conversacion_codigo: Mapped[str | None] = mapped_column(mysql.CHAR(36))
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )
    resuelto_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME())
    respuesta: Mapped[str | None] = mapped_column(mysql.VARCHAR(1000))

    usuario: Mapped[Usuario] = relationship(back_populates="tickets", foreign_keys=[usuario_id])
    tecnico: Mapped[Usuario | None] = relationship(
        back_populates="tickets_asignados", foreign_keys=[tecnico_id]
    )
    categoria: Mapped[Categoria] = relationship(back_populates="tickets")
    historial: Mapped[list["TicketHistorial"]] = relationship(
        back_populates="ticket",
        order_by="TicketHistorial.id",
        cascade="all, delete-orphan",
    )
    adjuntos: Mapped[list["TicketAdjunto"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    encuestas: Mapped[list["Encuesta"]] = relationship(back_populates="ticket")


class TicketSecuencia(Base):
    """Correlativo anual para la generación del código de ticket (RN-01)."""

    __tablename__ = "ticket_secuencias"

    anio: Mapped[int] = mapped_column(
        mysql.SMALLINT(unsigned=True), primary_key=True, autoincrement=False
    )
    ultimo_nro: Mapped[int] = mapped_column(
        mysql.INTEGER(unsigned=True), nullable=False, server_default=text("0")
    )


class TicketHistorial(Base):
    """Traza de cambios de estado de un ticket (RN-02) — tabla `ticket_historial`."""

    __tablename__ = "ticket_historial"
    __table_args__ = (Index("idx_hist_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    ticket_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    estado_anterior: Mapped[str | None] = mapped_column(mysql.VARCHAR(20))
    estado_nuevo: Mapped[str] = mapped_column(mysql.VARCHAR(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(mysql.TEXT())
    actor_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True), ForeignKey("usuarios.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    ticket: Mapped[Ticket] = relationship(back_populates="historial")
    actor: Mapped[Usuario | None] = relationship()


class TicketAdjunto(Base):
    """Evidencia adjunta a un ticket (RF-13) — tabla `ticket_adjuntos`."""

    __tablename__ = "ticket_adjuntos"

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    ticket_id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    nombre_original: Mapped[str] = mapped_column(mysql.VARCHAR(255), nullable=False)
    ruta_almacenada: Mapped[str] = mapped_column(mysql.VARCHAR(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(mysql.VARCHAR(100), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    ticket: Mapped[Ticket] = relationship(back_populates="adjuntos")


class Encuesta(Base):
    """Encuesta de satisfacción 1–5 (RN-04) — tabla `encuestas`."""

    __tablename__ = "encuestas"

    id: Mapped[int] = mapped_column(
        mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    ticket_id: Mapped[int | None] = mapped_column(
        mysql.BIGINT(unsigned=True), ForeignKey("tickets.id")
    )
    conversacion_codigo: Mapped[str | None] = mapped_column(mysql.CHAR(36))
    calificacion: Mapped[int] = mapped_column(mysql.TINYINT(unsigned=True), nullable=False)
    comentario: Mapped[str | None] = mapped_column(mysql.VARCHAR(500))
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    ticket: Mapped[Ticket | None] = relationship(back_populates="encuestas")


class IdempotencyKey(Base):
    """Clave de idempotencia de API-01 (reintentos sin duplicar tickets)."""

    __tablename__ = "idempotency_keys"

    clave: Mapped[str] = mapped_column(mysql.VARCHAR(64), primary_key=True)
    ticket_codigo: Mapped[str] = mapped_column(mysql.VARCHAR(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AdjuntoStaging(Base):
    """Adjunto subido antes de que exista el ticket (API-01b) — tabla `adjuntos_staging`."""

    __tablename__ = "adjuntos_staging"

    id: Mapped[str] = mapped_column(mysql.CHAR(12), primary_key=True)
    nombre_original: Mapped[str] = mapped_column(mysql.VARCHAR(255), nullable=False)
    ruta_almacenada: Mapped[str] = mapped_column(mysql.VARCHAR(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(mysql.VARCHAR(100), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(mysql.INTEGER(unsigned=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
