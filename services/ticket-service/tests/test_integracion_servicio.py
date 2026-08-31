"""Pruebas de integración de la capa de servicio contra MySQL real (tickets_test).

Cubre: QA-01 (registro), criterio 2.1 (concurrencia), idempotencia, QA-02
(consulta y RN-03), QA-05 (escalado), RN-02 (transiciones), QA-10 (encuesta)
y adjuntos staging→ticket.
"""

import asyncio
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from app.models import AdjuntoStaging, Ticket, TicketSecuencia, Usuario
from app.services.adjuntos import purgar_huerfanos, subir_adjunto
from app.services.tickets import (
    asignar_tecnico,
    cambiar_estado,
    escalar,
    guardar_respuesta,
    listar_por_correo,
    listar_tickets,
    obtener_ticket,
    registrar_encuesta,
    registrar_incidencia,
)

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _correo() -> str:
    return f"u{uuid.uuid4().hex[:10]}@unac.edu.pe"


async def _registrar(sesion, correo: str | None = None, **extra):
    datos = {
        "nombre": "Juan Pérez",
        "correo": correo or _correo(),
        "area": "Industrial",
        "categoria": "Correo Institucional",
        "subcategoria": "Recuperación de contraseña",
        "descripcion": "No puedo acceder a mi correo institucional.",
        "prioridad": "Media",
        "origen": "chatbot",
        "conversacion_codigo": None,
        "adjunto_id": None,
        "idempotency_key": None,
    }
    datos.update(extra)
    return await registrar_incidencia(sesion, **datos)


# --- QA-01: registro completo con usuario nuevo ---


async def test_registro_completo_usuario_nuevo(sesion) -> None:
    correo = _correo()
    ticket = await _registrar(sesion, correo=correo)

    assert re.fullmatch(r"INC-\d{4}-\d{4}", ticket.codigo)
    assert ticket.estado == "Registrado"
    assert ticket.prioridad == "Media"
    assert ticket.categoria.nombre == "Correo Institucional"
    assert ticket.usuario.correo == correo
    assert ticket.usuario.rol == "usuario"  # usuario creado automáticamente
    assert ticket.usuario.area == "Industrial"
    assert ticket.tecnico is None
    assert ticket.created_at is not None
    # Fila inicial del historial (RN-02)
    assert len(ticket.historial) == 1
    assert ticket.historial[0].estado_anterior is None
    assert ticket.historial[0].estado_nuevo == "Registrado"


async def test_registro_reutiliza_usuario_existente(sesion) -> None:
    correo = _correo()
    t1 = await _registrar(sesion, correo=correo)
    t2 = await _registrar(sesion, correo=correo)
    assert t1.usuario_id == t2.usuario_id
    total = (
        await sesion.execute(
            select(func.count()).select_from(Usuario).where(Usuario.correo == correo)
        )
    ).scalar_one()
    assert total == 1


async def test_registro_valida_dominio_y_categoria(sesion) -> None:
    with pytest.raises(ValidationAppError):
        await _registrar(sesion, correo="externo@gmail.com")
    with pytest.raises(ValidationAppError):
        await _registrar(sesion, categoria="Categoría Inexistente")
    with pytest.raises(ValidationAppError):
        await _registrar(sesion, area="Externo")


# --- Criterio 2.1: registros concurrentes → códigos únicos y correlativos ---


async def test_30_registros_concurrentes_codigos_unicos(fabrica_sesiones) -> None:
    async def _crear(i: int) -> str:
        async with fabrica_sesiones() as sesion_propia:
            ticket = await _registrar(sesion_propia, correo=f"conc{i}@unac.edu.pe")
            return ticket.codigo

    codigos = await asyncio.gather(*(_crear(i) for i in range(30)))

    assert len(set(codigos)) == 30  # únicos
    numeros = sorted(int(c.rsplit("-", 1)[1]) for c in codigos)
    assert numeros == list(range(numeros[0], numeros[0] + 30))  # correlativos sin huecos


async def test_secuencia_coherente_con_tickets(sesion) -> None:
    ticket = await _registrar(sesion)
    anio = int(ticket.codigo.split("-")[1])
    secuencia = (
        await sesion.execute(select(TicketSecuencia).where(TicketSecuencia.anio == anio))
    ).scalar_one()
    assert secuencia.ultimo_nro == int(ticket.codigo.rsplit("-", 1)[1])


# --- Idempotencia (API-01) ---


