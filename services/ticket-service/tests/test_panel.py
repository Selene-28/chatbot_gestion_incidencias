"""Pruebas del panel de agentes (tarea 2.5): rutas HTML y API JSON.

La capa de servicio de dominio (tarea 2.4, en paralelo) se sustituye por un
stub (_servicio_tickets se monkeypatchea) y la sesión de staff se inyecta con
dependency_overrides, así estas pruebas pasan sin MySQL ni el dominio real.
"""

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import panel as panel_api
from app.core import deps
from app.core.errors import ConflictError, NotFoundError
from app.main import create_app
from app.panel import consultas, routes

AHORA = datetime(2026, 7, 3, 10, 0, 0)

STAFF = SimpleNamespace(
    id=7, nombre="Paul Barzola", correo="tecnico1@ctic.local", rol="tecnico", activo=True
)
ADMIN = SimpleNamespace(
    id=1, nombre="Ana Admin", correo="admin@ctic.local", rol="admin", activo=True
)
TECNICOS = [
    SimpleNamespace(id=7, nombre="Paul Barzola", correo="tecnico1@ctic.local"),
]
CATEGORIAS = [SimpleNamespace(id=2, nombre="Correo Institucional")]


def _ticket(estado: str = "Registrado") -> Any:
    return SimpleNamespace(
        codigo="INC-2026-0001",
        estado=estado,
        prioridad="Media",
        descripcion="No puedo acceder a mi correo institucional.",
        subcategoria="Recuperación de contraseña",
        created_at=AHORA,
        updated_at=AHORA,
        usuario=SimpleNamespace(id=1, nombre="Juan Pérez", correo="jperez@unac.edu.pe"),
        categoria=SimpleNamespace(id=2, nombre="Correo Institucional"),
        tecnico=None,
        respuesta=None,
        adjuntos=[],
        historial=[
            SimpleNamespace(
                estado_anterior=None,
                estado_nuevo="Registrado",
                comentario="Ticket creado desde el chatbot.",
                actor=None,
                created_at=AHORA,
            )
        ],
    )


class ServicioFalso:
    """Stub del contrato de app.services.tickets (tarea 2.4)."""

    def __init__(self, ticket: Any) -> None:
        self.ticket = ticket
        self.llamadas: list[tuple] = []

    async def obtener_ticket(self, session: Any, codigo: str) -> Any:
        if codigo != self.ticket.codigo:
            raise NotFoundError("El ticket no existe.")
        return self.ticket

    async def listar_tickets(
        self,
        session: Any,
        *,
        estado: Any = None,
        categoria_id: Any = None,
        tecnico_id: Any = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list, int]:
        self.llamadas.append(("listar", estado, categoria_id, tecnico_id, page, size))
        return [self.ticket], 1

    async def cambiar_estado(
        self,
        session: Any,
        *,
        codigo: str,
        nuevo_estado: str,
        actor_id: int | None,
        comentario: str | None = None,
        libre: bool = False,
    ) -> Any:
        self.llamadas.append(("cambiar_estado", codigo, nuevo_estado, actor_id, comentario))
        self.ticket.estado = nuevo_estado
        return self.ticket

    async def asignar_tecnico(
        self, session: Any, *, codigo: str, tecnico_id: int, actor_id: int
    ) -> Any:
        self.llamadas.append(("asignar_tecnico", codigo, tecnico_id, actor_id))
        self.ticket.tecnico = next(t for t in TECNICOS if t.id == tecnico_id)
        return self.ticket

    async def guardar_respuesta(
        self, session: Any, *, codigo: str, texto: str, actor_id: int
    ) -> Any:
        self.llamadas.append(("guardar_respuesta", codigo, texto, actor_id))
        self.ticket.respuesta = texto
        return self.ticket

    async def obtener_adjunto(self, session: Any, *, codigo: str, adjunto_id: int) -> Any:
        self.llamadas.append(("obtener_adjunto", codigo, adjunto_id))
        for adjunto in self.ticket.adjuntos:
            if adjunto.id == adjunto_id:
                return adjunto
        raise NotFoundError("El adjunto indicado no existe.")


