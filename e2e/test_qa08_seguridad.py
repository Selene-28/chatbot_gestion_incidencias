"""QA-08 · Seguridad (DRS §6, SEG-02/PRI-03).

Criterio: solo usuarios autorizados consultan sus incidencias; HTTPS extremo a
extremo; datos personales no visibles a terceros.

- (a) Consultar un ticket ajeno por API-02 con otro correo → 403 sin filtrar.
- (b) Endpoints protegidos (panel, kb, métricas) sin auth → 401.
- (c) Un técnico no puede escribir en KB ni ver métricas admin → 403.
- HTTPS: se verifica en el despliegue (nginx :443 + certs), no en esta suite;
  ver ``test_https_se_verifica_en_despliegue`` (skip documentado).
"""

import pytest

import helpers

pytestmark = pytest.mark.qa08


async def test_ticket_ajeno_por_api02_devuelve_403_sin_filtrar_datos(cliente):
    """(a) Consultar un ticket con un correo que no es el dueño → 403, sin datos."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    ticket_id = await helpers.recorrer_registro(chat, datos)

    resp = await helpers.consultar_ticket(
        cliente, ticket_id, correo=helpers.correo_unico("intruso")
    )
    assert resp.status_code == 403, resp.text
    cuerpo = resp.json()
    assert cuerpo["success"] is False
    # No se filtran datos del ticket ajeno en el cuerpo de la respuesta.
    crudo = resp.text
    assert datos["descripcion"] not in crudo
    assert datos["categoria"] not in crudo
    assert cuerpo.get("data") in (None, {}, [])


@pytest.mark.parametrize(
    "metodo,url",
    [
        ("GET", "/api/panel/tickets"),
        ("GET", "/api/kb/articulos"),
        ("GET", "/api/metricas/resumen?desde=2026-01-01&hasta=2026-12-31"),
    ],
)
async def test_endpoints_protegidos_sin_auth_devuelven_401(cliente, metodo, url):
    """(b) Panel, KB y métricas sin autenticación → 401."""
    resp = await helpers.peticion(cliente, metodo, url)
    assert resp.status_code == 401, f"{url} devolvió {resp.status_code}: {resp.text[:200]}"


async def test_tecnico_no_puede_escribir_en_kb(cliente_tecnico):
    """(c) Un técnico no puede crear artículos de KB (operación admin) → 403."""
    resp = await helpers.peticion(
        cliente_tecnico,
        "POST",
        "/api/kb/articulos",
        json={"titulo": "T", "contenido": "C", "categoria": "General"},
    )
    assert resp.status_code == 403, resp.text


async def test_tecnico_no_puede_ver_metricas_admin(cliente_tecnico):
    """(c) Un técnico no puede acceder a las métricas de administración → 403."""
    resp = await helpers.peticion(
        cliente_tecnico,
        "GET",
        "/api/metricas/resumen",
        params={"desde": "2026-01-01", "hasta": "2026-12-31"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.skip(
    reason="HTTPS extremo a extremo se verifica en el despliegue (nginx :443 + "
    "certificados TLS, prd/07). La suite corre contra el proxy en :80; el TLS lo "
    "termina el reverse proxy en producción y no forma parte de esta verificación."
)
async def test_https_se_verifica_en_despliegue():
    """QA-08 (HTTPS): documentado como responsabilidad del despliegue."""
