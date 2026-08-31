"""Flujos conversacionales (máquinas de estado de prd/05)."""

from app.dialogo.engine import Engine
from app.dialogo.flujos.consultar import FlujoConsultar
from app.dialogo.flujos.diagnostico import FlujoDiagnostico
from app.dialogo.flujos.encuesta import FlujoEncuesta
from app.dialogo.flujos.escalar import FlujoEscalar
from app.dialogo.flujos.faq import FlujoFaq
from app.dialogo.flujos.registrar import FlujoRegistrar


def crear_engine() -> Engine:
    """Motor con todos los flujos del núcleo conversacional registrados."""
    return Engine(
        [
            FlujoRegistrar(),
            FlujoConsultar(),
            FlujoEscalar(),
            FlujoEncuesta(),
            FlujoFaq(),
            FlujoDiagnostico(),
        ]
    )
