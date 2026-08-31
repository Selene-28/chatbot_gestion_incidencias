"""Pruebas unitarias de los schemas Pydantic (validaciones de prd/01 §4)."""

import pytest
from pydantic import ValidationError

from app.schemas.encuestas import EncuestaCreate
from app.schemas.incidencias import EscalarRequest, IncidenciaCreate

INCIDENCIA_VALIDA = {
    "nombre": "Juan Pérez",
    "correo": "jperez@unac.edu.pe",
    "area": "Industrial",
    "categoria": "Correo Institucional",
    "subcategoria": "Recuperación de contraseña",
    "descripcion": "No puedo acceder a mi correo institucional.",
    "prioridad": "Media",
    "origen": "chatbot",
    "conversacionCodigo": "3f2a0000-0000-0000-0000-000000000000",
    "adjuntoId": "adj_9f31ab00",
}


def _mensajes(excinfo: pytest.ExceptionInfo[ValidationError]) -> str:
    return " ".join(str(e["msg"]) for e in excinfo.value.errors())


# --- IncidenciaCreate (API-01) ---


def test_incidencia_valida_con_alias() -> None:
    payload = IncidenciaCreate.model_validate(INCIDENCIA_VALIDA)
    assert payload.correo == "jperez@unac.edu.pe"
    assert payload.conversacion_codigo == INCIDENCIA_VALIDA["conversacionCodigo"]
    assert payload.adjunto_id == "adj_9f31ab00"


def test_incidencia_defaults() -> None:
    datos = {k: v for k, v in INCIDENCIA_VALIDA.items() if k not in
             ("prioridad", "origen", "conversacionCodigo", "adjuntoId", "subcategoria")}
    payload = IncidenciaCreate.model_validate(datos)
    assert payload.prioridad == "Media"
    assert payload.origen == "chatbot"
    assert payload.subcategoria is None


def test_correo_normalizado_a_minusculas() -> None:
    payload = IncidenciaCreate.model_validate(
        {**INCIDENCIA_VALIDA, "correo": "  JPEREZ@UNAC.EDU.PE  "}
    )
    assert payload.correo == "jperez@unac.edu.pe"


@pytest.mark.parametrize("nombre", ["ab", "x" * 121, "<script>alert(1)</script>"])
def test_nombre_invalido(nombre: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        IncidenciaCreate.model_validate({**INCIDENCIA_VALIDA, "nombre": nombre})
    assert "nombre" in _mensajes(excinfo).lower()


@pytest.mark.parametrize(
    "correo", ["jperez@gmail.com", "no-es-correo", "jperez@unac.edu.pe.evil.com", ""]
)
def test_correo_invalido_o_no_institucional(correo: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        IncidenciaCreate.model_validate({**INCIDENCIA_VALIDA, "correo": correo})
    assert "correo" in _mensajes(excinfo).lower()


def test_area_invalida() -> None:
    with pytest.raises(ValidationError) as excinfo:
        IncidenciaCreate.model_validate({**INCIDENCIA_VALIDA, "area": "Externo"})
    assert "área" in _mensajes(excinfo)


@pytest.mark.parametrize("descripcion", ["corta", "x" * 2001])
def test_descripcion_fuera_de_rango(descripcion: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        IncidenciaCreate.model_validate({**INCIDENCIA_VALIDA, "descripcion": descripcion})
    assert "descripción" in _mensajes(excinfo)


def test_prioridad_invalida() -> None:
    with pytest.raises(ValidationError) as excinfo:
        IncidenciaCreate.model_validate({**INCIDENCIA_VALIDA, "prioridad": "Urgente"})
    assert "prioridad" in _mensajes(excinfo).lower()


def test_mensajes_de_error_en_espanol() -> None:
    with pytest.raises(ValidationError) as excinfo:
        IncidenciaCreate.model_validate({**INCIDENCIA_VALIDA, "correo": "a@gmail.com"})
    assert "dominio institucional" in _mensajes(excinfo)


# --- EscalarRequest (API-03) ---


def test_escalar_valido() -> None:
    payload = EscalarRequest.model_validate(
        {"ticketId": "INC-2026-0001", "motivo": "No se resolvió.", "correo": "a@unac.edu.pe"}
    )
    assert payload.ticket_id == "INC-2026-0001"


@pytest.mark.parametrize("ticket", ["INC-26-1", "TIC-2026-0001", "INC-2026-1", ""])
def test_escalar_ticket_formato_invalido(ticket: str) -> None:
    with pytest.raises(ValidationError):
        EscalarRequest.model_validate(
            {"ticketId": ticket, "motivo": "Motivo válido.", "correo": "a@unac.edu.pe"}
        )


def test_escalar_motivo_vacio() -> None:
    with pytest.raises(ValidationError):
        EscalarRequest.model_validate(
            {"ticketId": "INC-2026-0001", "motivo": "", "correo": "a@unac.edu.pe"}
        )


# --- EncuestaCreate (API-06, RN-04) ---


def test_encuesta_valida_con_ticket() -> None:
    payload = EncuestaCreate.model_validate({"ticketId": "INC-2026-0001", "calificacion": 5})
    assert payload.ticket_id == "INC-2026-0001"
    assert payload.conversacion_codigo is None


def test_encuesta_valida_con_conversacion() -> None:
    payload = EncuestaCreate.model_validate(
        {"conversacionCodigo": "abc-123", "calificacion": 1, "comentario": "Bien."}
    )
    assert payload.conversacion_codigo == "abc-123"


@pytest.mark.parametrize("calificacion", [0, 6, -1, 100])
def test_encuesta_calificacion_fuera_de_rango(calificacion: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        EncuestaCreate.model_validate({"ticketId": "INC-2026-0001", "calificacion": calificacion})
    assert "entre 1 y 5" in _mensajes(excinfo)


def test_encuesta_sin_referencia() -> None:
    with pytest.raises(ValidationError) as excinfo:
        EncuestaCreate.model_validate({"calificacion": 3})
    assert "ticket o la conversación" in _mensajes(excinfo)


def test_encuesta_comentario_demasiado_largo() -> None:
    with pytest.raises(ValidationError):
        EncuestaCreate.model_validate(
            {"ticketId": "INC-2026-0001", "calificacion": 3, "comentario": "x" * 501}
        )
