"""Panel de agentes server-rendered: Jinja2 + htmx, sin build step (RF-11).

Seguridad:
- Autenticación por cookie HttpOnly ``panel_token`` (app.core.deps); sin
  sesión válida las rutas redirigen 303 a /panel/login (o HX-Redirect si la
  petición viene de htmx, para que el navegador haga la navegación completa).
- El autoescapado de Jinja2 está activo por defecto para plantillas .html
  (anti-XSS): todo dato del usuario se escapa al renderizar.
- Mitigación CSRF: la cookie es SameSite=Lax, por lo que el navegador NO la
  adjunta en POST cross-site; los formularios del panel son mismo-origen
  (prd/02 §7).
"""

import math
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import autenticar_staff
from app.core.db import get_session
from app.core.deps import LOGIN_URL, clear_panel_cookie, set_panel_cookie, staff_opcional
from app.core.errors import AppError, UnauthorizedError
from app.core.security import create_access_token
from app.panel import consultas

# Matriz de transiciones RN-02 (prd/01 RN-02, prd/02 §6).
# Orden canónico de los estados para los <select> del panel.
_ORDEN_ESTADOS = ["Registrado", "Asignado", "En Proceso", "Escalado", "Resuelto", "Cerrado"]

try:
    # Fuente de verdad: la matriz del dominio (app.services.tickets, tarea 2.4),
    # convertida a listas ordenadas para renderizar los selects.
    from app.services.tickets import TRANSICIONES as _MATRIZ_DOMINIO

    TRANSICIONES_VALIDAS: dict[str, list[str]] = {
        str(estado): [e for e in _ORDEN_ESTADOS if e in destinos]
        for estado, destinos in _MATRIZ_DOMINIO.items()
    }
except (ImportError, AttributeError):  # pragma: no cover - solo si falta el dominio
    # TODO unificar con dominio: copia local mientras la tarea 2.4 (en
    # paralelo) no esté disponible en este árbol de trabajo.
    TRANSICIONES_VALIDAS = {
        "Registrado": ["Asignado", "Escalado"],
        "Asignado": ["En Proceso", "Escalado"],
        "En Proceso": ["Escalado", "Resuelto"],
        "Escalado": ["En Proceso"],
        "Resuelto": ["En Proceso", "Cerrado"],
        "Cerrado": [],
    }

ESTADOS = list(TRANSICIONES_VALIDAS)

