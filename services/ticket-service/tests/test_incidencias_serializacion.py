"""Serialización de API-02: respuesta solo si el ticket está terminado."""

from datetime import datetime
from types import SimpleNamespace

from app.api.incidencias import _observaciones, _ticket_a_dict

AHORA = datetime(2026, 8, 31, 10, 0, 0)


def _ticket(*, estado: str, respuesta: str | None, comentario: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        codigo="INC-2026-0001",
        estado=estado,
        respuesta=respuesta,
        created_at=AHORA,
        updated_at=AHORA,
        categoria=SimpleNamespace(nombre="Correo Institucional"),
        tecnico=SimpleNamespace(nombre="Paul Barzola"),
        historial=[
            SimpleNamespace(comentario=comentario),
        ],
    )


def test_observaciones_abierto_usa_comentario_del_tecnico() -> None:
    ticket = _ticket(
        estado="En Proceso",
        respuesta="No debe verse aún.",
        comentario="En revisión con el área de redes.",
    )
    assert _observaciones(ticket) == "En revisión con el área de redes."
    data = _ticket_a_dict(ticket)
    assert data["respuesta"] is None
    assert data["observaciones"] == "En revisión con el área de redes."
    assert data["tecnico"] == "Paul Barzola"


def test_observaciones_terminado_usa_respuesta() -> None:
    ticket = _ticket(
        estado="Resuelto",
        respuesta="Se restableció el acceso.",
        comentario="Técnico asignado: Paul Barzola.",
    )
    assert _observaciones(ticket) == "Se restableció el acceso."
    data = _ticket_a_dict(ticket)
    assert data["respuesta"] == "Se restableció el acceso."
    assert data["observaciones"] == "Se restableció el acceso."
