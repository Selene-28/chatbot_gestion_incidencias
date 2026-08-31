"""Validaciones por campo/paso (prd/01 §4)."""

from app.dialogo import validaciones as v


def test_correo_institucional_valido() -> None:
    assert v.validar_correo("  JPerez@UNAC.edu.pe ") == "jperez@unac.edu.pe"


def test_correo_dominio_ajeno_rechazado() -> None:
    assert v.validar_correo("jperez@gmail.com") is None


def test_correo_formato_invalido() -> None:
    assert v.validar_correo("no-es-un-correo") is None
    assert v.validar_correo("a@b@unac.edu.pe") is None


def test_nombre_valido_y_limites() -> None:
    assert v.validar_nombre("Ana Li") == "Ana Li"
    assert v.validar_nombre("ab") is None
    assert v.validar_nombre("x" * 121) is None


def test_nombre_sin_html() -> None:
    assert v.validar_nombre("<script>alert(1)</script>") is None


def test_descripcion_limites() -> None:
    assert v.validar_descripcion("no imprime nada") == "no imprime nada"
    assert v.validar_descripcion("corta") is None
    assert v.validar_descripcion("x" * 2001) is None
    assert v.validar_descripcion("x" * 2000) is not None


def test_motivo_limites() -> None:
    assert v.validar_motivo("sigue sin resolverse") is not None
    assert v.validar_motivo("corto") is None
    assert v.validar_motivo("x" * 501) is None


def test_extraer_ticket() -> None:
    assert v.extraer_ticket("mi ticket es INC-2026-0001, gracias") == "INC-2026-0001"
    assert v.extraer_ticket("inc-2026-0002") == "INC-2026-0002"
    assert v.extraer_ticket("INC-26-01") is None
    assert v.extraer_ticket("sin código") is None


def test_calificacion() -> None:
    assert v.validar_calificacion("5") == 5
    assert v.validar_calificacion(" 1 ") == 1
    assert v.validar_calificacion("0") is None
    assert v.validar_calificacion("6") is None
    assert v.validar_calificacion("cinco") is None


def test_elegir_de_lista_normalizada() -> None:
    assert v.elegir_de_lista("MEDIA", v.PRIORIDADES) == "Media"
    assert v.elegir_de_lista("sga", v.CATEGORIAS) == "SGA"
    assert v.elegir_de_lista("equipos tecnologicos", v.CATEGORIAS) == "Equipos Tecnológicos"
    assert v.elegir_de_lista("otra cosa", v.PRIORIDADES) is None


def test_normalizar() -> None:
    assert v.normalizar("  ¿CÓMO   estás? ") == "¿como estas?"
