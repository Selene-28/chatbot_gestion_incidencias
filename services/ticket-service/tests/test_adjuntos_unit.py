"""Pruebas unitarias del servicio de adjuntos: firmas de bytes y nombres (RF-13)."""

import re

import pytest

from app.core.errors import ValidationAppError
from app.services.adjuntos import (
    TAMANO_MAXIMO_BYTES,
    detectar_tipo,
    generar_adjunto_id,
    nombre_archivo_almacenado,
    sanear_nombre_original,
    validar_archivo,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"\x00" * 16


# --- Detección por firma de bytes (no por extensión) ---


@pytest.mark.parametrize(
    ("contenido", "extension", "mime"),
    [
        (JPEG, ".jpg", "image/jpeg"),
        (PNG, ".png", "image/png"),
        (PDF, ".pdf", "application/pdf"),
    ],
)
def test_detectar_tipo_por_firma(contenido: bytes, extension: str, mime: str) -> None:
    assert detectar_tipo(contenido) == (extension, mime)


@pytest.mark.parametrize(
    "contenido",
    [b"texto plano cualquiera", b"GIF89a...", b"<html></html>", b"", b"\x00\x01\x02"],
)
def test_detectar_tipo_rechaza_otros_formatos(contenido: bytes) -> None:
    assert detectar_tipo(contenido) is None


def test_validar_archivo_ok() -> None:
    assert validar_archivo(PNG) == (".png", "image/png")


def test_validar_archivo_rechaza_tipo_no_permitido() -> None:
    with pytest.raises(ValidationAppError) as excinfo:
        validar_archivo(b"MZ\x90\x00 ejecutable")
    assert any("JPG" in e.description for e in excinfo.value.errors)


def test_validar_archivo_rechaza_extension_enganosa() -> None:
    """La validación es por contenido: un .png con bytes de texto se rechaza."""
    with pytest.raises(ValidationAppError):
        validar_archivo(b"no soy un png de verdad")


def test_validar_archivo_rechaza_mayor_a_5mb() -> None:
    grande = b"\xff\xd8\xff" + b"\x00" * TAMANO_MAXIMO_BYTES  # 5 MB + 3 bytes
    with pytest.raises(ValidationAppError) as excinfo:
        validar_archivo(grande)
    assert any("5 MB" in e.description for e in excinfo.value.errors)


def test_validar_archivo_acepta_exactamente_5mb() -> None:
    exacto = b"\xff\xd8\xff" + b"\x00" * (TAMANO_MAXIMO_BYTES - 3)
    assert validar_archivo(exacto) == (".jpg", "image/jpeg")


def test_validar_archivo_rechaza_vacio() -> None:
    with pytest.raises(ValidationAppError):
        validar_archivo(b"")


# --- Generación de identificadores y nombres de archivo ---


def test_generar_adjunto_id_formato() -> None:
    adjunto_id = generar_adjunto_id()
    assert re.fullmatch(r"adj_[0-9a-f]{8}", adjunto_id)
    assert len(adjunto_id) == 12  # CHAR(12) en adjuntos_staging


def test_generar_adjunto_id_aleatorio() -> None:
    ids = {generar_adjunto_id() for _ in range(50)}
    assert len(ids) == 50


def test_nombre_archivo_almacenado() -> None:
    assert nombre_archivo_almacenado("adj_9f31ab00", ".png") == "adj_9f31ab00.png"


def test_sanear_nombre_original_quita_rutas() -> None:
    assert sanear_nombre_original("../../etc/passwd") == "passwd"
    assert sanear_nombre_original("carpeta/foto.png") == "foto.png"
    assert sanear_nombre_original(None) == "adjunto"
    assert sanear_nombre_original("   ") == "adjunto"
    assert len(sanear_nombre_original("a" * 300 + ".png")) <= 255
