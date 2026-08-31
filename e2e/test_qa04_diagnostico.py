"""QA-04 · Diagnóstico básico guiado (DRS §6, flujo F-05).

Criterio: hace preguntas relacionadas; las respuestas CAMBIAN según lo que
responde el usuario; cierra bien si se resuelve; ofrece registrar/escalar si no.
El árbol de diagnóstico es estático (no depende del LLM).
"""

import pytest

import helpers

pytestmark = pytest.mark.qa04


async def _iniciar_diagnostico_internet(cliente):
    chat = await helpers.crear_sesion(cliente)
    r = await chat.enviar(texto="no tengo internet")
    # Primer nodo: pregunta por el tipo de conexión (WiFi / cable).
    assert "wifi" in r.ids_opciones and "cable" in r.ids_opciones
    return chat, r


async def test_las_respuestas_cambian_segun_la_rama_elegida(cliente):
    """Dos ramas distintas del mismo nodo producen respuestas diferentes (QA-04)."""
    # Rama WiFi → nueva pregunta sobre la red «UNAC».
    chat_wifi, inicio = await _iniciar_diagnostico_internet(cliente)
    r_wifi = await chat_wifi.enviar(opcion=inicio.elegir("WiFi"))

    # Rama Cable → pasos de solución para conexión por cable + «¿Se resolvió?».
    chat_cable, inicio2 = await _iniciar_diagnostico_internet(cliente)
    r_cable = await chat_cable.enviar(opcion=inicio2.elegir("Cable"))

    assert r_wifi.texto != r_cable.texto, "Las ramas deberían divergir (QA-04)."
    assert "red" in helpers.normalizar(r_wifi.texto)  # pregunta por la red UNAC
    assert "cable" in helpers.normalizar(r_cable.texto)  # pasos para cable
    assert "resuelto_si" in r_cable.ids_opciones  # nodo de resolución «¿Se resolvió?»


async def test_rama_resuelta_cierra_feliz(cliente):
    """Si el usuario indica que se resolvió, el flujo cierra positivamente."""
    chat, inicio = await _iniciar_diagnostico_internet(cliente)
    r_cable = await chat.enviar(opcion=inicio.elegir("Cable"))
    cierre = await chat.enviar(opcion=r_cable.elegir("Sí, se resolvió"))
    assert "resolvió" in cierre.texto.lower() or "resuelto" in cierre.texto.lower()
    # Tras el cierre feliz se ofrece de nuevo el menú principal.
    assert "registrar_incidencia" in cierre.ids_opciones


async def test_rama_no_resuelta_ofrece_registrar_con_datos_prellenados(cliente):
    """No resuelto → registro F-02 pre-llenado (no repregunta categoría/descripción)."""
    chat, inicio = await _iniciar_diagnostico_internet(cliente)
    r_cable = await chat.enviar(opcion=inicio.elegir("Cable"))
    transicion = await chat.enviar(opcion=r_cable.elegir("No, el problema continúa"))

    # Ofrece registrar la incidencia y arranca F-02 (pide el nombre).
    assert "incidencia" in transicion.texto.lower()
    assert "nombre" in helpers.normalizar(transicion.texto)

    # Se completa identificación y área; el siguiente paso debe SALTAR categoría
    # y descripción (ya pre-llenadas por el diagnóstico) e ir a prioridad.
    await chat.enviar(texto="Usuario Diagnostico Prueba")
    r_area = await chat.enviar(texto=helpers.correo_unico())
    r_siguiente = await chat.enviar(opcion=r_area.elegir("Industrial"))

    texto_norm = helpers.normalizar(r_siguiente.texto)
    assert "prioridad" in texto_norm, (
        "Tras el área, con categoría y descripción pre-llenadas, el flujo debía "
        f"saltar a prioridad. Se obtuvo: {r_siguiente.texto!r}"
    )
    assert "prio_media" in r_siguiente.ids_opciones
