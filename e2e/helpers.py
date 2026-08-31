"""Utilidades de la suite E2E: cliente HTTP resiliente, conducción de
conversaciones por /api/chat y recorrido del flujo F-02 completo.

Todo apunta al stack completo detrás de nginx (``E2E_BASE_URL``, por defecto
``http://localhost``). Los IDs de botón NO se hardcodean a ciegas: cada
``Respuesta`` expone ``elegir(...)`` para descubrir el id real leyéndolo de las
``opciones`` que devuelve el bot (contrato prd/04 §4). Los ids reales están
documentados en el README (``area_*``, ``cat_*``, ``prio_*``, ``confirmar``...).
"""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import httpx

# --- Configuración (todo sobre-escribible por entorno) -------------------------

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost")
API_KEY = os.environ.get("E2E_API_KEY", "cambiar")
STAFF_PASSWORD = os.environ.get("E2E_STAFF_PASSWORD", "cambiar")
STAFF_ADMIN = os.environ.get("E2E_STAFF_ADMIN", "admin@ctic.local")
STAFF_TECNICO = os.environ.get("E2E_STAFF_TECNICO", "tecnico1@ctic.local")

DOMINIO_INSTITUCIONAL = "unac.edu.pe"
PATRON_TICKET = re.compile(r"INC-\d{4}-\d{4}", re.IGNORECASE)

# Reintentos ante el rate-limit de nginx (10 r/s, ráfaga 20): 429/503 son
# transitorios de infraestructura, no fallos de la aplicación.
CODIGOS_REINTENTABLES = frozenset({429, 503})
MAX_REINTENTOS = 4


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (matching de etiquetas)."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


async def peticion(
    client: httpx.AsyncClient, metodo: str, url: str, **kwargs: Any
) -> httpx.Response:
    """Petición con reintentos ante el rate-limit (429/503) de nginx."""
    resp = None
    for intento in range(MAX_REINTENTOS):
        resp = await client.request(metodo, url, **kwargs)
        if resp.status_code not in CODIGOS_REINTENTABLES:
            return resp
        await asyncio.sleep(0.4 * (intento + 1))
    assert resp is not None
    return resp


def headers_api_key() -> dict[str, str]:
    """Cabecera de autenticación de servicio (chatbot-api → ticket-service)."""
    return {"X-Api-Key": API_KEY}


# --- Respuesta del bot ---------------------------------------------------------


@dataclass
class Respuesta:
    """Respuesta de ``POST /api/chat/mensajes`` ya parseada (data del envelope)."""

    status_code: int
    mensajes: list[dict[str, Any]] = field(default_factory=list)
    estado_bot: str = ""
    cruda: dict[str, Any] = field(default_factory=dict)

    @property
    def textos(self) -> list[str]:
        return [str(m.get("texto", "")) for m in self.mensajes]

    @property
    def texto(self) -> str:
        """Todo el texto de los mensajes del turno concatenado."""
        return "\n".join(self.textos)

    @property
    def opciones(self) -> list[dict[str, str]]:
        """Todas las opciones (botones) de todos los mensajes del turno."""
        botones: list[dict[str, str]] = []
        for m in self.mensajes:
            botones.extend(m.get("opciones") or [])
        return botones

    @property
    def ids_opciones(self) -> list[str]:
        return [str(o["id"]) for o in self.opciones]

    @property
    def tipos(self) -> list[str]:
        return [str(m.get("tipo", "")) for m in self.mensajes]

    def metas(self) -> list[dict[str, Any]]:
        return [m["meta"] for m in self.mensajes if m.get("meta")]

    def buscar_meta(self, clave: str) -> Any:
        """Primer valor no nulo de ``clave`` en el meta de cualquier mensaje."""
        for meta in self.metas():
            if meta.get(clave) is not None:
                return meta[clave]
        return None

    @property
    def ticket_id(self) -> str | None:
        """Código de ticket del turno: por meta ``ticketId`` o por regex del texto."""
        por_meta = self.buscar_meta("ticketId")
        if por_meta:
            return str(por_meta)
        m = PATRON_TICKET.search(self.texto)
        return m.group(0).upper() if m else None

    def elegir(self, contiene: str) -> str:
        """Descubre el id de un botón cuyo texto (o id) contenga ``contiene``.

        No hardcodea el id: lo lee de las ``opciones`` devueltas por el bot y
        empareja por etiqueta normalizada (o por el propio id como respaldo).
        """
        objetivo = normalizar(contiene)
        for opcion in self.opciones:
            etiqueta = normalizar(str(opcion.get("texto", "")))
            ident = normalizar(str(opcion.get("id", "")))
            if objetivo in etiqueta or objetivo in ident:
                return str(opcion["id"])
        disponibles = [(o.get("id"), o.get("texto")) for o in self.opciones]
        raise AssertionError(
            f"No se encontró un botón que contenga {contiene!r}. Opciones: {disponibles}"
        )


# --- Conversación de chat ------------------------------------------------------


@dataclass
class Chat:
    """Conversación de chat viva (sessionId + token de sesión)."""

    client: httpx.AsyncClient
    session_id: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Session-Token": self.token}

    async def enviar(
        self,
        texto: str | None = None,
        opcion: str | None = None,
        adjunto: str | None = None,
        esperar_ok: bool = True,
    ) -> Respuesta:
        """Envía un turno (texto libre o botón) y devuelve la ``Respuesta`` del bot."""
        cuerpo: dict[str, Any] = {"sessionId": self.session_id}
        if texto is not None:
            cuerpo["texto"] = texto
        if opcion is not None:
            cuerpo["opcionId"] = opcion
        if adjunto is not None:
            cuerpo["adjuntoId"] = adjunto
        resp = await peticion(
            self.client, "POST", "/api/chat/mensajes", json=cuerpo, headers=self.headers
        )
        if esperar_ok:
            assert resp.status_code == 200, (
                f"Se esperaba 200 en /api/chat/mensajes, llegó {resp.status_code}: "
                f"{resp.text[:300]}"
            )
        cuerpo_resp = resp.json()
        data = cuerpo_resp.get("data") or {}
        return Respuesta(
            status_code=resp.status_code,
            mensajes=data.get("mensajes", []),
            estado_bot=data.get("estadoBot", ""),
            cruda=cuerpo_resp,
        )


