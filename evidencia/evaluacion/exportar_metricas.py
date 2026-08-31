"""Exportación de las KPIs de la tesis a CSV (tarea 6.6, prd/04 §8, prd/03 §4).

Consume ``GET /api/metricas/resumen?desde&hasta`` (rol admin) y vuelca las KPIs
del pre/post-test a ``salidas/metricas_resumen.csv``. Este es el INSTRUMENTO de
medición del diseño pre-experimental: se ejecuta una vez para el pre-test y otra
para el post-test, con el mismo rango relativo, y se comparan los CSV.

KPIs exportadas (prd/00 §3):
- conversaciones y mensajes del rango,
- tasa de autoservicio (conversaciones resueltas sin ticket),
- latencia promedio del bot (ms) — REN-01 (< 3 s),
- calificación promedio de satisfacción (1-5) y nº de encuestas,
- tickets por estado,
- intents más frecuentes (top).

Genera dos CSV:
- ``metricas_resumen.csv``: una fila con las KPIs escalares (formato ancho, ideal
  para pegar en la matriz pre/post del capítulo de resultados).
- ``metricas_intents.csv``: el desglose de intents top (formato largo).
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
SALIDAS = RAIZ / "salidas"


def login_admin(cliente: httpx.Client, correo: str, password: str) -> None:
    """Inicia sesión como admin; la cookie ``panel_token`` queda en el cliente."""
    r = cliente.post("/api/auth/login", json={"correo": correo, "password": password})
    r.raise_for_status()


def obtener_resumen(cliente: httpx.Client, desde: str, hasta: str) -> dict:
    """Llama a GET /api/metricas/resumen y devuelve el bloque ``data``."""
    r = cliente.get("/api/metricas/resumen", params={"desde": desde, "hasta": hasta})
    r.raise_for_status()
    return r.json()["data"]


def escribir_csv(data: dict, desde: str, hasta: str) -> tuple[Path, Path]:
    """Escribe los dos CSV (KPIs escalares y desglose de intents)."""
    SALIDAS.mkdir(exist_ok=True)
    estados = data.get("ticketsPorEstado") or {}

    resumen = {
        "desde": desde,
        "hasta": hasta,
        "conversaciones": data.get("conversaciones"),
        "mensajes": data.get("mensajes"),
        "tasaAutoservicio": data.get("tasaAutoservicio"),
        "latenciaPromMs": data.get("latenciaPromMs"),
        "calificacionProm": data.get("calificacionProm"),
        "encuestas": data.get("encuestas"),
        "tokensLlm": data.get("tokensLlm"),
        "ticketsTotal": sum(estados.values()) if estados else 0,
        "ticketsPorEstado": "; ".join(f"{k}={v}" for k, v in estados.items()),
    }
    ruta_resumen = SALIDAS / "metricas_resumen.csv"
    with ruta_resumen.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(resumen.keys()))
        writer.writeheader()
        writer.writerow(resumen)

    ruta_intents = SALIDAS / "metricas_intents.csv"
    with ruta_intents.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["intent", "total"])
        for fila in data.get("intentsTop") or []:
            writer.writerow([fila.get("intent"), fila.get("total")])

    return ruta_resumen, ruta_intents


def imprimir_resumen(data: dict, desde: str, hasta: str) -> None:
    """Muestra las KPIs por consola."""
    print("\n" + "=" * 64)
    print(f"KPIs del rango {desde} .. {hasta} (instrumento pre/post-test)")
    print("=" * 64)
    print(f"  Conversaciones .......... {data.get('conversaciones')}")
    print(f"  Mensajes ................ {data.get('mensajes')}")
    print(f"  Tasa de autoservicio .... {data.get('tasaAutoservicio')}")
    print(f"  Latencia promedio (ms) .. {data.get('latenciaPromMs')}  (REN-01: < 3000)")
    print(f"  Calificación promedio ... {data.get('calificacionProm')}  (escala 1-5)")
    print(f"  Encuestas ............... {data.get('encuestas')}")
    print(f"  Tickets por estado ...... {data.get('ticketsPorEstado')}")
    print(f"  Tokens LLM consumidos ... {data.get('tokensLlm')}")
    print("  Intents top:")
    for fila in data.get("intentsTop") or []:
        print(f"    - {fila.get('intent'):24s} {fila.get('total')}")


def main() -> int:
    hoy = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://localhost", help="Base URL del stack (nginx)")
    parser.add_argument("--correo", default="admin@ctic.local", help="Correo admin del panel")
    parser.add_argument("--password", default="cambiar", help="Contraseña admin del panel")
    parser.add_argument(
        "--desde",
        default=(hoy - timedelta(days=30)).isoformat(),
        help="Fecha inicial YYYY-MM-DD (por defecto: hace 30 días)",
    )
    parser.add_argument(
        "--hasta", default=hoy.isoformat(), help="Fecha final YYYY-MM-DD (por defecto: hoy)"
    )
    args = parser.parse_args()

    print(f"Exportando métricas de {args.host} para {args.desde}..{args.hasta} ...")
    with httpx.Client(base_url=args.host, timeout=30.0) as cliente:
        login_admin(cliente, args.correo, args.password)
        data = obtener_resumen(cliente, args.desde, args.hasta)

    ruta_resumen, ruta_intents = escribir_csv(data, args.desde, args.hasta)
    imprimir_resumen(data, args.desde, args.hasta)
    print(f"\nCSV escrito: {ruta_resumen}")
    print(f"CSV escrito: {ruta_intents}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
