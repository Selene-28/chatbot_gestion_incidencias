"""Pruebas unitarias de la matriz de transiciones RN-02 (función pura)."""

import pytest

from app.models import ESTADOS_TICKET
from app.services.tickets import ESTADOS_ESCALABLES, TRANSICIONES, es_transicion_valida

# Matriz esperada según RN-02 (prd/01 §5)
MATRIZ_ESPERADA: dict[str, set[str]] = {
    "Registrado": {"Asignado", "Escalado"},
    "Asignado": {"En Proceso", "Escalado"},
    "En Proceso": {"Escalado", "Resuelto"},
    "Escalado": {"En Proceso"},
    "Resuelto": {"Cerrado", "En Proceso"},
    "Cerrado": set(),
}


def test_matriz_cubre_todos_los_estados() -> None:
    assert set(TRANSICIONES) == set(ESTADOS_TICKET)


@pytest.mark.parametrize("desde", sorted(MATRIZ_ESPERADA))
@pytest.mark.parametrize("hacia", sorted(ESTADOS_TICKET))
def test_matriz_completa_rn02(desde: str, hacia: str) -> None:
    """Verifica cada par (desde, hacia) contra la matriz esperada de RN-02."""
    esperado = hacia in MATRIZ_ESPERADA[desde]
    assert es_transicion_valida(desde, hacia) is esperado


def test_estado_desconocido_no_transiciona() -> None:
    assert es_transicion_valida("Inexistente", "Asignado") is False
    assert es_transicion_valida("Registrado", "Inexistente") is False


def test_estados_escalables_api03() -> None:
    """API-03: solo se escala desde Registrado, Asignado o En Proceso."""
    assert frozenset({"Registrado", "Asignado", "En Proceso"}) == ESTADOS_ESCALABLES


def test_cerrado_es_terminal() -> None:
    assert TRANSICIONES["Cerrado"] == frozenset()