@pytest.fixture()
def servicio(monkeypatch: pytest.MonkeyPatch) -> ServicioFalso:
    stub = ServicioFalso(_ticket())
    monkeypatch.setattr(panel_api, "_servicio_tickets", lambda: stub)
    monkeypatch.setattr(routes, "_servicio_tickets", lambda: stub)

    async def tecnicos(session: Any) -> list:
        return TECNICOS

    async def categorias(session: Any) -> list:
        return CATEGORIAS

    monkeypatch.setattr(consultas, "listar_tecnicos", tecnicos)
    monkeypatch.setattr(consultas, "listar_categorias", categorias)
    return stub


@pytest.fixture()
def app_panel() -> FastAPI:
    app = create_app()
    app.include_router(panel_api.router)
    app.include_router(routes.router)
    return app


@pytest.fixture()
def anonimo(app_panel: FastAPI) -> TestClient:
    """Cliente sin sesión."""
    return TestClient(app_panel, raise_server_exceptions=False)


@pytest.fixture()
def autenticado(app_panel: FastAPI) -> TestClient:
    """Cliente con staff mockeado (HTML y JSON)."""
    app_panel.dependency_overrides[deps.staff_opcional] = lambda: STAFF
    app_panel.dependency_overrides[deps.require_staff] = lambda: STAFF
    return TestClient(app_panel, raise_server_exceptions=False)


@pytest.fixture()
def admin(app_panel: FastAPI) -> TestClient:
    """Cliente con sesión de administrador mockeada."""
    app_panel.dependency_overrides[deps.staff_opcional] = lambda: ADMIN
    app_panel.dependency_overrides[deps.require_staff] = lambda: ADMIN
    app_panel.dependency_overrides[deps.require_admin] = lambda: ADMIN
    return TestClient(app_panel, raise_server_exceptions=False)


# --------------------------------------------------------------------------- #
# Rutas HTML — sin sesión
# --------------------------------------------------------------------------- #