async def test_idempotencia_devuelve_ticket_original(sesion) -> None:
    clave = f"idem-{uuid.uuid4().hex}"
    correo = _correo()
    t1 = await _registrar(sesion, correo=correo, idempotency_key=clave)
    t2 = await _registrar(sesion, correo=correo, idempotency_key=clave)
    assert t1.codigo == t2.codigo
    total = (
        await sesion.execute(
            select(func.count())
            .select_from(Ticket)
            .join(Usuario, Ticket.usuario_id == Usuario.id)
            .where(Usuario.correo == correo)
        )
    ).scalar_one()
    assert total == 1  # no se creó un segundo ticket


async def test_idempotencia_concurrente(fabrica_sesiones) -> None:
    clave = f"idem-{uuid.uuid4().hex}"
    correo = _correo()

    async def _crear() -> str:
        async with fabrica_sesiones() as sesion_propia:
            ticket = await _registrar(sesion_propia, correo=correo, idempotency_key=clave)
            return ticket.codigo

    codigos = await asyncio.gather(*(_crear() for _ in range(5)))
    assert len(set(codigos)) == 1


# --- QA-02: consulta por código y por correo, RN-03 ---


async def test_consulta_por_codigo_y_por_correo(sesion) -> None:
    correo = _correo()
    ticket = await _registrar(sesion, correo=correo)

    encontrado = await obtener_ticket(sesion, ticket.codigo)
    assert encontrado.id == ticket.id
    assert encontrado.categoria.nombre == "Correo Institucional"
    assert encontrado.historial  # cargado

    lista = await listar_por_correo(sesion, correo)
    assert [t.codigo for t in lista] == [ticket.codigo]


async def test_consulta_codigo_inexistente(sesion) -> None:
    with pytest.raises(NotFoundError):
        await obtener_ticket(sesion, "INC-1999-9999")


async def test_listar_por_correo_maximo_10(sesion) -> None:
    correo = _correo()
    for _ in range(12):
        await _registrar(sesion, correo=correo)
    lista = await listar_por_correo(sesion, correo)
    assert len(lista) == 10
    # Orden: del más reciente al más antiguo
    ids = [t.id for t in lista]
    assert ids == sorted(ids, reverse=True)


async def test_listar_por_correo_ajeno_no_filtra(sesion) -> None:
    await _registrar(sesion)
    assert await listar_por_correo(sesion, _correo()) == []


# --- QA-05: escalado válido e inválido (API-03, RN-03) ---


async def test_escalar_valido_registra_motivo(sesion) -> None:
    correo = _correo()
    ticket = await _registrar(sesion, correo=correo)
    motivo = "No fue posible resolver mediante el chatbot."

    escalado = await escalar(sesion, codigo=ticket.codigo, motivo=motivo, correo=correo)

    assert escalado.estado == "Escalado"
    ultimo = escalado.historial[-1]
    assert ultimo.estado_anterior == "Registrado"
    assert ultimo.estado_nuevo == "Escalado"
    assert ultimo.comentario == motivo


async def test_escalar_correo_ajeno_forbidden(sesion) -> None:
    ticket = await _registrar(sesion)
    with pytest.raises(ForbiddenError):
        await escalar(sesion, codigo=ticket.codigo, motivo="Motivo.", correo=_correo())


async def test_escalar_desde_estado_invalido_conflict(sesion) -> None:
    correo = _correo()
    ticket = await _registrar(sesion, correo=correo)
    await escalar(sesion, codigo=ticket.codigo, motivo="Primera vez.", correo=correo)
    with pytest.raises(ConflictError):  # ya está Escalado
        await escalar(sesion, codigo=ticket.codigo, motivo="Otra vez.", correo=correo)


# --- RN-02: transiciones de estado ---


