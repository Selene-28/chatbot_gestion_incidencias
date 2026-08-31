"""Textos oficiales del DRS y del PRD (prd/01 §2-§3, prd/05) — EXACTOS.

Los textos marcados como "oficiales" no deben editarse sin actualizar el DRS.
Los auxiliares (prompts de captura de datos) son propios del servicio.
"""

# --- Textos oficiales del DRS (prd/01 §2) ------------------------------------

BIENVENIDA = (
    "¡Hola! Soy el Asistente Virtual del CTIC. Estoy aquí para ayudarte con "
    "consultas e incidencias relacionadas con los servicios tecnológicos. "
    "¿En qué puedo ayudarte?"
)

AGRADECIMIENTO = (
    "Con gusto. Si necesita ayuda con otra consulta o incidencia, "
    "estaré disponible para asistirlo."
)

DESPEDIDA = "Gracias por utilizar el Asistente Virtual del CTIC. Que tenga un excelente día."

FALLO_1 = (
    "Lo siento, no logré entender tu mensaje. Por favor, selecciona una opción "
    "válida del menú o escribe tu duda en pocas palabras."
)

# El DRS no define el texto literal del Mensaje de Fallo 2 (solo indica
# "Mensaje de Fallo 2 + menú con botones fijos"); este texto es propio.
FALLO_2 = (
    "Sigo sin comprender tu solicitud. Para poder ayudarte, por favor "
    "selecciona una de las siguientes opciones:"
)

FUERA_DE_ALCANCE = (
    "Actualmente solo puedo atender consultas relacionadas con los servicios "
    "tecnológicos del CTIC. Si su consulta corresponde a otra área de la "
    "universidad, le recomiendo comunicarse con la dependencia correspondiente."
)

TRANSICION_HANDOFF = "Te voy a transferir con el personal de CTIC. Un momento, por favor..."

# DRS §Happy Path paso 10-11 (adaptado al código real INC-AAAA-NNNN)
def ticket_registrado(ticket_id: str) -> str:
    """Texto oficial de confirmación de registro (DRS)."""
    return (
        "Su incidencia ha sido registrada correctamente. El número de ticket "
        f"asignado es #{ticket_id}. Puede consultar el estado de su solicitud "
        "cuando lo desee."
    )


ESCALADO_CONFIRMACION = (
    "Su incidencia requiere atención especializada. El caso ha sido escalado "
    "al personal técnico del CTIC. Recibirá una notificación cuando exista "
    "una actualización."
)

ENCUESTA_SOLICITUD = "Antes de finalizar, ¿podría calificar la atención recibida del 1 al 5?"

# QA-03 / prd/05 F-04: limitación de la base de conocimiento
KB_SIN_RESPUESTA = (
    "No tengo información sobre eso en mi base de conocimiento. "
    "¿Deseas registrar una incidencia para que un técnico te ayude?"
)

# --- Menú principal (prd/01 §3, con emojis) -----------------------------------

MENU_TITULO = "¿En qué puedo ayudarte?"

MENU_OPCIONES: list[tuple[str, str]] = [
    ("registrar_incidencia", "📝 Registrar incidencia"),
    ("consultar_estado", "🔍 Consultar estado de mi incidencia"),
    ("faq_general", "❓ Preguntas frecuentes"),
    ("contactar_soporte", "🧑‍💻 Contactar con soporte"),
    ("info_ctic", "ℹ️ Información de la FIIS"),
]

# --- Textos auxiliares (propios del servicio) ---------------------------------

SESION_CERRADA = "La sesión de chat ha finalizado. Por favor, inicia un nuevo chat para continuar."

DISCULPA_TICKETS_CAIDO = (
    "Lo siento, en este momento no puedo comunicarme con el sistema de tickets. "
    "Por favor, inténtalo nuevamente en unos instantes."
)

HANDOFF_INTERINO = (
    "Mientras un agente se conecta, puedo registrar tu incidencia para que el "
    "equipo del CTIC la atienda cuanto antes. ¿Qué deseas hacer?"
)

# F-07: el agente cerró la atención → el bot vuelve (RN-06) y ofrece la encuesta
HANDOFF_REACTIVADO = "He vuelto 🙂 ¿Puedo ayudarte en algo más?"

# F-07: ningún agente atendió en 10 minutos (RN-09) → disculpa + registrar incidencia
HANDOFF_EXPIRADO = (
    "Lamento la demora: en este momento no hay agentes disponibles para atenderte. "
    "Puedo registrar tu incidencia para que el equipo del CTIC la atienda cuanto "
    "antes. ¿Qué deseas hacer?"
)

KB_TE_SIRVIO = "¿Te sirvió esta información?"
