"""Router de intenciones — CAPA 1 (reglas), prd/06 §2 y flujo F-01.

Estrategia:
- `opcionId` de botón → intent directo (sin NLP), vía `INTENTS_DE_MENU`.
- Texto libre: regex/keywords sobre el texto normalizado (minúsculas, sin
  tildes). Las intenciones sociales se detectan con patrones anclados para no
  robarle mensajes con contenido ("hola, no puedo entrar al aula virtual").
- Sin match → `no_comprendida`. La Capa 2 (clasificador LLM asíncrono,
  `app.dialogo.clasificador`) la invoca el orquestador (manager) solo cuando
  esta capa no decide; el parámetro `clasificador_llm` queda como punto de
  extensión sincrónico adicional (útil en pruebas).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.dialogo.validaciones import PATRON_TICKET, normalizar

UMBRAL_CONFIANZA = 0.55  # prd/06 §2: por debajo se trata como no_comprendida


@dataclass(frozen=True)
class IntentDetectado:
    """Resultado del router: intención + confianza [0,1] + vía (regla|llm)."""

    intent: str
    confianza: float
    via: str = "regla"


# opcionId del menú principal → intent directo
INTENTS_DE_MENU: frozenset[str] = frozenset(
    {
        "registrar_incidencia",
        "consultar_estado",
        "faq_general",
        "contactar_soporte",
        "info_ctic",
    }
)

# --- Patrones sociales (anclados: el mensaje ES el saludo/despedida/etc.) -----

_SALUDO_RE = re.compile(
    r"^\W*(hola+|buenos dias|buenas tardes|buenas noches|buen dia|buenas|saludos|hey|alo)"
    r"[\s,.!¡¿?]*$"
)
_DESPEDIDA_RE = re.compile(
    r"^\W*(adios|chau+|chao|hasta luego|hasta pronto|nos vemos|me despido|me retiro|bye)"
    r"[\s,.!¡¿?]*$"
)
_AGRADECIMIENTO_RE = re.compile(
    r"^\W*(muchas |muchisimas |mil )?(gracias|te agradezco|se agradece|muy amable)"
    r"[\s,.!¡¿?a-z]{0,25}$"
)
_FINALIZAR_RE = re.compile(
    r"\b(finalizar|terminar|cerrar (el )?chat|eso es todo|seria todo|ya no necesito( nada)? mas)\b"
)

# --- Patrones por intención (orden = prioridad) --------------------------------

_ESCALAR_RE = re.compile(r"\b(escalar|escalen|escalamiento|derivar|deriven)\b")

_CONSULTAR_RE = re.compile(
    r"(\bestado\b.*\b(ticket|incidencia|caso|solicitud)\b)"
    r"|(\b(ticket|incidencia|caso|solicitud)\b.*\bestado\b)"
    r"|(\bcomo va mi\b)|(\bseguimiento\b)|(\bconsultar (mi )?(ticket|incidencia)\b)"
)

_REGISTRAR_RE = re.compile(
    r"\b(registrar|registra|reportar|reporta|crear|abrir|levantar|generar)\b"
    r".{0,30}\b(incidencia|ticket|problema|reporte|caso)\b"
    r"|\b(nueva incidencia|nuevo ticket|quiero reportar|deseo reportar)\b"
)

_SOPORTE_RE = re.compile(
    r"\b(hablar|comunicar|contactar|conversar|chatear|atienda)\b"
    r".{0,30}\b(persona|humano|agente|alguien|soporte|tecnico|asesor)\b"
    r"|\b(contactar (con )?soporte|atencion humana|un humano|un agente|soporte tecnico)\b"
)

_INFO_CTIC_RE = re.compile(
    r"\b(horario|ubicacion|direccion|telefono|anexo)\b"
    r"|\bdonde (esta|queda|se encuentra|atiende)\b"
    r"|\b(informacion|contacto) (de |del )?ctic\b"
    r"|\bque es el ctic\b"
)

# --- Problemas obvios → diagnóstico F-05 / recuperar_correo (capa 1) -----------

_SINTOMA = (
    r"(no puedo|no me deja|no logro|no carga|no funciona|no anda|no abre|no entra|"
    r"no veo|no aparece|no me llega|no recibo|error|falla|fallo|caido|caida|lento|"
    r"lenta|intermitente|bloquead[oa]|se cae|se cierra|se cuelga|problema)"
)

_PROBLEMA_INTERNET_RE = re.compile(
    r"(\b(sin|no tengo|no hay|no funciona|no anda|se cayo|se corta|se cae)\b"
    r".{0,25}\b(internet|wifi|red|senal|conexion)\b)"
    r"|(\b(internet|wifi|red|conexion)\b.{0,40}" + _SINTOMA + r")"
    r"|(\bno (me )?puedo conectar\b.{0,25}\b(internet|wifi|red)\b)"
    r"|(\bproblemas? (con|de|en)\b.{0,20}\b(internet|wifi|red|conexion)\b)"
)

_PROBLEMA_AULA_RE = re.compile(
    r"(" + _SINTOMA + r".{0,50}\b(aula virtual|moodle|campus virtual)\b)"
    r"|(\b(aula virtual|moodle|campus virtual)\b.{0,50}" + _SINTOMA + r")"
    r"|(\bproblemas? (con|de|en)\b.{0,20}\b(aula virtual|moodle|campus virtual)\b)"
)

_SISTEMAS_SOFTWARE = r"(sga|turnitin|office|word|excel|power ?point|teams|zoom|software)"

_PROBLEMA_SOFTWARE_RE = re.compile(
    r"(" + _SINTOMA + r".{0,50}\b" + _SISTEMAS_SOFTWARE + r"\b)"
    r"|(\b" + _SISTEMAS_SOFTWARE + r"\b.{0,50}" + _SINTOMA + r")"
    r"|(\bproblemas? (con|de|en)\b.{0,20}\b" + _SISTEMAS_SOFTWARE + r"\b)"
)

# prd/06 §2: "contraseña" + "correo" → recuperar_correo
_RECUPERAR_CORREO_RE = re.compile(
    r"(?=.*\b(contrasena|password|clave|recuperar|restablecer|olvide|olvidado)\b)"
    r"(?=.*\b(correo|email|mail)\b)"
)

_FAQ_KEYWORDS = (
    "como ",
    "cómo",  # por si la normalización cambia
    "no puedo",
    "no me deja",
    "no me llega",
    "no funciona",
    "no tengo acceso",
    "problema",
    "falla",
    "error",
    "contrasena",
    "password",
    "clave",
    "wifi",
    "internet",
    "red ",
    "aula virtual",
    "moodle",
    "correo",
    "email",
    "olvide",
    "recuperar",
    "restablecer",
    "instalar",
    "acceso",
    "cuenta",
    "bloqueado",
    "bloqueada",
    "lento",
    "ayuda",
)

ClasificadorLLM = Callable[[str], IntentDetectado | None]


def detectar(texto: str, clasificador_llm: ClasificadorLLM | None = None) -> IntentDetectado:
    """Clasifica un texto libre en una de las intenciones de prd/01 §2."""
    t = normalizar(texto)
    if not t:
        return IntentDetectado("no_comprendida", 0.0)

    # Sociales (anclados) y cierre
    if _SALUDO_RE.match(t):
        return IntentDetectado("saludo", 0.98)
    if _DESPEDIDA_RE.match(t):
        return IntentDetectado("despedida", 0.98)
    if _AGRADECIMIENTO_RE.match(t):
        return IntentDetectado("agradecimiento", 0.95)
    if _FINALIZAR_RE.search(t):
        return IntentDetectado("finalizar", 0.9)

    if _ESCALAR_RE.search(t):
        return IntentDetectado("escalar_incidencia", 0.9)

    # Código de ticket presente → consulta directa (prd/06 §2)
    if PATRON_TICKET.search(texto):
        return IntentDetectado("consultar_estado", 0.99)
    if _CONSULTAR_RE.search(t):
        return IntentDetectado("consultar_estado", 0.9)
    if _REGISTRAR_RE.search(t):
        return IntentDetectado("registrar_incidencia", 0.9)
    if _SOPORTE_RE.search(t):
        return IntentDetectado("contactar_soporte", 0.9)
    if _INFO_CTIC_RE.search(t):
        return IntentDetectado("info_ctic", 0.85)

    # Problemas obvios → diagnóstico guiado F-05 (antes que el FAQ genérico)
    if _PROBLEMA_INTERNET_RE.search(t):
        return IntentDetectado("problema_internet", 0.85)
    if _PROBLEMA_AULA_RE.search(t):
        return IntentDetectado("problema_aula_virtual", 0.85)
    if _PROBLEMA_SOFTWARE_RE.search(t):
        return IntentDetectado("problema_software", 0.85)
    if _RECUPERAR_CORREO_RE.search(t):
        return IntentDetectado("recuperar_correo", 0.85)

    if any(kw in t for kw in _FAQ_KEYWORDS):
        return IntentDetectado("faq_general", 0.75)

    # Punto de extensión sincrónico (la capa 2 real la orquesta el manager)
    if clasificador_llm is not None:
        resultado = clasificador_llm(texto)
        if resultado is not None and resultado.confianza >= UMBRAL_CONFIANZA:
            return resultado

    return IntentDetectado("no_comprendida", 0.0)
