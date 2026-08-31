"""Evaluación de precisión del router de intenciones (tarea 6.6, prd/06 §7).

Envía cada frase del set de prueba (``datos/frases_intents.json``) a una sesión
NUEVA del chat (para que ningún flujo previo contamine el contexto) y compara el
intent detectado por el router —``meta.intent`` del primer mensaje del bot— con
el intent esperado por el anotador humano.

Objetivo de la tesis (prd/06 §7): precisión del router >= 90 %.

NOTA metodológica: sin ``ANTHROPIC_API_KEY`` real solo actúa la CAPA 1 (reglas
regex/keywords, ``app/dialogo/router.py``); la capa 2 (clasificador LLM) queda
inactiva y su ausencia se reporta explícitamente. El script detecta la vía de
clasificación (``meta.via`` = "regla" | "llm") y la incluye en el CSV, de modo
que el número reportado corresponde a la precisión de la capa efectivamente
activa durante la corrida.

Salida:
- ``salidas/precision_router.csv``: una fila por frase (esperado, detectado,
  acierto, via, confianza).
- ``salidas/precision_router_matriz.csv``: matriz de confusión simple
  (esperado x detectado).
- Resumen por consola con la precisión global y por intent.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos" / "frases_intents.json"
SALIDAS = RAIZ / "salidas"

REINTENTOS = 4  # tolerancia a 5xx transitorios de nginx/upstream


def post_resiliente(cliente: httpx.Client, path: str, **kwargs: object) -> httpx.Response:
    """POST con reintentos ante 5xx o errores de conexión (backoff simple)."""
    ultimo: Exception | None = None
    for intento in range(REINTENTOS):
        try:
            r = cliente.post(path, **kwargs)  # type: ignore[arg-type]
            if r.status_code < 500:
                return r
            ultimo = httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
        except httpx.TransportError as exc:
            ultimo = exc
        time.sleep(0.5 * (intento + 1))
    assert ultimo is not None
    raise ultimo


def crear_sesion(cliente: httpx.Client) -> tuple[str, str]:
    """Crea una sesión de chat nueva; devuelve (sessionId, sessionToken)."""
    r = post_resiliente(cliente, "/api/chat/sesiones", json={"canal": "web_widget"})
    r.raise_for_status()
    data = r.json()["data"]
    return data["sessionId"], data["sessionToken"]


def detectar_intent(cliente: httpx.Client, frase: str) -> tuple[str, str, float]:
    """Envía una frase a una sesión nueva y devuelve (intent, via, confianza).

    Lee el ``meta`` del primer mensaje del bot, donde el orquestador anota el
    intent, la vía (regla|llm) y la confianza del router (manager.py::_anotar_via).
    """
    session_id, token = crear_sesion(cliente)
    r = post_resiliente(
        cliente,
        "/api/chat/mensajes",
        headers={"X-Session-Token": token},
        json={"sessionId": session_id, "texto": frase},
    )
    r.raise_for_status()
    mensajes = r.json()["data"]["mensajes"]
    meta = (mensajes[0].get("meta") or {}) if mensajes else {}
    intent = meta.get("intent")
    if not intent:
        # Fallback: mensajes de flujo sin meta.intent no deberían ocurrir en el
        # primer turno de una sesión nueva; se registra como no_comprendida.
        intent = "no_comprendida"
    return str(intent), str(meta.get("via") or "-"), float(meta.get("confianza") or 0.0)


def evaluar(base_url: str) -> dict:
    """Ejecuta la evaluación completa contra el stack en ``base_url``."""
    casos = json.loads(DATOS.read_text(encoding="utf-8"))["casos"]
    filas: list[dict] = []
    aciertos_por_intent: dict[str, list[int]] = defaultdict(list)
    matriz: dict[tuple[str, str], int] = Counter()

    with httpx.Client(base_url=base_url, timeout=30.0) as cliente:
        for caso in casos:
            esperado = caso["esperado"]
            for frase in caso["frases"]:
                detectado, via, confianza = detectar_intent(cliente, frase)
                acierto = int(detectado == esperado)
                aciertos_por_intent[esperado].append(acierto)
                matriz[(esperado, detectado)] += 1
                filas.append(
                    {
                        "esperado": esperado,
                        "detectado": detectado,
                        "acierto": acierto,
                        "via": via,
                        "confianza": round(confianza, 2),
                        "frase": frase,
                    }
                )
                marca = "OK " if acierto else "XX "
                print(f"  {marca}[{esperado} -> {detectado}] {frase}")

    total = len(filas)
    aciertos = sum(f["acierto"] for f in filas)
    precision_global = aciertos / total if total else 0.0
    vias = Counter(f["via"] for f in filas)

    return {
        "filas": filas,
        "matriz": matriz,
        "aciertos_por_intent": aciertos_por_intent,
        "total": total,
        "aciertos": aciertos,
        "precision_global": precision_global,
        "vias": vias,
    }


def escribir_csv(res: dict) -> None:
    """Escribe el detalle y la matriz de confusión a ``salidas/``."""
    SALIDAS.mkdir(exist_ok=True)

    detalle = SALIDAS / "precision_router.csv"
    with detalle.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["esperado", "detectado", "acierto", "via", "confianza", "frase"]
        )
        writer.writeheader()
        writer.writerows(res["filas"])

    # Matriz de confusión (filas = esperado, columnas = detectado)
    etiquetas = sorted(
        {e for e, _ in res["matriz"]} | {d for _, d in res["matriz"]}
    )
    matriz_path = SALIDAS / "precision_router_matriz.csv"
    with matriz_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["esperado \\ detectado", *etiquetas])
        for esperado in sorted({e for e, _ in res["matriz"]}):
            fila = [res["matriz"].get((esperado, d), 0) for d in etiquetas]
            writer.writerow([esperado, *fila])

    print(f"\nCSV escrito: {detalle}")
    print(f"CSV escrito: {matriz_path}")


def imprimir_resumen(res: dict) -> None:
    """Imprime el resumen que alimenta el capítulo de resultados de la tesis."""
    print("\n" + "=" * 64)
    print("RESUMEN — Precisión del router de intenciones (capa 1, reglas)")
    print("=" * 64)
    print("\nPrecisión por intent:")
    for intent in sorted(res["aciertos_por_intent"]):
        marcas = res["aciertos_por_intent"][intent]
        p = sum(marcas) / len(marcas)
        print(f"  {intent:24s} {sum(marcas):>2}/{len(marcas):<2}  {p:6.1%}")

    print(f"\nVías de clasificación: {dict(res['vias'])}")
    print(
        f"\nPRECISIÓN GLOBAL: {res['aciertos']}/{res['total']} = "
        f"{res['precision_global']:.1%}"
    )
    objetivo = 0.90
    veredicto = "CUMPLE" if res["precision_global"] >= objetivo else "NO CUMPLE"
    print(f"Objetivo prd/06 §7 (>= 90%): {veredicto}")
    if "llm" not in res["vias"]:
        print(
            "\nNota: no se observó la vía 'llm'; sin ANTHROPIC_API_KEY real solo "
            "actúa la capa 1 (reglas). El número corresponde a esa capa."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host", default="http://localhost", help="Base URL del stack (nginx)"
    )
    args = parser.parse_args()

    print(f"Evaluando precisión del router contra {args.host} ...\n")
    res = evaluar(args.host)
    escribir_csv(res)
    imprimir_resumen(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
