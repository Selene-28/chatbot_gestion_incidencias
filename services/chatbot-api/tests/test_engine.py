"""Transiciones del motor genérico de flujos (con conversación fake, sin BD)."""

from typing import Any

import pytest

from app.dialogo.engine import Deps, Engine, FallbackDeFlujo, Resultado, contexto_de
from app.dialogo.tipos import Entrada, texto_plano
from app.models import Conversacion


class FlujoDemo:
    """Flujo de dos pasos: a (valida texto 'ok') → b (cualquier cosa termina)."""

    nombre = "demo"

    async def iniciar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        return Resultado(mensajes=[texto_plano("dame a")], paso="a")

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        if paso == "a":
            if entrada.texto == "ok":
                ctx["datos"]["a"] = entrada.texto
                return Resultado(mensajes=[texto_plano("dame b")], paso="b")
            return Resultado(mensajes=[texto_plano("inválido, dame a")], invalida=True)
        if paso == "b":
            ctx["sesion"]["hecho"] = True
            return Resultado(mensajes=[texto_plano("fin")], terminar=True)
        raise AssertionError(f"paso inesperado: {paso}")


@pytest.fixture()
def conv() -> Conversacion:
    return Conversacion(codigo="test-conv")


@pytest.fixture()
def engine() -> Engine:
    return Engine([FlujoDemo()])


DEPS = Deps(session=None, tickets=None)  # type: ignore[arg-type]


async def test_iniciar_activa_flujo_y_persiste_estado(engine: Engine, conv: Conversacion):
    mensajes = await engine.iniciar(conv, "demo", DEPS)
    assert [m.texto for m in mensajes] == ["dame a"]
    assert conv.flujo_activo == "demo"
    assert conv.flujo_contexto["paso"] == "a"


async def test_entrada_valida_avanza_de_paso(engine: Engine, conv: Conversacion):
    await engine.iniciar(conv, "demo", DEPS)
    mensajes = await engine.procesar(conv, Entrada(texto="ok"), DEPS)
    assert [m.texto for m in mensajes] == ["dame b"]
    assert conv.flujo_contexto["paso"] == "b"
    assert conv.flujo_contexto["datos"]["a"] == "ok"
    assert conv.flujo_contexto["intentos"] == 0


async def test_terminar_limpia_flujo_pero_preserva_sesion(engine: Engine, conv: Conversacion):
    await engine.iniciar(conv, "demo", DEPS)
    await engine.procesar(conv, Entrada(texto="ok"), DEPS)
    mensajes = await engine.procesar(conv, Entrada(texto="lo que sea"), DEPS)
    assert [m.texto for m in mensajes] == ["fin"]
    assert conv.flujo_activo is None
    assert conv.flujo_contexto["datos"] == {}
    assert conv.flujo_contexto["sesion"] == {"hecho": True}


async def test_entrada_invalida_resolicita_e_incrementa(engine: Engine, conv: Conversacion):
    await engine.iniciar(conv, "demo", DEPS)
    mensajes = await engine.procesar(conv, Entrada(texto="nop"), DEPS)
    assert "inválido" in mensajes[0].texto
    assert conv.flujo_contexto["intentos"] == 1
    assert conv.flujo_contexto["paso"] == "a"  # sigue en el mismo paso


async def test_tercer_intento_invalido_abandona_y_dispara_fallback(
    engine: Engine, conv: Conversacion
):
    await engine.iniciar(conv, "demo", DEPS)
    await engine.procesar(conv, Entrada(texto="nop"), DEPS)
    await engine.procesar(conv, Entrada(texto="nop"), DEPS)
    with pytest.raises(FallbackDeFlujo):
        await engine.procesar(conv, Entrada(texto="nop"), DEPS)
    assert conv.flujo_activo is None  # flujo abandonado


async def test_entrada_valida_reinicia_contador_de_intentos(
    engine: Engine, conv: Conversacion
):
    await engine.iniciar(conv, "demo", DEPS)
    await engine.procesar(conv, Entrada(texto="nop"), DEPS)
    await engine.procesar(conv, Entrada(texto="nop"), DEPS)
    await engine.procesar(conv, Entrada(texto="ok"), DEPS)
    assert conv.flujo_contexto["intentos"] == 0


async def test_estado_sobrevive_reinicio_del_motor(engine: Engine, conv: Conversacion):
    """Criterio 3.2: un Engine nuevo continúa el flujo desde el estado en BD."""
    await engine.iniciar(conv, "demo", DEPS)
    # 'reinicio': instancia nueva del motor; el estado vive en la conversación
    motor_nuevo = Engine([FlujoDemo()])
    mensajes = await motor_nuevo.procesar(conv, Entrada(texto="ok"), DEPS)
    assert [m.texto for m in mensajes] == ["dame b"]
    assert conv.flujo_contexto["paso"] == "b"


async def test_cancelar_descarta_datos_y_preserva_sesion(engine: Engine, conv: Conversacion):
    conv.flujo_contexto = {"paso": "a", "datos": {"x": 1}, "intentos": 2, "sesion": {"k": "v"}}
    conv.flujo_activo = "demo"
    engine.cancelar(conv)
    assert conv.flujo_activo is None
    ctx = contexto_de(conv)
    assert ctx["datos"] == {}
    assert ctx["sesion"] == {"k": "v"}


async def test_procesar_sin_flujo_activo_lanza_fallback(engine: Engine, conv: Conversacion):
    with pytest.raises(FallbackDeFlujo):
        await engine.procesar(conv, Entrada(texto="hola"), DEPS)
