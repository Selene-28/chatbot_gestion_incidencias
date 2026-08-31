"""Integración (MySQL + Chroma temporal): CRUD de la base de conocimiento (RF-12).

Verifica el ciclo crear/leer/editar/desactivar/reindexar, los permisos (staff vs
admin) y que el artículo creado queda indexado en el motor semántico (embedder
determinista de tests).
"""

import pytest
from sqlalchemy import text as sql_text

from app.ia import indexado
from tests.conftest import token_staff

pytestmark = pytest.mark.integration

STAFF = {"panel_token": token_staff("tecnico", sub=9)}
ADMIN = {"panel_token": token_staff("admin", sub=1)}

ARTICULO = {
    "titulo": "Cómo conectar el WiFi eduroam",
    "contenido": "Para conectarte a la red wifi eduroam usa tu correo y contraseña.",
    "categoria": "Internet/WiFi",
    "etiquetas": ["wifi", "red", "eduroam"],
}


async def test_kb_crud_e_indexado(api_client, sesion, chroma_tmp, fake_embedder):
    # crear (admin) → 201 e indexado
    r = await api_client.post("/api/kb/articulos", json=ARTICULO, cookies=ADMIN)
    assert r.status_code == 201, r.text
    art_id = r.json()["data"]["id"]

    chunks = indexado.get_coleccion().get(where={"articulo_id": art_id})
    assert chunks["ids"], "el artículo creado debe quedar indexado (RF-12)"

    # listar (staff) → aparece con la forma de resumen
    r = await api_client.get("/api/kb/articulos?q=eduroam", cookies=STAFF)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    encontrado = next(a for a in items if a["id"] == art_id)
    assert encontrado["version"] == 1
    assert encontrado["etiquetas"] == ["wifi", "red", "eduroam"]
    assert "contenido" not in encontrado

    # detalle (staff) → incluye contenido
    r = await api_client.get(f"/api/kb/articulos/{art_id}", cookies=STAFF)
    assert r.json()["data"]["contenido"] == ARTICULO["contenido"]

    # editar (admin) → version+1 y re-indexado
    cambios = {**ARTICULO, "titulo": "Conexión eduroam (actualizado)"}
    r = await api_client.put(f"/api/kb/articulos/{art_id}", json=cambios, cookies=ADMIN)
    assert r.status_code == 200
    assert r.json()["data"]["version"] == 2

    # desactivar (admin) → baja lógica + retiro del índice
    r = await api_client.delete(f"/api/kb/articulos/{art_id}", cookies=ADMIN)
    assert r.status_code == 200 and r.json()["data"]["ok"] is True
    assert not indexado.get_coleccion().get(where={"articulo_id": art_id})["ids"]

    activo = (
        await sesion.execute(
            sql_text("SELECT activo FROM kb_articulos WHERE id = :i"), {"i": art_id}
        )
    ).scalar_one()
    assert activo == 0

    # reindex (admin) → reconstruye desde MySQL (idempotente)
    r = await api_client.post("/api/kb/reindex", cookies=ADMIN)
    assert r.status_code == 200
    assert isinstance(r.json()["data"]["indexados"], int)


async def test_kb_permisos(api_client, chroma_tmp, fake_embedder):
    # sin cookie → 401
    r = await api_client.post("/api/kb/articulos", json=ARTICULO)
    assert r.status_code == 401
    # staff no-admin → 403 en escritura
    r = await api_client.post("/api/kb/articulos", json=ARTICULO, cookies=STAFF)
    assert r.status_code == 403
    # lectura permitida a cualquier staff
    r = await api_client.get("/api/kb/articulos", cookies=STAFF)
    assert r.status_code == 200


async def test_kb_validacion_titulo_vacio(api_client):
    r = await api_client.post(
        "/api/kb/articulos",
        json={"titulo": "", "contenido": "x", "categoria": "c", "etiquetas": []},
        cookies=ADMIN,
    )
    assert r.status_code == 400
