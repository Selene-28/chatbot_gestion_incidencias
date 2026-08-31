"""Pruebas de integración de los endpoints REST (contratos EXACTOS de prd/04 §3).

Usan httpx AsyncClient + ASGITransport sobre una app de prueba que monta los
routers del dominio, contra MySQL real (tickets_test).
"""

import uuid

import pytest

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

CUERPO_VALIDO = {
    "nombre": "Juan Pérez",
    "correo": "",  # se completa por prueba
    "area": "Industrial",
    "categoria": "Correo Institucional",
    "subcategoria": "Recuperación de contraseña",
    "descripcion": "No puedo acceder a mi correo institucional.",
    "prioridad": "Media",
    "origen": "chatbot",
}


def _cuerpo(**extra) -> dict:
    datos = {**CUERPO_VALIDO, "correo": f"api{uuid.uuid4().hex[:10]}@unac.edu.pe"}
    datos.update(extra)
    return datos


# --- API-01: POST /api/incidencias ---


async def test_api01_registrar_incidencia(api_client) -> None:
    respuesta = await api_client.post("/api/incidencias", json=_cuerpo())
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["code"] == 201
    assert cuerpo["message"] == "La incidencia fue registrada correctamente."
    assert cuerpo["data"]["estado"] == "Registrado"
    assert cuerpo["data"]["ticketId"].startswith("INC-")


async def test_api01_idempotency_key(api_client) -> None:
    datos = _cuerpo()
    clave = str(uuid.uuid4())
    r1 = await api_client.post(
        "/api/incidencias", json=datos, headers={"Idempotency-Key": clave}
    )
    r2 = await api_client.post(
        "/api/incidencias", json=datos, headers={"Idempotency-Key": clave}
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["data"]["ticketId"] == r2.json()["data"]["ticketId"]


async def test_api01_validacion_400_con_envelope(api_client) -> None:
    respuesta = await api_client.post("/api/incidencias", json=_cuerpo(correo="a@gmail.com"))
    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert cuerpo["code"] == 400
    assert cuerpo["message"] == "Los datos enviados son inválidos."
    assert any(e["field"] == "correo" for e in cuerpo["errors"])


async def test_api01_sin_api_key_401(api_client) -> None:
    respuesta = await api_client.post(
        "/api/incidencias", json=_cuerpo(), headers={"X-Api-Key": "incorrecta"}
    )
    assert respuesta.status_code == 401
    assert respuesta.json()["success"] is False


# --- API-01b: POST /api/incidencias/adjuntos ---


async def test_api01b_subir_adjunto_y_asociarlo(api_client) -> None:
    subida = await api_client.post(
        "/api/incidencias/adjuntos",
        files={"file": ("evidencia.png", PNG, "image/png")},
    )
    assert subida.status_code == 201
    adjunto_id = subida.json()["data"]["adjuntoId"]
    assert adjunto_id.startswith("adj_") and len(adjunto_id) == 12

    registro = await api_client.post("/api/incidencias", json=_cuerpo(adjuntoId=adjunto_id))
    assert registro.status_code == 201


async def test_api01b_rechaza_tipo_por_firma(api_client) -> None:
    # Extensión .png pero contenido de texto: se valida el MIME real (RF-13)
    respuesta = await api_client.post(
        "/api/incidencias/adjuntos",
        files={"file": ("falso.png", b"no soy una imagen", "image/png")},
    )
    assert respuesta.status_code == 400
    assert any("JPG" in e["description"] for e in respuesta.json()["errors"])


async def test_api01b_rechaza_mayor_a_5mb(api_client) -> None:
    grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024)
    respuesta = await api_client.post(
        "/api/incidencias/adjuntos", files={"file": ("grande.png", grande, "image/png")}
    )
    assert respuesta.status_code == 400


async def test_api01_adjunto_inexistente_400(api_client) -> None:
    respuesta = await api_client.post(
        "/api/incidencias", json=_cuerpo(adjuntoId="adj_ffffffff")
    )
    assert respuesta.status_code == 400


# --- API-02: GET /api/incidencias/{ticketId} y GET /api/incidencias?correo= ---