def test_html_sin_sesion_redirige_a_login(anonimo: TestClient) -> None:
    for ruta in ("/panel/tickets", "/panel/tickets/INC-2026-0001"):
        r = anonimo.get(ruta, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/panel/login"


def test_htmx_sin_sesion_recibe_hx_redirect(anonimo: TestClient) -> None:
    r = anonimo.get(
        "/panel/tickets", headers={"HX-Request": "true"}, follow_redirects=False
    )
    assert r.status_code == 401
    assert r.headers["HX-Redirect"] == "/panel/login"


def test_pagina_login_renderiza(anonimo: TestClient) -> None:
    r = anonimo.get("/panel/login")
    assert r.status_code == 200
    assert "Panel de agentes" in r.text
    assert 'name="password"' in r.text


def test_login_html_error_re_renderiza_con_mensaje(
    anonimo: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import auth as auth_api

    async def buscar(session: Any, correo: str) -> Any:
        return None

    monkeypatch.setattr(auth_api, "_buscar_staff", buscar)
    monkeypatch.setattr(auth_api, "RETARDO_LOGIN_FALLIDO_S", 0)
    r = anonimo.post(
        "/panel/login", data={"correo": "x@ctic.local", "password": "mala"}
    )
    assert r.status_code == 401
    assert "Credenciales inválidas." in r.text


def test_login_html_ok_setea_cookie_y_redirige(
    anonimo: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import auth as auth_api

    usuario = SimpleNamespace(
        id=7, nombre="Paul Barzola", correo="tecnico1@ctic.local", rol="tecnico", activo=True
    )

    async def autenticar(session: Any, correo: str, password: str) -> Any:
        return usuario

    monkeypatch.setattr(routes, "autenticar_staff", autenticar, raising=True)
    assert auth_api  # el import real sigue disponible para otros tests
    r = anonimo.post(
        "/panel/login",
        data={"correo": usuario.correo, "password": "secreta123"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/panel/tickets"
    assert "panel_token=" in r.headers["set-cookie"]
    assert "httponly" in r.headers["set-cookie"].lower()


def test_logout_html_borra_cookie_y_redirige(anonimo: TestClient) -> None:
    r = anonimo.get("/panel/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/panel/login"
    assert "panel_token=" in r.headers["set-cookie"].lower()


# --------------------------------------------------------------------------- #
# Rutas HTML — con sesión mockeada
# --------------------------------------------------------------------------- #


def test_listado_renderiza_con_sesion(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.get("/panel/tickets")
    assert r.status_code == 200
    assert "INC-2026-0001" in r.text
    assert "Juan Pérez" in r.text
    assert "Cerrar sesión (Paul Barzola)" in r.text


def test_listado_htmx_devuelve_solo_fragmento(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.get(
        "/panel/tickets?estado=Registrado&categoria=2", headers={"HX-Request": "true"}
    )
    assert r.status_code == 200
    assert "INC-2026-0001" in r.text
    assert "<html" not in r.text  # fragmento, no página completa
    assert ("listar", "Registrado", 2, None, 1, 20) in servicio.llamadas


def test_detalle_renderiza_historial_y_transiciones(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.get("/panel/tickets/INC-2026-0001")
    assert r.status_code == 200
    assert "No puedo acceder a mi correo institucional." in r.text
    assert "Ticket creado desde el chatbot." in r.text
    for estado in (
        "Registrado",
        "Asignado",
        "En Proceso",
        "Escalado",
        "Resuelto",
        "Cerrado",
    ):
        assert f'<option value="{estado}"' in r.text
    assert "Guardar cambios" in r.text


def test_post_estado_devuelve_fragmento_actualizado(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.post(
        "/panel/tickets/INC-2026-0001/estado",
        data={"estado": "Asignado", "comentario": "Se asigna a mesa de ayuda"},
    )
    assert r.status_code == 200
    assert (
        "cambiar_estado",
        "INC-2026-0001",
        "Asignado",
        STAFF.id,
        "Se asigna a mesa de ayuda",
    ) in servicio.llamadas
    assert "El estado se guardó como «Asignado»." in r.text


def test_post_estado_conflicto_muestra_error(
    autenticado: TestClient, servicio: ServicioFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def rechazar(session: Any, **kw: Any) -> Any:
        raise ConflictError("Transición de estado no permitida.")

    monkeypatch.setattr(servicio, "cambiar_estado", rechazar)
    r = autenticado.post(
        "/panel/tickets/INC-2026-0001/estado", data={"estado": "Cerrado"}
    )
    assert r.status_code == 200  # htmx no intercambia 4xx: banner en el fragmento
    assert "Transición de estado no permitida." in r.text


def test_post_asignar_devuelve_fragmento_con_tecnico(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.post(
        "/panel/tickets/INC-2026-0001/asignar", data={"tecnico_id": "7"}
    )
    assert r.status_code == 200
    assert ("asignar_tecnico", "INC-2026-0001", 7, STAFF.id) in servicio.llamadas
    assert "Paul Barzola" in r.text
    assert "Carlos Ramírez" not in r.text
    assert "María Torres" not in r.text
    assert "Lucía Torres" not in r.text


def test_detalle_muestra_seccion_respuesta_y_adjuntos(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.get("/panel/tickets/INC-2026-0001")
    assert r.status_code == 200
    assert "<h2>Respuesta</h2>" in r.text
    assert 'name="respuesta"' in r.text
    assert 'maxlength="1000"' in r.text
    assert "<h2>Archivo adjunto</h2>" in r.text
    assert "Esta incidencia no tiene archivos adjuntos." in r.text


def test_post_respuesta_guarda_texto(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.post(
        "/panel/tickets/INC-2026-0001/respuesta",
        data={"respuesta": "Se restableció el acceso al correo."},
    )
    assert r.status_code == 200
    assert (
        "guardar_respuesta",
        "INC-2026-0001",
        "Se restableció el acceso al correo.",
        STAFF.id,
    ) in servicio.llamadas
    assert "La respuesta se guardó correctamente." in r.text
    assert "Se restableció el acceso al correo." in r.text


def test_detalle_lista_adjunto_con_enlace_de_descarga(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    servicio.ticket.adjuntos = [
        SimpleNamespace(
            id=3,
            nombre_original="evidencia.png",
            mime_type="image/png",
            tamano_bytes=2048,
        )
    ]
    r = autenticado.get("/panel/tickets/INC-2026-0001")
    assert r.status_code == 200
    assert "evidencia.png" in r.text
    assert 'href="/panel/tickets/INC-2026-0001/adjuntos/3"' in r.text


def test_descargar_adjunto_devuelve_archivo(
    autenticado: TestClient,
    servicio: ServicioFalso,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archivo = tmp_path / "tickets" / "adj_abc.png"
    archivo.parent.mkdir()
    archivo.write_bytes(b"contenido-adjunto")
    servicio.ticket.adjuntos = [
        SimpleNamespace(
            id=3,
            nombre_original="evidencia.png",
            mime_type="image/png",
            tamano_bytes=len(b"contenido-adjunto"),
            ruta_almacenada=str(archivo),
        )
    ]
    from app.services import adjuntos as svc_adjuntos

    monkeypatch.setattr(
        svc_adjuntos, "get_settings", lambda: SimpleNamespace(UPLOADS_DIR=str(tmp_path))
    )
    r = autenticado.get("/panel/tickets/INC-2026-0001/adjuntos/3")
    assert r.status_code == 200
    assert r.content == b"contenido-adjunto"
    assert "evidencia.png" in r.headers.get("content-disposition", "")


# --------------------------------------------------------------------------- #
# Handoffs, base de conocimiento y métricas (semana 5, tareas 5.2/5.3/5.4)
#
# Estas páginas solo se SIRVEN desde ticket-service; sus datos vienen de
# chatbot-api vía fetch same-origin. Aquí solo comprobamos que el HTML se
# entrega según el rol y que el JS embebido apunta a los endpoints correctos.
# --------------------------------------------------------------------------- #


def test_handoffs_sin_sesion_redirige_a_login(anonimo: TestClient) -> None:
    r = anonimo.get("/panel/handoffs", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/panel/login"


def test_handoffs_renderiza_con_staff(autenticado: TestClient) -> None:
    r = autenticado.get("/panel/handoffs")
    assert r.status_code == 200
    assert "Handoffs" in r.text
    # El JS apunta a los endpoints de chatbot-api que se consumen same-origin.
    assert "/api/chat/handoffs" in r.text
    assert "/atender" in r.text
    assert "/mensajes" in r.text
    assert "/cerrar" in r.text
    # Enlace de navegación disponible para el staff.
    assert 'href="/panel/handoffs"' in r.text


def test_nav_no_muestra_enlaces_admin_a_tecnico(autenticado: TestClient) -> None:
    r = autenticado.get("/panel/handoffs")
    assert 'href="/panel/kb"' not in r.text
    assert 'href="/panel/metricas"' not in r.text


def test_nav_muestra_enlaces_admin(admin: TestClient) -> None:
    r = admin.get("/panel/handoffs")
    assert 'href="/panel/kb"' in r.text
    assert 'href="/panel/metricas"' in r.text


def test_kb_sin_sesion_redirige_a_login(anonimo: TestClient) -> None:
    r = anonimo.get("/panel/kb", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/panel/login"


def test_kb_tecnico_recibe_403(autenticado: TestClient) -> None:
    r = autenticado.get("/panel/kb")
    assert r.status_code == 403
    assert "solo para administradores" in r.text.lower()


def test_kb_admin_renderiza(admin: TestClient) -> None:
    r = admin.get("/panel/kb")
    assert r.status_code == 200
    assert "Base de conocimiento" in r.text
    assert "/api/kb/articulos" in r.text
    assert "/api/kb/reindex" in r.text


def test_metricas_sin_sesion_redirige_a_login(anonimo: TestClient) -> None:
    r = anonimo.get("/panel/metricas", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/panel/login"


def test_metricas_tecnico_recibe_403(autenticado: TestClient) -> None:
    r = autenticado.get("/panel/metricas")
    assert r.status_code == 403


def test_metricas_admin_renderiza(admin: TestClient) -> None:
    r = admin.get("/panel/metricas")
    assert r.status_code == 200
    assert "métricas" in r.text.lower()
    assert "/api/metricas/resumen" in r.text


# --------------------------------------------------------------------------- #
# API JSON del panel
# --------------------------------------------------------------------------- #


def test_api_listado_envelope(autenticado: TestClient, servicio: ServicioFalso) -> None:
    r = autenticado.get("/api/panel/tickets?estado=Registrado&page=1&size=10")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["items"][0] == {
        "ticketId": "INC-2026-0001",
        "estado": "Registrado",
        "prioridad": "Media",
        "categoria": "Correo Institucional",
        "solicitante": "Juan Pérez",
        "tecnico": None,
        "fechaRegistro": "2026-07-03T10:00:00",
    }


def test_api_detalle_incluye_historial(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.get("/api/panel/tickets/INC-2026-0001")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["descripcion"] == "No puedo acceder a mi correo institucional."
    assert data["historial"] == [
        {
            "estadoAnterior": None,
            "estadoNuevo": "Registrado",
            "comentario": "Ticket creado desde el chatbot.",
            "actor": None,
            "fecha": "2026-07-03T10:00:00",
        }
    ]


def test_api_patch_aplica_asignacion_y_estado(
    autenticado: TestClient, servicio: ServicioFalso
) -> None:
    r = autenticado.patch(
        "/api/panel/tickets/INC-2026-0001",
        json={"estado": "Asignado", "tecnicoId": 7, "comentario": "ok"},
    )
    assert r.status_code == 200
    assert servicio.llamadas == [
        ("asignar_tecnico", "INC-2026-0001", 7, STAFF.id),
        ("cambiar_estado", "INC-2026-0001", "Asignado", STAFF.id, "ok"),
    ]
    data = r.json()["data"]
    assert data["estado"] == "Asignado"
    assert data["tecnico"] == "Paul Barzola"


def test_api_patch_propaga_409_transicion_invalida(
    autenticado: TestClient, servicio: ServicioFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def rechazar(session: Any, **kw: Any) -> Any:
        raise ConflictError("Transición de estado no permitida.")

    monkeypatch.setattr(servicio, "cambiar_estado", rechazar)
    r = autenticado.patch(
        "/api/panel/tickets/INC-2026-0001", json={"estado": "Cerrado"}
    )
    assert r.status_code == 409
    cuerpo = r.json()
    assert cuerpo["success"] is False
    assert cuerpo["message"] == "Transición de estado no permitida."


def test_api_patch_sin_cambios_400(autenticado: TestClient, servicio: ServicioFalso) -> None:
    r = autenticado.patch(
        "/api/panel/tickets/INC-2026-0001", json={"comentario": "solo comentario"}
    )
    assert r.status_code == 400


def test_api_404_propagado(autenticado: TestClient, servicio: ServicioFalso) -> None:
    r = autenticado.get("/api/panel/tickets/INC-2026-9999")
    assert r.status_code == 404


def test_api_tecnicos(autenticado: TestClient, servicio: ServicioFalso) -> None:
    r = autenticado.get("/api/panel/tecnicos")
    assert r.status_code == 200
    nombres = [t["nombre"] for t in r.json()["data"]["items"]]
    assert nombres == ["Paul Barzola"]


# --------------------------------------------------------------------------- #
# Integración con el dominio real (solo si la tarea 2.4 ya está disponible)
# --------------------------------------------------------------------------- #


def test_matriz_transiciones_coincide_con_dominio() -> None:
    tickets = pytest.importorskip("app.services.tickets")
    matriz = getattr(tickets, "TRANSICIONES", None)
    if matriz is None:
        pytest.skip("El dominio no expone TRANSICIONES; se usa la copia local (TODO unificar).")
    del_panel = {estado: set(destinos) for estado, destinos in routes.TRANSICIONES_VALIDAS.items()}
    del_dominio = {str(estado): set(destinos) for estado, destinos in matriz.items()}
    assert del_dominio == del_panel
