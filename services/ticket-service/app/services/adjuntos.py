"""Servicio de adjuntos (RF-13, API-01b).

Los archivos se validan por FIRMA DE BYTES (no por extensión ni cabecera
Content-Type del cliente) y se guardan fuera del árbol web con nombre
aleatorio en `{UPLOADS_DIR}/staging/`. Un job horario purga los huérfanos.
"""

import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import AdjuntoStaging, TicketAdjunto

logger = logging.getLogger(__name__)

TAMANO_MAXIMO_MB = 15
TAMANO_MAXIMO_BYTES = TAMANO_MAXIMO_MB * 1024 * 1024
MAX_ADJUNTOS_POR_TICKET = 8
PURGA_INTERVALO_S = 3600  # el job corre cada hora
PURGA_MAX_HORAS = 24  # huérfanos con más de 24 h se eliminan

# Firmas de bytes de los formatos permitidos (RF-13: JPG/JPEG, PNG, PDF)
_FIRMAS: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"\x89\x50\x4e\x47", ".png", "image/png"),
    (b"%PDF", ".pdf", "application/pdf"),
)

MSG_TIPO_INVALIDO = "El archivo debe ser JPG, JPEG, PNG o PDF."
MSG_TAMANO_EXCEDIDO = f"El archivo supera el tamaño máximo de {TAMANO_MAXIMO_MB} MB."


def detectar_tipo(contenido: bytes) -> tuple[str, str] | None:
    """Detecta (extensión, mime) por firma de bytes; None si no es un tipo permitido."""
    for firma, extension, mime in _FIRMAS:
        if contenido.startswith(firma):
            return extension, mime
    return None


def validar_archivo(contenido: bytes) -> tuple[str, str]:
    """Valida tamaño ≤ 15 MB y tipo por firma; devuelve (extensión, mime)."""
    if len(contenido) == 0:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[{"field": "file", "description": "El archivo está vacío."}],
        )
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[{"field": "file", "description": MSG_TAMANO_EXCEDIDO}],
        )
    tipo = detectar_tipo(contenido)
    if tipo is None:
        raise ValidationAppError(
            "Los datos enviados son inválidos.",
            errors=[{"field": "file", "description": MSG_TIPO_INVALIDO}],
        )
    return tipo


def _puede_escribir(directorio: Path) -> bool:
    """True si se puede crear el directorio y escribir un archivo de prueba."""
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        sonda = directorio / ".write_test"
        sonda.write_bytes(b"ok")
        sonda.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def resolver_directorio_uploads(*candidatos: Path) -> Path:
    """Primera ruta escribible; en Railway el volumen /data/uploads suele ser root."""
    vistos: list[Path] = []
    for candidato in candidatos:
        if candidato in vistos:
            continue
        vistos.append(candidato)
        if _puede_escribir(candidato):
            return candidato.resolve()
    raise OSError("No hay un directorio escribible para guardar adjuntos.")


_aviso_uploads_emitido = False


def directorio_uploads() -> Path:
    """Carpeta real de adjuntos: UPLOADS_DIR, o $HOME/uploads, o /tmp."""
    global _aviso_uploads_emitido
    configurado = Path(get_settings().UPLOADS_DIR)
    elegido = resolver_directorio_uploads(
        configurado,
        Path(os.environ.get("HOME", "/tmp")) / "uploads",
        Path("/tmp/ctic-uploads"),
    )
    if elegido != configurado.resolve() and not _aviso_uploads_emitido:
        logger.warning(
            "UPLOADS_DIR %s no es escribible; los adjuntos se guardan en %s",
            configurado,
            elegido,
        )
        _aviso_uploads_emitido = True
    return elegido


def generar_adjunto_id() -> str:
    """Genera un token corto tipo adj_XXXXXXXX (12 caracteres, aleatorio)."""
    return f"adj_{secrets.token_hex(4)}"


def nombre_archivo_almacenado(adjunto_id: str, extension: str) -> str:
    """Nombre físico del archivo: id aleatorio + extensión detectada."""
    return f"{adjunto_id}{extension}"


def _raices_uploads_permitidas() -> list[Path]:
    """Raíces válidas: la carpeta en uso y la configurada (por si hay archivos viejos)."""
    raices = [directorio_uploads()]
    configurada = Path(get_settings().UPLOADS_DIR).resolve()
    if configurada not in raices:
        raices.append(configurada)
    return raices


def ruta_adjunto_segura(adjunto: TicketAdjunto) -> Path:
    """Resuelve la ruta física del adjunto; exige que viva bajo UPLOADS_DIR (RF-13)."""
    destino = Path(adjunto.ruta_almacenada).resolve()
    if not any(destino.is_relative_to(raiz) for raiz in _raices_uploads_permitidas()):
        raise ForbiddenError("La ruta del adjunto no es válida.")
    if not destino.is_file():
        raise NotFoundError("El archivo adjunto ya no está disponible.")
    return destino


def sanear_nombre_original(nombre: str | None) -> str:
    """Reduce el nombre del cliente a su base (sin rutas) y lo acota a 255."""
    base = Path(nombre or "").name.strip()
    return (base or "adjunto")[:255]


async def subir_adjunto(
    session: AsyncSession, *, filename: str, content: bytes
) -> AdjuntoStaging:
    """Valida y guarda un adjunto en staging; devuelve la fila creada (API-01b)."""
    extension, mime = validar_archivo(content)

    adjunto_id = generar_adjunto_id()
    for _ in range(5):  # colisión de token improbable; se reintenta por robustez
        if await session.get(AdjuntoStaging, adjunto_id) is None:
            break
        adjunto_id = generar_adjunto_id()

    staging_dir = directorio_uploads() / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    ruta = staging_dir / nombre_archivo_almacenado(adjunto_id, extension)
    ruta.write_bytes(content)

    fila = AdjuntoStaging(
        id=adjunto_id,
        nombre_original=sanear_nombre_original(filename),
        ruta_almacenada=str(ruta),
        mime_type=mime,
        tamano_bytes=len(content),
    )
    session.add(fila)
    try:
        await session.commit()
    except Exception:
        ruta.unlink(missing_ok=True)  # no dejar archivos sin fila asociada
        raise
    await session.refresh(fila)
    return fila


async def purgar_huerfanos(session: AsyncSession, max_horas: int = PURGA_MAX_HORAS) -> int:
    """Elimina adjuntos de staging (filas y archivos) con más de max_horas."""
    limite = datetime.now() - timedelta(hours=max_horas)
    huerfanos = (
        (await session.execute(select(AdjuntoStaging).where(AdjuntoStaging.created_at < limite)))
        .scalars()
        .all()
    )
    for fila in huerfanos:
        Path(fila.ruta_almacenada).unlink(missing_ok=True)
        await session.delete(fila)
    await session.commit()
    if huerfanos:
        logger.info("Purga de adjuntos huérfanos: %d eliminados", len(huerfanos))
    return len(huerfanos)


async def loop_purga() -> None:
    """Tarea periódica: purga adjuntos huérfanos cada hora (se registra en el lifespan)."""
    while True:
        try:
            async with get_sessionmaker()() as session:
                await purgar_huerfanos(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fallo en la purga periódica de adjuntos huérfanos")
        await asyncio.sleep(PURGA_INTERVALO_S)