async def test_ciclo_de_vida_completo(sesion) -> None:
    ticket = await _registrar(sesion)
    tecnico_id = (
        await sesion.execute(select(Usuario.id).where(Usuario.correo == "tecnico1@ctic.local"))
    ).scalar_one()

    asignado = await asignar_tecnico(
        sesion, codigo=ticket.codigo, tecnico_id=tecnico_id, actor_id=tecnico_id
    )
    assert asignado.estado == "Asignado"
    assert asignado.tecnico.nombre == "Paul Barzola"

    en_proceso = await cambiar_estado(
        sesion, codigo=ticket.codigo, nuevo_estado="En Proceso", actor_id=tecnico_id
    )
    assert en_proceso.estado == "En Proceso"
    assert en_proceso.resuelto_at is None

    resuelto = await cambiar_estado(
        sesion,
        codigo=ticket.codigo,
        nuevo_estado="Resuelto",
        actor_id=tecnico_id,
        comentario="Se restableció la contraseña.",
    )
    assert resuelto.estado == "Resuelto"
    assert resuelto.resuelto_at is not None  # RN-02: al resolver se fija resuelto_at

    cerrado = await cambiar_estado(
        sesion, codigo=ticket.codigo, nuevo_estado="Cerrado", actor_id=tecnico_id
    )
    assert cerrado.estado == "Cerrado"

    # Historial completo con actores (RN-02)
    estados = [(h.estado_anterior, h.estado_nuevo) for h in cerrado.historial]
    assert estados == [
        (None, "Registrado"),
        ("Registrado", "Asignado"),
        ("Asignado", "En Proceso"),
        ("En Proceso", "Resuelto"),
        ("Resuelto", "Cerrado"),
    ]
    assert cerrado.historial[-1].actor_id == tecnico_id


async def test_guardar_respuesta_del_tecnico(sesion) -> None:
    ticket = await _registrar(sesion)
    tecnico_id = (
        await sesion.execute(select(Usuario.id).where(Usuario.correo == "tecnico1@ctic.local"))
    ).scalar_one()
    actualizado = await guardar_respuesta(
        sesion,
        codigo=ticket.codigo,
        texto="Se restableció el acceso al correo institucional.",
        actor_id=tecnico_id,
    )
    assert actualizado.respuesta == "Se restableció el acceso al correo institucional."
    assert any(h.comentario == "Respuesta registrada." for h in actualizado.historial)
    with pytest.raises(ValidationAppError):
        await guardar_respuesta(sesion, codigo=ticket.codigo, texto="  ", actor_id=tecnico_id)
    with pytest.raises(ValidationAppError):
        await guardar_respuesta(
            sesion, codigo=ticket.codigo, texto="<b>html</b>", actor_id=tecnico_id
        )


async def test_transicion_invalida_conflict(sesion) -> None:
    ticket = await _registrar(sesion)
    with pytest.raises(ConflictError):  # Registrado → Resuelto no permitido
        await cambiar_estado(sesion, codigo=ticket.codigo, nuevo_estado="Resuelto", actor_id=None)
    with pytest.raises(ValidationAppError):  # estado inexistente
        await cambiar_estado(sesion, codigo=ticket.codigo, nuevo_estado="Perdido", actor_id=None)


async def test_cerrado_es_terminal_en_bd(sesion) -> None:
    correo = _correo()
    ticket = await _registrar(sesion, correo=correo)
    tecnico_id = (
        await sesion.execute(select(Usuario.id).where(Usuario.correo == "tecnico1@ctic.local"))
    ).scalar_one()
    await asignar_tecnico(sesion, codigo=ticket.codigo, tecnico_id=tecnico_id, actor_id=tecnico_id)
    await cambiar_estado(sesion, codigo=ticket.codigo, nuevo_estado="En Proceso", actor_id=None)
    await cambiar_estado(sesion, codigo=ticket.codigo, nuevo_estado="Resuelto", actor_id=None)
    await cambiar_estado(sesion, codigo=ticket.codigo, nuevo_estado="Cerrado", actor_id=None)
    for destino in ("Asignado", "En Proceso", "Escalado", "Resuelto"):
        with pytest.raises(ConflictError):
            await cambiar_estado(sesion, codigo=ticket.codigo, nuevo_estado=destino, actor_id=None)


async def test_listar_tickets_con_filtros(sesion) -> None:
    correo = _correo()
    ticket = await _registrar(sesion, correo=correo)
    await escalar(sesion, codigo=ticket.codigo, motivo="Se requiere soporte.", correo=correo)

    escalados, total = await listar_tickets(sesion, estado="Escalado")
    assert total >= 1
    assert all(t.estado == "Escalado" for t in escalados)
    assert any(t.codigo == ticket.codigo for t in escalados)

    _, total_pagina = await listar_tickets(sesion, page=1, size=1)
    assert total_pagina == (await listar_tickets(sesion))[1]


# --- QA-10: encuesta (API-06, RN-04) ---


