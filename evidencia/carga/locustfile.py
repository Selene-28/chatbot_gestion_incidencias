"""Prueba de carga del chatbot CTIC-FIIS UNAC (tarea 6.2, prd/02 §8, REN-04).

Simula usuarios concurrentes del widget web ejecutando flujos MIXTOS y realistas
sobre el protocolo de chat (prd/04 §4). Cada usuario (``WidgetUser``) crea su
propia sesión (``POST /api/chat/sesiones``) en ``on_start`` y usa su
``X-Session-Token`` en cada mensaje, tal como el widget real.

Los IDs de botón NO se hardcodean: cada tarea INSPECCIONA la respuesta del bot y
descubre las opciones a pulsar (área ``area_*``, categoría ``cat_*``, prioridad
``prio_*``, confirmar, etc.). Así la prueba sigue siendo válida aunque cambien
los catálogos de ``app/dialogo/flujos/``.

Flujos simulados (ponderados):
- saludar (peso 2),
- consultar una FAQ vía el mini-flujo de preguntas frecuentes (peso 3),
- registrar una incidencia completa recorriendo F-02 (peso 2),
- consultar el estado de incidencias por correo, F-03 (peso 2),
- pedir información del CTIC (peso 1).

Objetivo prd/02 §8: 50 sesiones concurrentes. Criterio de aceptación
(QA-09/QA-11): p95 de latencia < 3 s en los flujos y 0 errores 5xx.

Escenario reproducible (headless), documentado en el README::

    locust -f carga/locustfile.py --headless -u 50 -r 5 -t 60s \
        --host http://localhost \
        --csv salidas/carga --html salidas/carga_reporte.html

- ``-u 50``  : 50 usuarios concurrentes (objetivo REN-04).
- ``-r 5``   : rampa de 5 usuarios/segundo.
- ``-t 60s`` : duración 60 segundos.
- ``--csv``  : vuelca *_stats.csv / *_stats_history.csv / *_failures.csv.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from locust import HttpUser, between, task

# Preguntas realistas para el mini-flujo de FAQ (variadas por dominio).
PREGUNTAS_FAQ = [
    "Cómo recupero la contraseña de mi correo institucional",
    "Cómo me conecto al WiFi del campus",
    "No puedo entrar al aula virtual, qué hago",
    "Cómo instalo Office 365 con mi cuenta de la UNAC",
    "Cuál es el horario de atención del CTIC",
    "Cómo solicito la VPN institucional",
    "Cómo accedo al SGA",
    "Mi cuenta está bloqueada, cómo la desbloqueo",
]

DESCRIPCIONES = [
    "No puedo acceder a mi correo institucional desde ayer por la tarde.",
    "El aula virtual no me carga los cursos y ya revisé mi matrícula.",
    "El WiFi del laboratorio conecta pero no tengo salida a internet.",
    "Office me pide comprar una licencia y no debería según el convenio.",
    "No logro instalar MATLAB, la licencia campus no aparece en mi cuenta.",
]

CORREOS = [f"usuario{n}@unac.edu.pe" for n in range(1, 40)]


def ids_opciones(mensajes: list[dict]) -> list[str]:
    """Extrae, en orden, todos los IDs de botón presentes en la respuesta."""
    ids: list[str] = []
    for mensaje in mensajes:
        for opcion in mensaje.get("opciones") or []:
            ids.append(opcion["id"])
    return ids


def primer_id(mensajes: list[dict], predicado: Callable[[str], bool]) -> str | None:
    """Primer ID de botón que cumple ``predicado`` (para descubrir opciones)."""
    for opcion_id in ids_opciones(mensajes):
        if predicado(opcion_id):
            return opcion_id
    return None


class WidgetUser(HttpUser):
    """Usuario del widget: una sesión propia y flujos conversacionales mixtos."""

    # Pausa realista entre acciones del usuario (piensa/lee la respuesta).
    wait_time = between(0.5, 2.5)

    def on_start(self) -> None:
        """Crea la sesión de chat del usuario (su propio token)."""
        self.session_id: str | None = None
        self.token: str | None = None
        with self.client.post(
            "/api/chat/sesiones",
            json={"canal": "web_widget"},
            name="POST /api/chat/sesiones",
            catch_response=True,
        ) as resp:
            if resp.status_code != 201:
                resp.failure(f"crear sesión devolvió {resp.status_code}")
                return
            data = resp.json().get("data", {})
            self.session_id = data.get("sessionId")
            self.token = data.get("sessionToken")
            resp.success()

    # ------------------------------------------------------------- utilidades

    def _mensaje(self, cuerpo: dict, etiqueta: str) -> list[dict]:
        """Envía un mensaje y devuelve la lista de mensajes del bot.

        Marca como fallo cualquier 5xx o envelope con ``success=false`` (evidencia
        honesta del criterio QA-09/QA-11: 0 errores 5xx). ``name`` agrupa las
        métricas por flujo para leer el p95 de cada uno.
        """
        if not self.session_id or not self.token:
            return []
        cuerpo = {"sessionId": self.session_id, **cuerpo}
        with self.client.post(
            "/api/chat/mensajes",
            json=cuerpo,
            headers={"X-Session-Token": self.token},
            name=f"POST /api/chat/mensajes [{etiqueta}]",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 500:
                resp.failure(f"5xx: {resp.status_code}")
                return []
            if resp.status_code != 200:
                resp.failure(f"status {resp.status_code}")
                return []
            cuerpo_json = resp.json()
            if not cuerpo_json.get("success", False):
                resp.failure(f"success=false: {cuerpo_json.get('message')}")
                return []
            resp.success()
            return cuerpo_json.get("data", {}).get("mensajes", [])

    def _volver_al_menu(self) -> None:
        """Escape global: cancela cualquier flujo activo antes de la próxima tarea."""
        self._mensaje({"opcionId": "menu"}, "menu")

    # ---------------------------------------------------------------- tareas

    @task(2)
    def saludar(self) -> None:
        """Flujo social simple: el usuario saluda."""
        self._mensaje({"texto": random.choice(["Hola", "Buenos días", "Buenas"])}, "saludo")

    @task(1)
    def info_ctic(self) -> None:
        """Consulta de información institucional del CTIC (FULLTEXT)."""
        self._mensaje({"opcionId": "info_ctic"}, "info_ctic")
        self._volver_al_menu()

    @task(3)
    def faq(self) -> None:
        """Mini-flujo de preguntas frecuentes: botón + consulta (motor RAG)."""
        self._mensaje({"opcionId": "faq_general"}, "faq:inicio")
        self._mensaje({"texto": random.choice(PREGUNTAS_FAQ)}, "faq:consulta")
        self._volver_al_menu()

    @task(2)
    def registrar_incidencia(self) -> None:
        """F-02 completo: identificación → área → categoría → descripción →
        prioridad → adjunto (omitir) → confirmar. Descubre los IDs de botón."""
        self._mensaje({"opcionId": "registrar_incidencia"}, "registrar:inicio")
        self._mensaje({"texto": "Juan Pérez López"}, "registrar:nombre")
        msgs = self._mensaje({"texto": random.choice(CORREOS)}, "registrar:correo")

        area = primer_id(msgs, lambda i: i.startswith("area_"))
        if not area:
            return self._volver_al_menu()
        msgs = self._mensaje({"opcionId": area}, "registrar:area")

        categoria = primer_id(msgs, lambda i: i.startswith("cat_"))
        if not categoria:
            return self._volver_al_menu()
        self._mensaje({"opcionId": categoria}, "registrar:categoria")

        msgs = self._mensaje({"texto": random.choice(DESCRIPCIONES)}, "registrar:descripcion")

        prioridad = primer_id(msgs, lambda i: i.startswith("prio_"))
        if not prioridad:
            return self._volver_al_menu()
        msgs = self._mensaje({"opcionId": prioridad}, "registrar:prioridad")

        # Paso de adjunto: descubrir el botón "omitir" (o su variante del widget).
        omitir = primer_id(msgs, lambda i: i in ("omitir", "__omitir__")) or "omitir"
        msgs = self._mensaje({"opcionId": omitir}, "registrar:adjunto")

        confirmar = primer_id(msgs, lambda i: i == "confirmar") or "confirmar"
        self._mensaje({"opcionId": confirmar}, "registrar:confirmar")
        self._volver_al_menu()

    @task(2)
    def consultar_estado(self) -> None:
        """F-03: consulta por correo; descubre y elige un ticket si hay lista."""
        msgs = self._mensaje({"opcionId": "consultar_estado"}, "consultar:inicio")
        # La sesión puede no estar identificada → el bot pide el correo.
        if any("correo" in (m.get("texto") or "").lower() for m in msgs):
            msgs = self._mensaje({"texto": random.choice(CORREOS)}, "consultar:correo")
        # Elegir "Por mi correo" si aparece el selector de modo.
        modo = primer_id(msgs, lambda i: i == "modo_correo")
        if modo:
            msgs = self._mensaje({"opcionId": modo}, "consultar:modo")
        # Si hay tickets, abrir el detalle del primero (IDs INC-*).
        ticket = primer_id(msgs, lambda i: i.startswith("INC-"))
        if ticket:
            self._mensaje({"opcionId": ticket}, "consultar:detalle")
        self._volver_al_menu()
