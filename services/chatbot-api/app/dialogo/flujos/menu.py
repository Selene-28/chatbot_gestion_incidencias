"""Menú principal y respuestas sociales fijas (prd/01 §2-§3).

No es una máquina de estados: son mensajes sin estado que se muestran tras el
saludo y tras cada atención completada.
"""

from app.dialogo import textos
from app.dialogo.tipos import MensajeBot, con_opciones, texto_plano


def menu_principal(titulo: str = textos.MENU_TITULO) -> MensajeBot:
    """Menú principal con los 5 botones oficiales (prd/01 §3)."""
    return con_opciones(titulo, textos.MENU_OPCIONES)


def bienvenida_con_menu() -> list[MensajeBot]:
    """Respuesta al intent `saludo`: bienvenida oficial + menú."""
    return [texto_plano(textos.BIENVENIDA), menu_principal()]


def agradecimiento() -> list[MensajeBot]:
    """Respuesta fija al intent `agradecimiento`."""
    return [texto_plano(textos.AGRADECIMIENTO)]


def despedida() -> list[MensajeBot]:
    """Respuesta fija al intent `despedida`."""
    return [texto_plano(textos.DESPEDIDA)]


def fuera_de_alcance() -> list[MensajeBot]:
    """Respuesta fija al intent `fuera_de_alcance` (LF-01) + menú."""
    return [texto_plano(textos.FUERA_DE_ALCANCE), menu_principal()]