async def test_encuesta_valida_por_ticket(sesion) -> None:
    ticket = await _registrar(sesion)
    encuesta = await registrar_encuesta(
        sesion,
        ticket_codigo=ticket.codigo,
        conversacion_codigo=None,
        calificacion=5,
        comentario="La atención fue rápida y clara.",
    )
    assert encuesta.id is not None
    assert encuesta.ticket_id == ticket.id
    assert encuesta.calificacion == 5


async def test_encuesta_duplicada_conflict(sesion) -> None:
    ticket = await _registrar(sesion)
    await registrar_encuesta(
        sesion, ticket_codigo=ticket.codigo, conversacion_codigo=None, calificacion=4,
        comentario=None,
    )
    with pytest.raises(ConflictError):  # RN-04: una sola por atención
        await registrar_encuesta(
            sesion, ticket_codigo=ticket.codigo, conversacion_codigo=None, calificacion=5,
            comentario=None,
        )


async def test_encuesta_duplicada_por_conversacion(sesion) -> None:
    codigo_conv = str(uuid.uuid4())
    await registrar_encuesta(
        sesion, ticket_codigo=None, conversacion_codigo=codigo_conv, calificacion=3,
        comentario=None,
    )
    with pytest.raises(ConflictError):
        await registrar_encuesta(
            sesion, ticket_codigo=None, conversacion_codigo=codigo_conv, calificacion=3,
            comentario=None,
        )


@pytest.mark.parametrize("calificacion", [0, 6])
async def test_encuesta_fuera_de_rango(sesion, calificacion: int) -> None:
    with pytest.raises(ValidationAppError):
        await registrar_encuesta(
            sesion, ticket_codigo=None, conversacion_codigo="conv-x",
            calificacion=calificacion, comentario=None,
        )


async def test_encuesta_sin_referencia(sesion) -> None:
    with pytest.raises(ValidationAppError):
        await registrar_encuesta(
            sesion, ticket_codigo=None, conversacion_codigo=None, calificacion=3, comentario=None,
        )


async def test_encuesta_ticket_inexistente(sesion) -> None:
    with pytest.raises(NotFoundError):
        await registrar_encuesta(
            sesion, ticket_codigo="INC-1999-9999", conversacion_codigo=None,
            calificacion=3, comentario=None,
        )


# --- Adjuntos: staging → ticket y purga ---


async def test_adjunto_staging_a_ticket(sesion) -> None:
    staging = await subir_adjunto(sesion, filename="pantallazo.png", content=PNG)
    ruta_staging = Path(staging.ruta_almacenada)
    assert ruta_staging.exists()
    assert "staging" in ruta_staging.parts

    ticket = await _registrar(sesion, adjunto_id=staging.id)

    assert len(ticket.adjuntos) == 1
    adjunto = ticket.adjuntos[0]
    assert adjunto.nombre_original == "pantallazo.png"
    assert adjunto.mime_type == "image/png"
    assert adjunto.tamano_bytes == len(PNG)
    # Archivo movido de staging/ a tickets/
    assert not ruta_staging.exists()
    ruta_final = Path(adjunto.ruta_almacenada)
    assert ruta_final.exists()
    assert "tickets" in ruta_final.parts
    # La fila de staging desapareció
    assert await sesion.get(AdjuntoStaging, staging.id) is None


async def test_adjunto_staging_inexistente(sesion) -> None:
    with pytest.raises(ValidationAppError):
        await _registrar(sesion, adjunto_id="adj_00000000")


async def test_purga_de_huerfanos(sesion, fabrica_sesiones) -> None:
    staging = await subir_adjunto(sesion, filename="viejo.png", content=PNG)
    reciente = await subir_adjunto(sesion, filename="reciente.png", content=PNG)
    ruta_vieja = Path(staging.ruta_almacenada)

    # Envejece el primero más allá de las 24 h
    from sqlalchemy import text

    await sesion.execute(
        text(
            "UPDATE adjuntos_staging "
            "SET created_at = DATE_SUB(NOW(), INTERVAL 25 HOUR) WHERE id = :id"
        ),
        {"id": staging.id},
    )
    await sesion.commit()

    async with fabrica_sesiones() as otra_sesion:
        purgados = await purgar_huerfanos(otra_sesion, max_horas=24)
        assert purgados >= 1
        assert await otra_sesion.get(AdjuntoStaging, staging.id) is None
        assert await otra_sesion.get(AdjuntoStaging, reciente.id) is not None

    assert not ruta_vieja.exists()
    assert Path(reciente.ruta_almacenada).exists()  # el reciente sobrevive