router = APIRouter(prefix="/panel", tags=["panel-html"], include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

SessionDep = Annotated[AsyncSession, Depends(get_session)]
StaffDep = Annotated[Any, Depends(staff_opcional)]


def _servicio_tickets() -> Any:
    """Módulo de servicios de dominio (import diferido; tarea 2.4 en paralelo)."""
    from app.services import tickets

    return tickets


def _redirigir_login(request: Request) -> Response:
    """Respuesta «sin sesión» apta para navegador: 303 (o HX-Redirect en htmx)."""
    if request.headers.get("HX-Request"):
        # htmx: el header fuerza una navegación completa del navegador al login.
        return Response(status_code=401, headers={"HX-Redirect": LOGIN_URL})
    return RedirectResponse(LOGIN_URL, status_code=303)


def _a_entero(valor: str | None) -> int | None:
    """Convierte parámetros de formulario/select ('' → None) con tolerancia."""
    if valor is None or not valor.strip():
        return None
    try:
        return int(valor)
    except ValueError:
        return None


def _filtros_qs(estado: str, categoria: int | None, tecnico: int | None, size: int) -> str:
    """Querystring de los filtros vigentes, para los enlaces de paginación."""
    pares = {"estado": estado, "categoria": categoria, "tecnico": tecnico, "size": size}
    return urlencode({k: v for k, v in pares.items() if v not in (None, "")})


# --------------------------------------------------------------------------- #
# Sesión (login / logout)
# --------------------------------------------------------------------------- #


@router.get("")
@router.get("/")
async def raiz_panel() -> Response:
    """Entrada al panel: redirige al listado (que exige sesión y manda al login)."""
    return RedirectResponse("/panel/tickets", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def pagina_login(request: Request) -> Response:
    """Formulario de inicio de sesión del panel."""
    return templates.TemplateResponse(request, "login.html", {"error": None, "staff": None})


@router.post("/login", response_class=HTMLResponse)
async def enviar_login(
    request: Request,
    session: SessionDep,
    correo: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    """Valida credenciales; en éxito setea la cookie y redirige al listado."""
    try:
        usuario = await autenticar_staff(session, correo.strip(), password)
    except UnauthorizedError as exc:
        contexto = {"error": exc.message, "staff": None, "correo": correo}
        return templates.TemplateResponse(request, "login.html", contexto, status_code=401)
    token = create_access_token(str(usuario.id), usuario.rol)
    respuesta = RedirectResponse("/panel/tickets", status_code=303)
    set_panel_cookie(respuesta, token)
    return respuesta


@router.get("/logout")
async def cerrar_sesion() -> Response:
    """Elimina la cookie del panel y vuelve al login."""
    respuesta = RedirectResponse(LOGIN_URL, status_code=303)
    clear_panel_cookie(respuesta)
    return respuesta


# --------------------------------------------------------------------------- #
# Listado de tickets
# --------------------------------------------------------------------------- #


@router.get("/tickets", response_class=HTMLResponse)
async def pagina_tickets(
    request: Request,
    session: SessionDep,
    staff: StaffDep,
    estado: str | None = None,
    categoria: str | None = None,
    tecnico: str | None = None,
    page: int = 1,
    size: int = 20,
) -> Response:
    """Listado con filtros; si la petición viene de htmx devuelve solo la tabla."""
    if staff is None:
        return _redirigir_login(request)
    estado = (estado or "").strip()
    categoria_id = _a_entero(categoria)
    tecnico_id = _a_entero(tecnico)
    page = max(1, page)
    size = min(max(1, size), 100)
    items, total = await _servicio_tickets().listar_tickets(
        session,
        estado=estado or None,
        categoria_id=categoria_id,
        tecnico_id=tecnico_id,
        page=page,
        size=size,
    )
    contexto = {
        "staff": staff,
        "tickets": items,
        "total": total,
        "page": page,
        "size": size,
        "paginas": max(1, math.ceil(total / size)),
        "estado": estado,
        "categoria": categoria_id,
        "tecnico": tecnico_id,
        "estados": ESTADOS,
        "categorias": await consultas.listar_categorias(session),
        "tecnicos": await consultas.listar_tecnicos(session),
        "filtros_qs": _filtros_qs(estado, categoria_id, tecnico_id, size),
    }
    plantilla = "_tabla_tickets.html" if request.headers.get("HX-Request") else "tickets.html"
    return templates.TemplateResponse(request, plantilla, contexto)


# --------------------------------------------------------------------------- #
# Detalle de ticket y acciones (cambiar estado, asignar técnico)
# --------------------------------------------------------------------------- #


async def _contexto_detalle(
    session: AsyncSession,
    staff: Any,
    ticket: Any,
    error: str | None = None,
    mensaje: str | None = None,
) -> dict[str, Any]:
    """Contexto común de la vista de detalle y sus fragmentos htmx."""
    return {
        "staff": staff,
        "ticket": ticket,
        "estados": _ORDEN_ESTADOS,
        "transiciones": _ORDEN_ESTADOS,
        "tecnicos": await consultas.listar_tecnicos(session),
        "error": error,
        "mensaje": mensaje,
    }


@router.get("/tickets/{codigo}", response_class=HTMLResponse)
async def pagina_detalle(
    request: Request, session: SessionDep, staff: StaffDep, codigo: str
) -> Response:
    """Detalle del ticket: datos, historial y formularios de acción."""
    if staff is None:
        return _redirigir_login(request)
    ticket = await _servicio_tickets().obtener_ticket(session, codigo)
    contexto = await _contexto_detalle(session, staff, ticket)
    return templates.TemplateResponse(request, "ticket_detalle.html", contexto)


@router.post("/tickets/{codigo}/estado", response_class=HTMLResponse)
async def form_cambiar_estado(
    request: Request,
    session: SessionDep,
    staff: StaffDep,
    codigo: str,
    estado: Annotated[str, Form()],
    comentario: Annotated[str, Form()] = "",
) -> Response:
    """Aplica una transición de estado y devuelve el fragmento actualizado."""
    if staff is None:
        return _redirigir_login(request)
    servicio = _servicio_tickets()
    error = mensaje = None
    try:
        ticket = await servicio.cambiar_estado(
            session,
            codigo=codigo,
            nuevo_estado=estado,
            actor_id=staff.id,
            comentario=comentario.strip() or None,
            libre=True,
        )
        mensaje = f"El estado se guardó como «{estado}»."
    except AppError as exc:
        # htmx no intercambia contenido en respuestas 4xx: devolvemos 200 con
        # un banner de error y el estado real (sin cambios) del ticket.
        error = exc.message
        ticket = await servicio.obtener_ticket(session, codigo)
    contexto = await _contexto_detalle(session, staff, ticket, error, mensaje)
    return templates.TemplateResponse(request, "_detalle.html", contexto)


@router.post("/tickets/{codigo}/respuesta", response_class=HTMLResponse)
async def form_guardar_respuesta(
    request: Request,
    session: SessionDep,
    staff: StaffDep,
    codigo: str,
    respuesta: Annotated[str, Form()] = "",
) -> Response:
    """Guarda la respuesta del técnico (máx. 1000 caracteres) y refresca el detalle."""
    if staff is None:
        return _redirigir_login(request)
    servicio = _servicio_tickets()
    error = mensaje = None
    try:
        ticket = await servicio.guardar_respuesta(
            session, codigo=codigo, texto=respuesta, actor_id=staff.id
        )
        mensaje = "La respuesta se guardó correctamente."
    except AppError as exc:
        error = exc.message
        ticket = await servicio.obtener_ticket(session, codigo)
    contexto = await _contexto_detalle(session, staff, ticket, error, mensaje)
    return templates.TemplateResponse(request, "_detalle.html", contexto)


@router.get("/tickets/{codigo}/adjuntos/{adjunto_id}")
async def descargar_adjunto(
    request: Request,
    session: SessionDep,
    staff: StaffDep,
    codigo: str,
    adjunto_id: int,
) -> Response:
    """Descarga un adjunto del ticket (solo staff autenticado, RF-13)."""
    if staff is None:
        return _redirigir_login(request)  # request se usa para HX-Redirect / 303
    from app.services.adjuntos import ruta_adjunto_segura

    servicio = _servicio_tickets()
    adjunto = await servicio.obtener_adjunto(session, codigo=codigo, adjunto_id=adjunto_id)
    ruta = ruta_adjunto_segura(adjunto)
    return FileResponse(
        path=str(ruta),
        filename=adjunto.nombre_original,
        media_type=adjunto.mime_type,
    )


# --------------------------------------------------------------------------- #
# Handoffs, base de conocimiento y métricas (semana 5, tareas 5.2/5.3/5.4)
#
# Estas rutas solo SIRVEN el HTML del panel; los datos se obtienen en el
# navegador vía fetch same-origin a chatbot-api (/api/chat/*, /api/kb/*,
# /api/metricas/*). La cookie HttpOnly ``panel_token`` (SameSite=Lax) viaja
# automáticamente en esas peticiones porque todo pasa por el mismo origen
# (nginx :80); chatbot-api la valida con el JWT_SECRET compartido. Por eso el
# backend de ticket-service NO reenvía peticiones servidor-a-servidor aquí.
# --------------------------------------------------------------------------- #


@router.get("/handoffs", response_class=HTMLResponse)
async def pagina_handoffs(request: Request, staff: StaffDep) -> Response:
    """Cola de handoffs y chat agente↔usuario (require_staff)."""
    if staff is None:
        return _redirigir_login(request)
    return templates.TemplateResponse(request, "handoffs.html", {"staff": staff})


@router.get("/kb", response_class=HTMLResponse)
async def pagina_kb(request: Request, staff: StaffDep) -> Response:
    """Administración de la base de conocimiento (solo admin)."""
    if staff is None:
        return _redirigir_login(request)
    if staff.rol != "admin":
        return templates.TemplateResponse(
            request, "solo_admin.html", {"staff": staff}, status_code=403
        )
    return templates.TemplateResponse(request, "kb.html", {"staff": staff})


@router.get("/metricas", response_class=HTMLResponse)
async def pagina_metricas(request: Request, staff: StaffDep) -> Response:
    """Dashboard de métricas del chatbot (solo admin)."""
    if staff is None:
        return _redirigir_login(request)
    if staff.rol != "admin":
        return templates.TemplateResponse(
            request, "solo_admin.html", {"staff": staff}, status_code=403
        )
    return templates.TemplateResponse(request, "metricas.html", {"staff": staff})


@router.post("/tickets/{codigo}/asignar", response_class=HTMLResponse)
async def form_asignar_tecnico(
    request: Request,
    session: SessionDep,
    staff: StaffDep,
    codigo: str,
    tecnico_id: Annotated[str, Form()] = "",
) -> Response:
    """Asigna un técnico al ticket y devuelve el fragmento actualizado."""
    if staff is None:
        return _redirigir_login(request)
    servicio = _servicio_tickets()
    error = mensaje = None
    tecnico = _a_entero(tecnico_id)
    if tecnico is None:
        ticket = await servicio.obtener_ticket(session, codigo)
        contexto = await _contexto_detalle(
            session, staff, ticket, error="Seleccione un técnico válido."
        )
        return templates.TemplateResponse(request, "_detalle.html", contexto)
    try:
        ticket = await servicio.asignar_tecnico(
            session, codigo=codigo, tecnico_id=tecnico, actor_id=staff.id
        )
        mensaje = "Técnico asignado correctamente."
    except AppError as exc:
        error = exc.message
        ticket = await servicio.obtener_ticket(session, codigo)
    contexto = await _contexto_detalle(session, staff, ticket, error, mensaje)
    return templates.TemplateResponse(request, "_detalle.html", contexto)