async def test_api02_consultar_estado_campos_exactos(api_client) -> None:
    datos = _cuerpo()
    ticket_id = (await api_client.post("/api/incidencias", json=datos)).json()["data"]["ticketId"]

    respuesta = await api_client.get(
        f"/api/incidencias/{ticket_id}", params={"correo": datos["correo"]}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["message"] == "OK"
    data = cuerpo["data"]
    # Campos EXACTOS de prd/04 §3 (API-02)
    assert set(data) == {
        "ticketId",
        "estado",
        "categoria",
        "fechaRegistro",
        "tecnico",
        "ultimaActualizacion",
        "observaciones",
        "respuesta",
    }
    assert data["respuesta"] is None
    assert data["ticketId"] == ticket_id
    assert data["estado"] == "Registrado"
    assert data["categoria"] == "Correo Institucional"
    assert data["tecnico"] is None
    assert "T" in data["fechaRegistro"]  # ISO 8601
    assert isinstance(data["observaciones"], str) and data["observaciones"]


async def test_api02_correo_ajeno_403_sin_datos(api_client) -> None:
    datos = _cuerpo()
    ticket_id = (await api_client.post("/api/incidencias", json=datos)).json()["data"]["ticketId"]

    respuesta = await api_client.get(
        f"/api/incidencias/{ticket_id}", params={"correo": "otro@unac.edu.pe"}
    )
    assert respuesta.status_code == 403
    cuerpo = respuesta.json()
    assert cuerpo["success"] is False
    assert "data" not in cuerpo  # RN-03: sin filtrar datos del ticket


async def test_api02_ticket_inexistente_404(api_client) -> None:
    respuesta = await api_client.get(
        "/api/incidencias/INC-1999-9999", params={"correo": "alguien@unac.edu.pe"}
    )
    assert respuesta.status_code == 404


async def test_api02_lista_por_correo(api_client) -> None:
    datos = _cuerpo()
    await api_client.post("/api/incidencias", json=datos)
    await api_client.post("/api/incidencias", json={**datos, "descripcion": "Sigue sin funcionar."})

    respuesta = await api_client.get("/api/incidencias", params={"correo": datos["correo"]})
    assert respuesta.status_code == 200
    data = respuesta.json()["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert all(item["ticketId"].startswith("INC-") for item in data["items"])


async def test_api02_correo_invalido_400(api_client) -> None:
    respuesta = await api_client.get("/api/incidencias", params={"correo": "a@gmail.com"})
    assert respuesta.status_code == 400


# --- API-03: PUT /api/incidencias/escalar ---


async def test_api03_escalar(api_client) -> None:
    datos = _cuerpo()
    ticket_id = (await api_client.post("/api/incidencias", json=datos)).json()["data"]["ticketId"]

    respuesta = await api_client.put(
        "/api/incidencias/escalar",
        json={
            "ticketId": ticket_id,
            "motivo": "No fue posible resolver mediante el chatbot.",
            "correo": datos["correo"],
        },
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["message"] == "La incidencia fue derivada al personal técnico."
    assert cuerpo["data"] == {"estado": "Escalado"}

    # El motivo queda como observación (último comentario del historial)
    consulta = await api_client.get(
        f"/api/incidencias/{ticket_id}", params={"correo": datos["correo"]}
    )
    assert consulta.json()["data"]["observaciones"] == (
        "No fue posible resolver mediante el chatbot."
    )


async def test_api03_escalar_repetido_409(api_client) -> None:
    datos = _cuerpo()
    ticket_id = (await api_client.post("/api/incidencias", json=datos)).json()["data"]["ticketId"]
    cuerpo = {"ticketId": ticket_id, "motivo": "Motivo válido.", "correo": datos["correo"]}
    assert (await api_client.put("/api/incidencias/escalar", json=cuerpo)).status_code == 200
    respuesta = await api_client.put("/api/incidencias/escalar", json=cuerpo)
    assert respuesta.status_code == 409
    assert respuesta.json()["success"] is False


async def test_api03_escalar_correo_ajeno_403(api_client) -> None:
    datos = _cuerpo()
    ticket_id = (await api_client.post("/api/incidencias", json=datos)).json()["data"]["ticketId"]
    respuesta = await api_client.put(
        "/api/incidencias/escalar",
        json={"ticketId": ticket_id, "motivo": "Motivo válido.", "correo": "otro@unac.edu.pe"},
    )
    assert respuesta.status_code == 403


# --- API-06: POST /api/encuesta ---


async def test_api06_encuesta_valida(api_client) -> None:
    datos = _cuerpo()
    ticket_id = (await api_client.post("/api/incidencias", json=datos)).json()["data"]["ticketId"]

    respuesta = await api_client.post(
        "/api/encuesta",
        json={
            "ticketId": ticket_id,
            "conversacionCodigo": None,
            "calificacion": 5,
            "comentario": "La atención fue rápida y clara.",
        },
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["message"] == "Gracias por valorar nuestro servicio."
    assert cuerpo["data"] == {}


async def test_api06_encuesta_duplicada_409(api_client) -> None:
    datos = _cuerpo()
    ticket_id = (await api_client.post("/api/incidencias", json=datos)).json()["data"]["ticketId"]
    cuerpo = {"ticketId": ticket_id, "calificacion": 4}
    assert (await api_client.post("/api/encuesta", json=cuerpo)).status_code == 201
    assert (await api_client.post("/api/encuesta", json=cuerpo)).status_code == 409


@pytest.mark.parametrize("calificacion", [0, 6])
async def test_api06_calificacion_fuera_de_rango_400(api_client, calificacion: int) -> None:
    respuesta = await api_client.post(
        "/api/encuesta", json={"conversacionCodigo": "conv-1", "calificacion": calificacion}
    )
    assert respuesta.status_code == 400
    assert any("entre 1 y 5" in e["description"] for e in respuesta.json()["errors"])


async def test_api06_sin_referencia_400(api_client) -> None:
    respuesta = await api_client.post("/api/encuesta", json={"calificacion": 3})
    assert respuesta.status_code == 400
