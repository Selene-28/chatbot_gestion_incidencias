"""Capa de servicio del dominio de tickets (RN-01..RN-04).

Contrato compartido con el panel de agentes: las firmas públicas de este
módulo las consume código ajeno — no cambiarlas sin coordinar.
Cada función pública es una unidad transaccional: hace commit al terminar.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.models import (
    AREAS,
    ORIGENES,
    PRIORIDADES,
    AdjuntoStaging,
    Categoria,
    Encuesta,
    EstadoTicket,
    IdempotencyKey,
    Ticket,
    TicketAdjunto,
    TicketHistorial,
    TicketSecuencia,
    Usuario,
)
from app.schemas import comunes

logger = logging.getLogger(__name__)

# --- RN-02: matriz de transiciones de estado ---
TRANSICIONES: dict[str, frozenset[str]] = {
    EstadoTicket.REGISTRADO: frozenset({EstadoTicket.ASIGNADO, EstadoTicket.ESCALADO}),
    EstadoTicket.ASIGNADO: frozenset({EstadoTicket.EN_PROCESO, EstadoTicket.ESCALADO}),
    EstadoTicket.EN_PROCESO: frozenset({EstadoTicket.ESCALADO, EstadoTicket.RESUELTO}),
    EstadoTicket.ESCALADO: frozenset({EstadoTicket.EN_PROCESO}),
    EstadoTicket.RESUELTO: frozenset({EstadoTicket.CERRADO, EstadoTicket.EN_PROCESO}),
    EstadoTicket.CERRADO: frozenset(),
}

# Estados desde los que se permite escalar (API-03)
ESTADOS_ESCALABLES: frozenset[str] = frozenset(
    {EstadoTicket.REGISTRADO, EstadoTicket.ASIGNADO, EstadoTicket.EN_PROCESO}
)

# Carga ansiosa estándar de un ticket para serialización (evita lazy-load async)
_CARGA_COMPLETA = (
    selectinload(Ticket.usuario),
    selectinload(Ticket.categoria),
    selectinload(Ticket.tecnico),
    selectinload(Ticket.historial),
    selectinload(Ticket.adjuntos),
)


def es_transicion_valida(desde: str, hacia: str) -> bool:
    """Función pura de RN-02: indica si la transición de estado está permitida."""
    return hacia in TRANSICIONES.get(desde, frozenset())


# --------------------------------------------------------------------------
# Registro de incidencias (API-01, RN-01)
# --------------------------------------------------------------------------


async def registrar_incidencia(
    session: AsyncSession,
    *,
    nombre: str,
    correo: str,
    area: str,
    categoria: str,
    subcategoria: str | None,
    descripcion: str,
    prioridad: str,
    origen: str,
    conversacion_codigo: str | None,
    adjunto_id: str | None,
    idempotency_key: str | None,
) -> Ticket:
    """Registra una incidencia con código único INC-AAAA-NNNN (RN-01).

    Crea el usuario si el correo no existe (rol 'usuario'), inserta la fila
    inicial del historial y, si hay clave de idempotencia repetida, devuelve
    el ticket original sin crear otro.
    """
    correo = comunes.normalizar_correo(correo)
    _validar_datos_registro(correo=correo, area=area, prioridad=prioridad, origen=origen)

    if idempotency_key:
        existente = await session.get(IdempotencyKey, idempotency_key)
        if existente is not None:
            return await obtener_ticket(session, existente.ticket_codigo)

    fila_categoria = (
        await session.execute(
            select(Categoria).where(Categoria.nombre == categoria, Categoria.activo.is_(True))
        )
    ).scalar_one_or_none()
    if fila_categoria is None:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[
                {"field": "categoria", "description": "La categoría no existe o no está activa."}
            ],
        )

    # El FOR UPDATE de la secuencia (RN-01) serializa los registros concurrentes;
    # tomarlo ANTES del alta de usuario evita interbloqueos por correos duplicados.
    codigo = await _generar_codigo(session, anio=datetime.now().year)
    usuario = await _obtener_o_crear_usuario(session, nombre=nombre, correo=correo, area=area)

    ticket = Ticket(
        codigo=codigo,
        usuario_id=usuario.id,
        categoria_id=fila_categoria.id,
        subcategoria=subcategoria,
        descripcion=descripcion,
        prioridad=prioridad,
        estado=EstadoTicket.REGISTRADO.value,
        origen=origen,
        conversacion_codigo=conversacion_codigo,
    )
    session.add(ticket)
    await session.flush()

    # Fila inicial del historial (RN-02: todo cambio de estado deja traza)
    session.add(
        TicketHistorial(
            ticket_id=ticket.id,
            estado_anterior=None,
            estado_nuevo=EstadoTicket.REGISTRADO.value,
            comentario=None,
            actor_id=None,
        )
    )

    if adjunto_id:
        await _adjuntar_desde_staging(session, ticket_id=ticket.id, adjunto_id=adjunto_id)

    if idempotency_key:
        session.add(IdempotencyKey(clave=idempotency_key, ticket_codigo=codigo))

    try:
        await session.commit()
    except IntegrityError:
        # Carrera de idempotencia: otro reintento ganó la inserción de la clave.
        await session.rollback()
        if idempotency_key:
            existente = await session.get(IdempotencyKey, idempotency_key)
            if existente is not None:
                return await obtener_ticket(session, existente.ticket_codigo)
        raise

    return await obtener_ticket(session, codigo)


def _validar_datos_registro(*, correo: str, area: str, prioridad: str, origen: str) -> None:
    """Validaciones de dominio del registro (prd/01 §4)."""
    errores: list[dict[str, str]] = []
    if not comunes.es_correo_institucional(correo):
        errores.append({"field": "correo", "description": comunes.MSG_CORREO_DOMINIO})
    if area not in AREAS:
        errores.append(
            {"field": "area", "description": f"El área debe ser una de: {', '.join(AREAS)}."}
        )
    if prioridad not in PRIORIDADES:
        errores.append(
            {
                "field": "prioridad",
                "description": f"La prioridad debe ser una de: {', '.join(PRIORIDADES)}.",
            }
        )
    if origen not in ORIGENES:
        errores.append(
            {"field": "origen", "description": f"El origen debe ser uno de: {', '.join(ORIGENES)}."}
        )
    if errores:
        raise ValidationAppError("Los datos enviados son inválidos.", errors=errores)


async def _obtener_o_crear_usuario(
    session: AsyncSession, *, nombre: str, correo: str, area: str
) -> Usuario:
    """Devuelve el usuario del correo; si no existe lo crea con rol 'usuario'."""
    usuario = (
        await session.execute(select(Usuario).where(Usuario.correo == correo))
    ).scalar_one_or_none()
    if usuario is not None:
        return usuario
    try:
        async with session.begin_nested():
            usuario = Usuario(nombre=nombre, correo=correo, area=area, rol="usuario")
            session.add(usuario)
    except IntegrityError:
        # Carrera: otra transacción creó el mismo correo; se reutiliza.
        # Lectura con bloqueo: ve el último dato confirmado, no el snapshot
        # REPEATABLE READ previo (que aún no contiene la fila ganadora).
        usuario = (
            await session.execute(
                select(Usuario).where(Usuario.correo == correo).with_for_update()
            )
        ).scalar_one()
    return usuario


async def _generar_codigo(session: AsyncSession, *, anio: int) -> str:
    """RN-01: correlativo anual con SELECT ... FOR UPDATE sobre ticket_secuencias."""
    # Garantiza la fila del año (idempotente) antes de bloquearla.
    await session.execute(
        text(
            "INSERT INTO ticket_secuencias (anio, ultimo_nro) VALUES (:anio, 0) "
            "ON DUPLICATE KEY UPDATE anio = anio"
        ),
        {"anio": anio},
    )
    secuencia = (
        await session.execute(
            select(TicketSecuencia).where(TicketSecuencia.anio == anio).with_for_update()
        )
    ).scalar_one()
    secuencia.ultimo_nro += 1
    await session.flush()
    return f"INC-{anio}-{secuencia.ultimo_nro:04d}"


async def _adjuntar_desde_staging(
    session: AsyncSession, *, ticket_id: int, adjunto_id: str
) -> None:
    """Mueve un adjunto de staging al ticket (fila y archivo físico)."""
    staging = (
        await session.execute(
            select(AdjuntoStaging).where(AdjuntoStaging.id == adjunto_id).with_for_update()
        )
    ).scalar_one_or_none()
    if staging is None:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[
                {"field": "adjuntoId", "description": "El adjunto indicado no existe o expiró."}
            ],
        )

    origen = Path(staging.ruta_almacenada)
    if not origen.exists():
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[
                {"field": "adjuntoId", "description": "El archivo adjunto ya no está disponible."}
            ],
        )
    destino_dir = Path(get_settings().UPLOADS_DIR) / "tickets"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / origen.name
    shutil.move(str(origen), str(destino))

    session.add(
        TicketAdjunto(
            ticket_id=ticket_id,
            nombre_original=staging.nombre_original,
            ruta_almacenada=str(destino),
            mime_type=staging.mime_type,
            tamano_bytes=staging.tamano_bytes,
        )
    )
    await session.delete(staging)


# --------------------------------------------------------------------------
# Consulta (API-02, RN-03)
# --------------------------------------------------------------------------


async def obtener_ticket(session: AsyncSession, codigo: str) -> Ticket:
    """Devuelve el ticket con usuario/categoría/técnico/historial/adjuntos cargados."""
    ticket = (
        await session.execute(
            select(Ticket)
            .where(Ticket.codigo == codigo.strip())
            .options(*_CARGA_COMPLETA)
            # Refresca relaciones/colecciones aunque el objeto ya esté en la sesión
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("La incidencia indicada no existe.")
    return ticket


async def listar_por_correo(
    session: AsyncSession, correo: str, limite: int = 10
) -> list[Ticket]:
    """RN-03: lista solo los tickets del correo dado, del más reciente al más antiguo."""
    correo = comunes.normalizar_correo(correo)
    resultado = await session.execute(
        select(Ticket)
        .join(Usuario, Ticket.usuario_id == Usuario.id)
        .where(Usuario.correo == correo)
        .options(*_CARGA_COMPLETA)
        .execution_options(populate_existing=True)
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(limite)
    )
    return list(resultado.scalars().all())


# --------------------------------------------------------------------------
# Escalamiento (API-03) y cambios de estado (RN-02)
# --------------------------------------------------------------------------


async def escalar(session: AsyncSession, *, codigo: str, motivo: str, correo: str) -> Ticket:
    """Escala una incidencia a pedido del propietario (RN-03) desde estados válidos."""
    ticket = await obtener_ticket(session, codigo)
    if ticket.usuario.correo != comunes.normalizar_correo(correo):
        raise ForbiddenError("No tiene permiso para operar sobre esta incidencia.")
    if ticket.estado not in ESTADOS_ESCALABLES:
        raise ConflictError(
            f"La incidencia no puede escalarse desde el estado '{ticket.estado}'."
        )
    _aplicar_transicion(
        session,
        ticket=ticket,
        nuevo_estado=EstadoTicket.ESCALADO.value,
        comentario=motivo,
        actor_id=None,
    )
    await session.commit()
    return await obtener_ticket(session, codigo)


async def cambiar_estado(
    session: AsyncSession,
    *,
    codigo: str,
    nuevo_estado: str,
    actor_id: int | None,
    comentario: str | None = None,
) -> Ticket:
    """Cambia el estado validando la matriz RN-02; toda transición deja historial."""
    if nuevo_estado not in TRANSICIONES:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[
                {
                    "field": "estado",
                    "description": f"El estado debe ser uno de: {', '.join(TRANSICIONES)}.",
                }
            ],
        )
    ticket = await obtener_ticket(session, codigo)
    if not es_transicion_valida(ticket.estado, nuevo_estado):
        raise ConflictError(
            f"Transición de estado no permitida: '{ticket.estado}' → '{nuevo_estado}'."
        )
    _aplicar_transicion(
        session, ticket=ticket, nuevo_estado=nuevo_estado, comentario=comentario, actor_id=actor_id
    )
    await session.commit()
    return await obtener_ticket(session, codigo)


def _aplicar_transicion(
    session: AsyncSession,
    *,
    ticket: Ticket,
    nuevo_estado: str,
    comentario: str | None,
    actor_id: int | None,
) -> None:
    """Aplica el cambio de estado y registra la traza en ticket_historial (RN-02)."""
    estado_anterior = ticket.estado
    ticket.estado = nuevo_estado
    if nuevo_estado == EstadoTicket.RESUELTO:
        ticket.resuelto_at = datetime.now()
    elif estado_anterior == EstadoTicket.RESUELTO:
        ticket.resuelto_at = None  # reapertura
    session.add(
        TicketHistorial(
            ticket_id=ticket.id,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            comentario=comentario,
            actor_id=actor_id,
        )
    )


async def asignar_tecnico(
    session: AsyncSession, *, codigo: str, tecnico_id: int, actor_id: int
) -> Ticket:
    """Asigna un técnico; si el ticket estaba 'Registrado' pasa a 'Asignado' (RN-02)."""
    ticket = await obtener_ticket(session, codigo)
    if ticket.estado == EstadoTicket.CERRADO:
        raise ConflictError("No se puede asignar un técnico a una incidencia cerrada.")

    tecnico = await session.get(Usuario, tecnico_id)
    if tecnico is None or tecnico.rol not in ("tecnico", "admin") or not tecnico.activo:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[
                {
                    "field": "tecnicoId",
                    "description": "El técnico indicado no existe o no es válido.",
                }
            ],
        )

    estado_anterior = ticket.estado
    ticket.tecnico_id = tecnico_id
    nuevo_estado = (
        EstadoTicket.ASIGNADO.value
        if estado_anterior == EstadoTicket.REGISTRADO
        else estado_anterior
    )
    ticket.estado = nuevo_estado
    session.add(
        TicketHistorial(
            ticket_id=ticket.id,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            comentario=f"Técnico asignado: {tecnico.nombre}.",
            actor_id=actor_id,
        )
    )
    await session.commit()
    return await obtener_ticket(session, codigo)


ESTADOS_TERMINADOS: frozenset[str] = frozenset(
    {EstadoTicket.RESUELTO.value, EstadoTicket.CERRADO.value}
)


async def guardar_respuesta(
    session: AsyncSession, *, codigo: str, texto: str, actor_id: int
) -> Ticket:
    """Guarda la respuesta del técnico (máx. 1000 caracteres) sin cambiar estado."""
    limpio = (texto or "").strip()
    if not limpio:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[{"field": "respuesta", "description": "La respuesta no puede estar vacía."}],
        )
    if len(limpio) > comunes.RESPUESTA_MAX:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[
                {
                    "field": "respuesta",
                    "description": (
                        f"La respuesta no puede superar {comunes.RESPUESTA_MAX} caracteres."
                    ),
                }
            ],
        )
    if comunes.contiene_html(limpio):
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[{"field": "respuesta", "description": "La respuesta no puede contener HTML."}],
        )
    ticket = await obtener_ticket(session, codigo)
    ticket.respuesta = limpio
    session.add(
        TicketHistorial(
            ticket_id=ticket.id,
            estado_anterior=ticket.estado,
            estado_nuevo=ticket.estado,
            comentario=f"Respuesta registrada: {limpio}",
            actor_id=actor_id,
        )
    )
    await session.commit()
    return await obtener_ticket(session, codigo)


async def obtener_adjunto(
    session: AsyncSession, *, codigo: str, adjunto_id: int
) -> TicketAdjunto:
    """Devuelve un adjunto del ticket o 404 si no pertenece a ese código."""
    ticket = await obtener_ticket(session, codigo)
    for adjunto in ticket.adjuntos:
        if adjunto.id == adjunto_id:
            return adjunto
    raise NotFoundError("El adjunto indicado no existe.")


# --------------------------------------------------------------------------
# Listado para el panel (RF-11)
# --------------------------------------------------------------------------


async def listar_tickets(
    session: AsyncSession,
    *,
    estado: str | None = None,
    categoria_id: int | None = None,
    tecnico_id: int | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[Ticket], int]:
    """Listado paginado con filtros para el panel; devuelve (items, total)."""
    page = max(1, page)
    size = min(max(1, size), 100)  # prd/04 §5: máx 100 por página

    condiciones = []
    if estado is not None:
        if estado not in TRANSICIONES:
            raise ValidationAppError(
                "Los datos enviados son inválidos.",
                errors=[
                    {
                        "field": "estado",
                        "description": f"El estado debe ser uno de: {', '.join(TRANSICIONES)}.",
                    }
                ],
            )
        condiciones.append(Ticket.estado == estado)
    if categoria_id is not None:
        condiciones.append(Ticket.categoria_id == categoria_id)
    if tecnico_id is not None:
        condiciones.append(Ticket.tecnico_id == tecnico_id)

    total = (
        await session.execute(select(func.count()).select_from(Ticket).where(*condiciones))
    ).scalar_one()
    resultado = await session.execute(
        select(Ticket)
        .where(*condiciones)
        .options(*_CARGA_COMPLETA)
        .execution_options(populate_existing=True)
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(resultado.scalars().all()), int(total)


# --------------------------------------------------------------------------
# Encuesta de satisfacción (API-06, RN-04)
# --------------------------------------------------------------------------


async def registrar_encuesta(
    session: AsyncSession,
    *,
    ticket_codigo: str | None,
    conversacion_codigo: str | None,
    calificacion: int,
    comentario: str | None,
) -> Encuesta:
    """Registra la encuesta 1–5; una sola por atención (ticket o conversación)."""
    if not isinstance(calificacion, int) or not (1 <= calificacion <= 5):
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[{"field": "calificacion", "description": comunes.MSG_CALIFICACION}],
        )
    if not ticket_codigo and not conversacion_codigo:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[
                {
                    "field": "ticketId",
                    "description": "Debe indicar el ticket o la conversación que desea calificar.",
                }
            ],
        )

    ticket_id: int | None = None
    if ticket_codigo:
        ticket = await obtener_ticket(session, ticket_codigo)
        ticket_id = ticket.id
        duplicada = (
            await session.execute(
                select(func.count()).select_from(Encuesta).where(Encuesta.ticket_id == ticket_id)
            )
        ).scalar_one()
        if duplicada:
            raise ConflictError("Ya se registró una encuesta para esta atención.")
    if conversacion_codigo:
        duplicada = (
            await session.execute(
                select(func.count())
                .select_from(Encuesta)
                .where(Encuesta.conversacion_codigo == conversacion_codigo)
            )
        ).scalar_one()
        if duplicada:
            raise ConflictError("Ya se registró una encuesta para esta atención.")

    encuesta = Encuesta(
        ticket_id=ticket_id,
        conversacion_codigo=conversacion_codigo,
        calificacion=calificacion,
        comentario=comentario,
    )
    session.add(encuesta)
    await session.commit()
    await session.refresh(encuesta)
    return encuesta
