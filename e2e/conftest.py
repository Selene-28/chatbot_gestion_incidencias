"""Fixtures compartidas y resumen de la Definición de Terminado.

- Clientes httpx async contra ``E2E_BASE_URL`` (widget, admin, técnico).
- Hook que agrega el resultado por criterio y, al final de la corrida, imprime
  ``QA-01..QA-11: X/11 verdes`` (el GATE de release del proyecto).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

import helpers

# --- Clientes HTTP -------------------------------------------------------------


@pytest_asyncio.fixture
async def cliente() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente del widget (sin autenticación de staff), contra nginx."""
    async with httpx.AsyncClient(base_url=helpers.BASE_URL, timeout=30.0) as c:
        yield c


@pytest_asyncio.fixture
async def cliente_admin() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente autenticado como admin (cookie ``panel_token`` en el cliente)."""
    async with httpx.AsyncClient(base_url=helpers.BASE_URL, timeout=30.0) as c:
        await helpers.login_staff(c, helpers.STAFF_ADMIN)
        yield c


@pytest_asyncio.fixture
async def cliente_tecnico() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente autenticado como técnico (rol no-admin)."""
    async with httpx.AsyncClient(base_url=helpers.BASE_URL, timeout=30.0) as c:
        await helpers.login_staff(c, helpers.STAFF_TECNICO)
        yield c


# --- Agregación de resultados por QA (Definición de Terminado) -----------------

# qa -> True si todos sus tests pasaron, False si alguno falló.
_resultado_qa: dict[str, bool] = {}
# Mediciones que los tests quieran publicar en el resumen (p. ej. QA-09).
mediciones: dict[str, str] = {}


def _qa_de(report: pytest.TestReport) -> str | None:
    for palabra in report.keywords:
        if len(palabra) == 4 and palabra.startswith("qa") and palabra[2:].isdigit():
            return palabra
    return None


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Agrega el resultado por QA.

    Un QA es ROJO solo si alguna de sus fases FALLA. Los ``skip`` y ``xfail``
    (fallos conocidos y documentados) no lo enrojecen: dejan constancia sin
    bloquear el gate. Un ``xpass`` estricto sí falla, para forzar la revisión
    del test cuando el backend corrija el defecto conocido.
    """
    qa = _qa_de(report)
    if qa is None:
        return
    if report.failed:
        _resultado_qa[qa] = False
    else:
        _resultado_qa.setdefault(qa, True)


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:  # noqa: ANN001
    """Imprime el resumen final: estado por QA y ``X/11 verdes``."""
    tr = terminalreporter
    tr.write_sep("=", "RESUMEN QA — Definición de Terminado (DRS §6)")
    if mediciones:
        for clave, valor in mediciones.items():
            tr.write_line(f"  {clave}: {valor}")
        tr.write_sep("-", "")
    verdes = 0
    for n in range(1, 12):
        qa = f"qa{n:02d}"
        estado = _resultado_qa.get(qa)
        if estado is True:
            marca, color = "VERDE", {"green": True}
            verdes += 1
        elif estado is False:
            marca, color = "ROJO ", {"red": True}
        else:
            marca, color = "s/e  ", {"yellow": True}  # sin ejecutar
        tr.write_line(f"  QA-{n:02d}: {marca}", **color)
    tr.write_sep("-", "")
    tr.write_line(f"  QA-01..QA-11: {verdes}/11 verdes", bold=True)
