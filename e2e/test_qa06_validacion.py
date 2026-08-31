"""QA-06 · Validación de datos (DRS §6, LF-04).

Criterio: no permite registrar con obligatorios vacíos; verifica el formato del
correo institucional; re-solicita ante errores. Se comprueba por chat (F-02) y
contra el contrato directo API-01.
"""

import pytest

import helpers

pytestmark = pytest.mark.qa06


async def test_correo_no_institucional_es_rechazado_por_chat(cliente):
    """En F-02, un correo no institucional se rechaza y el bot re-solicita."""
    chat = await helpers.crear_sesion(cliente)
    await chat.enviar(opcion="registrar_incidencia")
    await chat.enviar(texto="Usuario Prueba Validacion")
    r = await chat.enviar(texto="juan@gmail.com")

    texto = helpers.normalizar(r.texto)
    assert "unac.edu.pe" in texto  # exige el dominio institucional
    # Sigue en el paso de correo: un correo válido ahora sí avanza (a escuela).
    r_ok = await chat.enviar(texto=helpers.correo_unico())
    assert "escuela" in helpers.normalizar(r_ok.texto)


async def test_campo_obligatorio_invalido_no_permite_avanzar(cliente):
    """Un obligatorio inválido (nombre demasiado corto) bloquea el avance."""
    chat = await helpers.crear_sesion(cliente)
    await chat.enviar(opcion="registrar_incidencia")
    r = await chat.enviar(texto="a")  # nombre inválido (< 3 caracteres)

    assert "nombre" in helpers.normalizar(r.texto)
    # No avanzó al correo: el bot vuelve a pedir el nombre; uno válido sí avanza.
    r_ok = await chat.enviar(texto="Usuario Valido Prueba")
    assert "correo" in helpers.normalizar(r_ok.texto)


async def test_descripcion_demasiado_corta_se_resolicita(cliente):
    """Una descripción por debajo del mínimo (10 chars) se vuelve a pedir."""
    datos = helpers.datos_incidencia()
    chat = await helpers.crear_sesion(cliente)
    await chat.enviar(opcion="registrar_incidencia")
    await chat.enviar(texto=datos["nombre"])
    r_area = await chat.enviar(texto=datos["correo"])
    r_cat = await chat.enviar(opcion=r_area.elegir(datos["area"]))
    await chat.enviar(opcion=r_cat.elegir(datos["categoria"]))
    r = await chat.enviar(texto="corta")  # < 10 caracteres

    assert "10" in r.texto and "2000" in r.texto  # recuerda los límites


async def test_api01_directo_rechaza_correo_invalido(cliente):
    """API-01 directo: correo no institucional → 400 con errors[].field=correo."""
    resp = await helpers.peticion(
        cliente,
        "POST",
        "/api/incidencias",
        headers=helpers.headers_api_key(),
        json={
            "nombre": "Usuario Prueba",
            "correo": "juan@gmail.com",
            "area": "Industrial",
            "categoria": "Correo Institucional",
            "descripcion": "Descripción de prueba con longitud suficiente.",
            "prioridad": "Media",
            "origen": "chatbot",
        },
    )
    assert resp.status_code == 400, resp.text
    cuerpo = resp.json()
    assert cuerpo["success"] is False
    campos = {e["field"] for e in cuerpo["errors"]}
    assert "correo" in campos


async def test_api01_directo_rechaza_obligatorio_faltante(cliente):
    """API-01 directo: sin correo (obligatorio) → 400 con field=correo."""
    resp = await helpers.peticion(
        cliente,
        "POST",
        "/api/incidencias",
        headers=helpers.headers_api_key(),
        json={
            "nombre": "Usuario Prueba",
            "area": "Industrial",
            "categoria": "Correo Institucional",
            "descripcion": "Descripción de prueba con longitud suficiente.",
            "prioridad": "Media",
        },
    )
    assert resp.status_code == 400, resp.text
    campos = {e["field"] for e in resp.json()["errors"]}
    assert "correo" in campos
