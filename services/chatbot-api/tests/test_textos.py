"""Textos oficiales del DRS — deben ser EXACTOS (prd/01 §2, prd/05)."""

from app.dialogo import textos


def test_bienvenida_oficial() -> None:
    assert textos.BIENVENIDA == (
        "¡Hola! Soy el Asistente Virtual del CTIC. Estoy aquí para ayudarte con "
        "consultas e incidencias relacionadas con los servicios tecnológicos. "
        "¿En qué puedo ayudarte?"
    )


def test_agradecimiento_oficial() -> None:
    assert textos.AGRADECIMIENTO == (
        "Con gusto. Si necesita ayuda con otra consulta o incidencia, "
        "estaré disponible para asistirlo."
    )


def test_despedida_oficial() -> None:
    assert textos.DESPEDIDA == (
        "Gracias por utilizar el Asistente Virtual del CTIC. Que tenga un excelente día."
    )


def test_fallo_1_oficial() -> None:
    assert textos.FALLO_1 == (
        "Lo siento, no logré entender tu mensaje. Por favor, selecciona una opción "
        "válida del menú o escribe tu duda en pocas palabras."
    )


def test_fuera_de_alcance_oficial() -> None:
    assert textos.FUERA_DE_ALCANCE == (
        "Actualmente solo puedo atender consultas relacionadas con los servicios "
        "tecnológicos del CTIC. Si su consulta corresponde a otra área de la "
        "universidad, le recomiendo comunicarse con la dependencia correspondiente."
    )


def test_transicion_handoff_oficial() -> None:
    assert textos.TRANSICION_HANDOFF == (
        "Te voy a transferir con el personal de CTIC. Un momento, por favor..."
    )


def test_ticket_registrado_oficial() -> None:
    assert textos.ticket_registrado("INC-2026-0001") == (
        "Su incidencia ha sido registrada correctamente. El número de ticket "
        "asignado es #INC-2026-0001. Puede consultar el estado de su solicitud "
        "cuando lo desee."
    )


def test_escalado_oficial() -> None:
    assert textos.ESCALADO_CONFIRMACION == (
        "Su incidencia requiere atención especializada. El caso ha sido escalado "
        "al personal técnico del CTIC. Recibirá una notificación cuando exista "
        "una actualización."
    )


def test_encuesta_oficial() -> None:
    assert textos.ENCUESTA_SOLICITUD == (
        "Antes de finalizar, ¿podría calificar la atención recibida del 1 al 5?"
    )


def test_menu_oficial_con_emojis() -> None:
    assert textos.MENU_OPCIONES == [
        ("registrar_incidencia", "📝 Registrar incidencia"),
        ("consultar_estado", "🔍 Consultar estado de mi incidencia"),
        ("faq_general", "❓ Preguntas frecuentes"),
        ("contactar_soporte", "🧑‍💻 Contactar con soporte"),
        ("info_ctic", "ℹ️ Información de la FIIS"),
    ]
