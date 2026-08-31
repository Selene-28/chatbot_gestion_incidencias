"""QA-09 · Rendimiento (DRS §6, REN-01).

Criterio: respuesta promedio ≤ 3 s; registro sin pérdida de información.

Se mide el tiempo de respuesta de N mensajes de chat variados. Se usan mensajes
resueltos por FLUJO/reglas (no dependen del LLM), de modo que la medición es
representativa del camino de autoservicio. Se reporta el promedio y el p95.
El ritmo se pacea para no toparse con el rate-limit de nginx; se mide el tiempo
de respuesta real del servidor (``response.elapsed``), sin contar las pausas.
"""

import asyncio

import pytest

import conftest
import helpers

pytestmark = pytest.mark.qa09

N_MENSAJES = 20
UMBRAL_PROMEDIO_S = 3.0  # REN-01

# Mensajes variados, todos resolubles por reglas/flujo (sin LLM) y sin dejar un
# flujo activo colgado en la conversación.
_MENSAJES = [
    "hola",
    "¿cómo recupero mi contraseña del correo?",
    "cuál es el horario y la ubicación del ctic",
    "gracias",
]


def _percentil(valores: list[float], pct: float) -> float:
    ordenados = sorted(valores)
    k = max(0, min(len(ordenados) - 1, round(pct / 100 * len(ordenados)) - 1))
    return ordenados[k]


async def test_promedio_de_respuesta_bajo_umbral(cliente):
    """El promedio de latencia de N mensajes de chat es ≤ 3 s (REN-01)."""
    chat = await helpers.crear_sesion(cliente)
    latencias: list[float] = []

    for i in range(N_MENSAJES):
        texto = _MENSAJES[i % len(_MENSAJES)]
        cuerpo = {"sessionId": chat.session_id, "texto": texto}
        resp = await helpers.peticion(
            cliente, "POST", "/api/chat/mensajes", json=cuerpo, headers=chat.headers
        )
        assert resp.status_code == 200, resp.text
        latencias.append(resp.elapsed.total_seconds())
        await asyncio.sleep(0.12)  # mantenerse bajo el rate-limit (sin contar en la medición)

    promedio = sum(latencias) / len(latencias)
    p95 = _percentil(latencias, 95)
    maximo = max(latencias)

    conftest.mediciones[f"QA-09 latencia (N={N_MENSAJES})"] = (
        f"promedio={promedio * 1000:.0f} ms · p95={p95 * 1000:.0f} ms · "
        f"máx={maximo * 1000:.0f} ms (umbral {UMBRAL_PROMEDIO_S:.0f} s)"
    )

    assert promedio <= UMBRAL_PROMEDIO_S, (
        f"El promedio {promedio:.3f} s supera el umbral REN-01 de {UMBRAL_PROMEDIO_S} s. "
        f"p95={p95:.3f} s, máx={maximo:.3f} s."
    )
