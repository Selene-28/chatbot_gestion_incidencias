"""Validaciones de campos capturados por los flujos (prd/01 §4)."""

import re
import unicodedata

DOMINIO_INSTITUCIONAL = "unac.edu.pe"

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_HTML_RE = re.compile(r"[<>]")
PATRON_TICKET = re.compile(r"\bINC-\d{4}-\d{4}\b", re.IGNORECASE)

NOMBRE_MIN, NOMBRE_MAX = 3, 120
DESCRIPCION_MIN, DESCRIPCION_MAX = 10, 2000
MOTIVO_MIN, MOTIVO_MAX = 10, 500
COMENTARIO_MAX = 500
CODIGO_INSTITUCIONAL_DIGITOS = 10

ESCUELAS: tuple[str, ...] = ("Industrial", "Sistemas")
PRIORIDADES: tuple[str, ...] = ("Baja", "Media", "Alta")
PRIORIDAD_DEFAULT = "Media"

# Categorías seed del ticket-service (alembic 0002 + 0004).
# TODO(Semana 5): obtenerlas de un endpoint de categorías del ticket-service
# en lugar de esta lista fija.
CATEGORIAS: tuple[str, ...] = (
    "Correo Institucional",
    "Problemas con la página web de la facultad",
    "Internet/WiFi",
    "SGA",
    "Equipos Tecnológicos",
    "Laboratorios",
    "Solicitudes Tecnológicas",
    "Otros",
)


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (matching por reglas)."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def validar_correo(texto: str) -> str | None:
    """Correo institucional válido (@unac.edu.pe) normalizado, o None."""
    correo = texto.strip().lower()
    if _EMAIL_RE.match(correo) and correo.endswith(f"@{DOMINIO_INSTITUCIONAL}"):
        return correo
    return None


def validar_nombre(texto: str) -> str | None:
    """Nombre de 3–120 caracteres sin HTML, o None."""
    nombre = texto.strip()
    if NOMBRE_MIN <= len(nombre) <= NOMBRE_MAX and not _HTML_RE.search(nombre):
        return nombre
    return None


def validar_codigo_institucional(texto: str) -> str | None:
    """Código institucional del alumno: exactamente 10 dígitos numéricos, o None."""
    codigo = texto.strip()
    if codigo.isdigit() and len(codigo) == CODIGO_INSTITUCIONAL_DIGITOS:
        return codigo
    return None


def validar_descripcion(texto: str) -> str | None:
    """Descripción de 10–2000 caracteres, o None."""
    descripcion = texto.strip()
    if DESCRIPCION_MIN <= len(descripcion) <= DESCRIPCION_MAX:
        return descripcion
    return None


def validar_motivo(texto: str) -> str | None:
    """Motivo de escalamiento de 10–500 caracteres, o None."""
    motivo = texto.strip()
    if MOTIVO_MIN <= len(motivo) <= MOTIVO_MAX:
        return motivo
    return None


def extraer_ticket(texto: str) -> str | None:
    """Primer código INC-AAAA-NNNN presente en el texto, o None."""
    match = PATRON_TICKET.search(texto)
    return match.group(0).upper() if match else None


def validar_calificacion(valor: str) -> int | None:
    """Calificación entera 1–5, o None."""
    valor = valor.strip().rstrip("⭐").strip()
    if valor.isdigit() and 1 <= int(valor) <= 5:
        return int(valor)
    return None


def elegir_de_lista(texto: str, opciones: tuple[str, ...]) -> str | None:
    """Empareja texto libre contra una lista fija (normalizado), o None."""
    entrada = normalizar(texto)
    for opcion in opciones:
        if normalizar(opcion) == entrada:
            return opcion
    return None
