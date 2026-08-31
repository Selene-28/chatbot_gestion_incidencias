"""Reglas de validación compartidas entre schemas y capa de servicio (prd/01 §4)."""

import re

DOMINIO_INSTITUCIONAL = "unac.edu.pe"

# Regex de email pragmática (RFC 5322 simplificada)
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PATRON_TICKET = re.compile(r"^INC-\d{4}-\d{4}$")
_HTML_RE = re.compile(r"[<>]")

NOMBRE_MIN, NOMBRE_MAX = 3, 120
DESCRIPCION_MIN, DESCRIPCION_MAX = 10, 2000
COMENTARIO_MAX = 500
RESPUESTA_MAX = 1000
CALIFICACION_MIN, CALIFICACION_MAX = 1, 5

MSG_CORREO_FORMATO = "El correo no tiene un formato válido."
MSG_CORREO_DOMINIO = (
    f"El correo debe pertenecer al dominio institucional @{DOMINIO_INSTITUCIONAL}."
)
MSG_NOMBRE = f"El nombre debe tener entre {NOMBRE_MIN} y {NOMBRE_MAX} caracteres, sin HTML."
MSG_DESCRIPCION = (
    f"La descripción debe tener entre {DESCRIPCION_MIN} y {DESCRIPCION_MAX} caracteres."
)
MSG_CALIFICACION = "La calificación debe ser un número entero entre 1 y 5."
MSG_TICKET_FORMATO = "El número de ticket no tiene el formato INC-AAAA-NNNN."


def normalizar_correo(correo: str) -> str:
    """Normaliza un correo: sin espacios laterales y en minúsculas."""
    return correo.strip().lower()


def es_correo_institucional(correo: str) -> bool:
    """Indica si el correo tiene formato válido y dominio @unac.edu.pe (RF-15)."""
    correo = normalizar_correo(correo)
    return bool(_EMAIL_RE.match(correo)) and correo.endswith(f"@{DOMINIO_INSTITUCIONAL}")


def tiene_formato_correo(correo: str) -> bool:
    """Indica si el texto tiene formato de correo electrónico."""
    return bool(_EMAIL_RE.match(normalizar_correo(correo)))


def contiene_html(texto: str) -> bool:
    """Indica si el texto contiene caracteres de marcado HTML (< o >)."""
    return bool(_HTML_RE.search(texto))


def es_codigo_ticket(codigo: str) -> bool:
    """Indica si el código cumple el formato INC-AAAA-NNNN."""
    return bool(PATRON_TICKET.match(codigo.strip()))
