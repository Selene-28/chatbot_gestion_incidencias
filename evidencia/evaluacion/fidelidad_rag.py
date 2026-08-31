"""Evaluación de fidelidad/recall del RAG (tarea 6.6, prd/06 §7).

Envía cada pregunta del set (``datos/preguntas_rag.json``) al chat usando el
mini-flujo de FAQ (botón ``faq_general`` → texto de la consulta), lo que fuerza
el paso por ``app.dialogo.flujos.faq.responder_faq`` (motor RAG) independiente-
mente de las palabras clave. Verifica si el artículo esperado es la FUENTE
PRINCIPAL devuelta en ``meta.fuentesKb`` (recall@1) y, como comprobación
complementaria, si aparece entre todas las fuentes citadas (recall@k).

Objetivo de la tesis (prd/06 §7): 30 preguntas con evaluación de fidelidad
(¿la respuesta está soportada por el artículo correcto?).

NOTA metodológica: sin ``ANTHROPIC_API_KEY`` real no hay REDACCIÓN generada por
el LLM; lo que se evalúa es la RECUPERACIÓN (retrieval). El chatbot conserva la
recuperación semántica por embeddings locales (``meta.via`` = "semantico") y, si
esta falla, degrada al FULLTEXT de MySQL (``meta.via`` = "fulltext"). Por tanto
este instrumento mide el recall@1 del retrieval, no la calidad de la redacción.

Salida:
- ``salidas/fidelidad_rag.csv``: una fila por pregunta (esperado, recuperado,
  recall@1, recall@k, via, fuentes).
- Resumen por consola con recall@1 y recall@k.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos" / "preguntas_rag.json"
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


def mapa_articulos(cliente: httpx.Client) -> dict[int, str]:
    """Mapa id->título de los artículos KB (requiere login admin).

    Permite traducir los IDs de ``meta.fuentesKb`` a títulos para comparar con
    el ``articulo_esperado`` del set de prueba.
    """
    r = cliente.get("/api/kb/articulos", params={"size": 100})
    r.raise_for_status()
    items = r.json()["data"]["items"]
    return {int(a["id"]): a["titulo"] for a in items}


def login_admin(cliente: httpx.Client, correo: str, password: str) -> None:
    """Inicia sesión como admin; la cookie ``panel_token`` queda en el cliente."""
    r = post_resiliente(cliente, "/api/auth/login", json={"correo": correo, "password": password})
    r.raise_for_status()


def crear_sesion(cliente: httpx.Client) -> tuple[str, str]:
    """Crea una sesión de chat nueva; devuelve (sessionId, sessionToken)."""
    r = post_resiliente(cliente, "/api/chat/sesiones", json={"canal": "web_widget"})
    r.raise_for_status()
    data = r.json()["data"]
    return data["sessionId"], data["sessionToken"]


def consultar_faq(cliente: httpx.Client, pregunta: str) -> tuple[list[int], str]:
    """Ejecuta el mini-flujo FAQ y devuelve (fuentesKb, via) de la respuesta.

    1) botón ``faq_general`` → el bot pide la consulta.
    2) texto de la pregunta → el bot responde vía ``responder_faq`` (RAG).
    """
    session_id, token = crear_sesion(cliente)
    headers = {"X-Session-Token": token}
    post_resiliente(
        cliente,
        "/api/chat/mensajes",
        headers=headers,
        json={"sessionId": session_id, "opcionId": "faq_general"},
    ).raise_for_status()
    r = post_resiliente(
        cliente,
        "/api/chat/mensajes",
        headers=headers,
        json={"sessionId": session_id, "texto": pregunta},
    )
    r.raise_for_status()
    for mensaje in r.json()["data"]["mensajes"]:
        meta = mensaje.get("meta") or {}
        if "fuentesKb" in meta or meta.get("via"):
            fuentes = [int(x) for x in (meta.get("fuentesKb") or [])]
            return fuentes, str(meta.get("via") or "-")
    return [], "sin_meta"


def evaluar(base_url: str, correo: str, password: str) -> dict:
    """Ejecuta la evaluación completa contra el stack en ``base_url``."""
    preguntas = json.loads(DATOS.read_text(encoding="utf-8"))["preguntas"]
    filas: list[dict] = []

    with httpx.Client(base_url=base_url, timeout=60.0) as cliente:
        login_admin(cliente, correo, password)
        id_a_titulo = mapa_articulos(cliente)

        for item in preguntas:
            pregunta = item["pregunta"]
            esperado = item["articulo_esperado"]
            fuentes, via = consultar_faq(cliente, pregunta)
            titulos = [id_a_titulo.get(fid, f"#{fid}") for fid in fuentes]
            recuperado = titulos[0] if titulos else "(sin fuente)"
            recall_1 = int(bool(titulos) and titulos[0] == esperado)
            recall_k = int(esperado in titulos)
            filas.append(
                {
                    "esperado": esperado,
                    "recuperado": recuperado,
                    "recall_1": recall_1,
                    "recall_k": recall_k,
                    "via": via,
                    "fuentes": " | ".join(titulos) if titulos else "",
                    "pregunta": pregunta,
                }
            )
            marca = "OK " if recall_1 else ("~k " if recall_k else "XX ")
            print(f"  {marca}[{esperado[:34]:34s} <- {recuperado[:34]:34s}] {pregunta[:40]}")

    total = len(filas)
    r1 = sum(f["recall_1"] for f in filas)
    rk = sum(f["recall_k"] for f in filas)
    vias = {}
    for f in filas:
        vias[f["via"]] = vias.get(f["via"], 0) + 1
    return {
        "filas": filas,
        "total": total,
        "recall_1": r1 / total if total else 0.0,
        "recall_k": rk / total if total else 0.0,
        "aciertos_1": r1,
        "aciertos_k": rk,
        "vias": vias,
    }


def escribir_csv(res: dict) -> None:
    """Escribe el detalle a ``salidas/fidelidad_rag.csv``."""
    SALIDAS.mkdir(exist_ok=True)
    ruta = SALIDAS / "fidelidad_rag.csv"
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "esperado", "recuperado", "recall_1", "recall_k", "via", "fuentes", "pregunta"
            ],
        )
        writer.writeheader()
        writer.writerows(res["filas"])
    print(f"\nCSV escrito: {ruta}")


def imprimir_resumen(res: dict) -> None:
    """Imprime el resumen que alimenta el capítulo de resultados de la tesis."""
    print("\n" + "=" * 64)
    print("RESUMEN — Fidelidad/recall del RAG (recuperación semántica)")
    print("=" * 64)
    print(f"\nVías de respuesta: {res['vias']}")
    print(
        f"\nRECALL@1: {res['aciertos_1']}/{res['total']} = {res['recall_1']:.1%}"
        f"   (el artículo esperado es la fuente PRINCIPAL)"
    )
    print(
        f"RECALL@k: {res['aciertos_k']}/{res['total']} = {res['recall_k']:.1%}"
        f"   (el artículo esperado aparece entre las fuentes citadas)"
    )
    print(
        "\nNota: sin ANTHROPIC_API_KEY real se evalúa la RECUPERACIÓN "
        "(retrieval semántico/textual), no la redacción generada."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://localhost", help="Base URL del stack (nginx)")
    parser.add_argument("--correo", default="admin@ctic.local", help="Correo admin del panel")
    parser.add_argument("--password", default="cambiar", help="Contraseña admin del panel")
    args = parser.parse_args()

    print(f"Evaluando fidelidad del RAG contra {args.host} ...\n")
    res = evaluar(args.host, args.correo, args.password)
    escribir_csv(res)
    imprimir_resumen(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