async def crear_sesion(client: httpx.AsyncClient) -> Chat:
    """Crea una sesión de chat nueva (POST /api/chat/sesiones) → ``Chat``."""
    resp = await peticion(
        client, "POST", "/api/chat/sesiones", json={"canal": "web_widget"}
    )
    assert resp.status_code == 201, f"No se pudo crear la sesión: {resp.text[:300]}"
    data = resp.json()["data"]
    return Chat(client=client, session_id=data["sessionId"], token=data["sessionToken"])


# --- Datos de prueba y recorrido del flujo F-02 --------------------------------

# Cada test genera un correo propio para no depender de datos preexistentes.
_contador = 0


def correo_unico(prefijo: str = "e2e") -> str:
    """Correo institucional único por invocación (aislamiento entre tests)."""
    global _contador
    _contador += 1
    return f"{prefijo}{os.getpid()}_{_contador}@{DOMINIO_INSTITUCIONAL}"


def datos_incidencia(**sobrescribir: Any) -> dict[str, str]:
    """Datos por defecto de una incidencia F-02 (con correo único)."""
    base = {
        "nombre": "Usuario E2E de Prueba",
        "correo": correo_unico(),
        "area": "Industrial",
        "categoria": "Correo Institucional",
        "descripcion": "No puedo acceder a mi correo institucional desde ayer por la tarde.",
        "prioridad": "Media",
    }
    base.update(sobrescribir)
    return base


async def recorrer_registro(chat: Chat, datos: dict[str, str]) -> str:
    """Recorre el flujo F-02 completo por chat y devuelve el código del ticket.

    Descubre los ids de botón (``area_*``, ``cat_*``, ``prio_*``, ``omitir``,
    ``confirmar``) leyéndolos de cada respuesta del bot. Asume una sesión NO
    identificada (arranca pidiendo nombre y correo).
    """
    await chat.enviar(opcion="registrar_incidencia")  # → pide nombre
    await chat.enviar(texto=datos["nombre"])  # → pide correo
    r_area = await chat.enviar(texto=datos["correo"])  # → botones de escuela
    r_cat = await chat.enviar(opcion=r_area.elegir(datos["area"]))  # → categorías
    await chat.enviar(opcion=r_cat.elegir(datos["categoria"]))  # → pide descripción
    r_prio = await chat.enviar(texto=datos["descripcion"])  # → botones de prioridad
    r_adj = await chat.enviar(opcion=r_prio.elegir(datos["prioridad"]))  # → adjunto
    r_conf = await chat.enviar(opcion=r_adj.elegir("omitir"))  # → confirmación
    r_final = await chat.enviar(opcion=r_conf.elegir("confirmar"))  # → creado
    ticket_id = r_final.ticket_id
    assert ticket_id is not None, (
        "El registro no devolvió un código de ticket. "
        f"Mensajes: {r_final.textos}"
    )
    return ticket_id


# --- ticket-service (contratos del DRS) ----------------------------------------


async def consultar_ticket(
    client: httpx.AsyncClient, ticket_id: str, correo: str
) -> httpx.Response:
    """API-02: GET /api/incidencias/{id}?correo=... (auth de servicio)."""
    return await peticion(
        client,
        "GET",
        f"/api/incidencias/{ticket_id}",
        params={"correo": correo},
        headers=headers_api_key(),
    )


async def escalar_ticket(
    client: httpx.AsyncClient, ticket_id: str, motivo: str, correo: str
) -> httpx.Response:
    """API-03: PUT /api/incidencias/escalar (auth de servicio)."""
    return await peticion(
        client,
        "PUT",
        "/api/incidencias/escalar",
        json={"ticketId": ticket_id, "motivo": motivo, "correo": correo},
        headers=headers_api_key(),
    )


async def registrar_encuesta(
    client: httpx.AsyncClient,
    calificacion: int,
    ticket_id: str | None = None,
    conversacion_codigo: str | None = None,
    comentario: str | None = None,
) -> httpx.Response:
    """API-06: POST /api/encuesta (auth de servicio)."""
    cuerpo: dict[str, Any] = {"calificacion": calificacion}
    if ticket_id is not None:
        cuerpo["ticketId"] = ticket_id
    if conversacion_codigo is not None:
        cuerpo["conversacionCodigo"] = conversacion_codigo
    if comentario is not None:
        cuerpo["comentario"] = comentario
    return await peticion(
        client, "POST", "/api/encuesta", json=cuerpo, headers=headers_api_key()
    )


# --- Panel / staff -------------------------------------------------------------


async def login_staff(
    client: httpx.AsyncClient, correo: str, password: str = STAFF_PASSWORD
) -> httpx.Response:
    """Login del panel; la cookie ``panel_token`` queda en el cliente httpx."""
    resp = await peticion(
        client,
        "POST",
        "/api/auth/login",
        json={"correo": correo, "password": password},
    )
    assert resp.status_code == 200, f"Login de staff falló ({correo}): {resp.text[:300]}"
    return resp
