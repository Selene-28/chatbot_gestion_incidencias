"""app/ia/llm.py con cliente mockeado: structured outputs, streaming y breaker."""

import time
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.core.config import get_settings
from app.ia import llm

ESQUEMA_INTENT = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "confianza": {"type": "number"},
    },
    "required": ["intent", "confianza"],
    "additionalProperties": False,
}


def _error_conexion() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )


class _StreamFake:
    """Context manager async que imita client.messages.stream(...)."""

    def __init__(self, fragmentos: list[str], error: Exception | None = None) -> None:
        self._fragmentos = fragmentos
        self._error = error

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *exc):  # type: ignore[no-untyped-def]
        return False

    @property
    def text_stream(self):  # type: ignore[no-untyped-def]
        async def _gen():  # type: ignore[no-untyped-def]
            for fragmento in self._fragmentos:
                yield fragmento
            if self._error is not None:
                raise self._error

        return _gen()


class _ClienteFake:
    """Doble de AsyncAnthropic: registra llamadas y devuelve lo programado."""

    def __init__(
        self,
        texto_json: str = '{"intent": "recuperar_correo", "confianza": 0.94}',
        error: Exception | None = None,
        fragmentos: list[str] | None = None,
    ) -> None:
        self.texto_json = texto_json
        self.error = error
        self.fragmentos = fragmentos or ["Hola ", "mundo"]
        self.llamadas: list[dict] = []
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    async def _create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.llamadas.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.texto_json)])

    def _stream(self, **kwargs):  # type: ignore[no-untyped-def]
        self.llamadas.append(kwargs)
        if self.error is not None:
            return _StreamFake([], error=self.error)
        return _StreamFake(self.fragmentos)


@pytest.fixture()
def con_key(monkeypatch):  # type: ignore[no-untyped-def]
    """Simula una API key configurada y deja el breaker limpio."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    llm.reset_estado()
    yield
    llm.reset_estado()
    get_settings.cache_clear()


def _inyectar(monkeypatch, cliente: _ClienteFake) -> None:
    monkeypatch.setattr(llm, "_get_client", lambda: cliente)


# ------------------------------------------------------------- sin key / estado


def test_sin_key_no_disponible_y_disabled():
    """Con la key vacía del entorno de test: no disponible y healthz=disabled."""
    llm.reset_estado()
    assert llm.llm_disponible() is False
    assert llm.estado_llm() == "disabled"


async def test_clasificar_sin_key_lanza_llm_no_disponible():
    llm.reset_estado()
    with pytest.raises(llm.LlmNoDisponible):
        await llm.clasificar("system", "user", ESQUEMA_INTENT)


async def test_generar_stream_sin_key_lanza_llm_no_disponible():
    llm.reset_estado()
    with pytest.raises(llm.LlmNoDisponible):
        async for _ in llm.generar_stream("system", "user"):
            pass


# ------------------------------------------------------------ structured output


async def test_clasificar_parsea_el_json(con_key, monkeypatch):
    cliente = _ClienteFake()
    _inyectar(monkeypatch, cliente)

    resultado = await llm.clasificar("Eres el clasificador.", "hola", ESQUEMA_INTENT)

    assert resultado == {"intent": "recuperar_correo", "confianza": 0.94}
    llamada = cliente.llamadas[0]
    assert llamada["model"] == get_settings().LLM_MODEL_ROUTER
    assert llamada["max_tokens"] == 50
    assert llamada["output_config"] == {"format": {"type": "json_schema", "schema": ESQUEMA_INTENT}}
    # system estable primero, cacheable (prompt caching)
    assert llamada["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert llamada["messages"] == [{"role": "user", "content": "hola"}]
    # sin temperature (retirado en los modelos actuales)
    assert "temperature" not in llamada


async def test_clasificar_respeta_model_y_max_tokens(con_key, monkeypatch):
    cliente = _ClienteFake()
    _inyectar(monkeypatch, cliente)

    await llm.clasificar("s", "u", ESQUEMA_INTENT, model="claude-opus-4-8", max_tokens=99)

    assert cliente.llamadas[0]["model"] == "claude-opus-4-8"
    assert cliente.llamadas[0]["max_tokens"] == 99


# ------------------------------------------------------------------- streaming


async def test_generar_stream_itera_los_fragmentos(con_key, monkeypatch):
    cliente = _ClienteFake(fragmentos=["Para ", "recuperar ", "su contraseña..."])
    _inyectar(monkeypatch, cliente)

    partes = [f async for f in llm.generar_stream("system RAG", "consulta")]

    assert "".join(partes) == "Para recuperar su contraseña..."
    llamada = cliente.llamadas[0]
    assert llamada["model"] == get_settings().LLM_MODEL
    assert llamada["max_tokens"] == 400


async def test_generar_stream_error_de_api_se_mapea(con_key, monkeypatch):
    _inyectar(monkeypatch, _ClienteFake(error=_error_conexion()))

    with pytest.raises(llm.LlmNoDisponible):
        async for _ in llm.generar_stream("s", "u"):
            pass


# -------------------------------------------------------------- circuit breaker


async def test_breaker_abre_tras_tres_fallos(con_key, monkeypatch):
    _inyectar(monkeypatch, _ClienteFake(error=_error_conexion()))

    for _ in range(3):
        with pytest.raises(llm.LlmNoDisponible):
            await llm.clasificar("s", "u", ESQUEMA_INTENT)

    assert llm.llm_disponible() is False
    assert llm.estado_llm() == "degraded"
    # con el breaker abierto ni siquiera se intenta la llamada
    cliente_nuevo = _ClienteFake()
    _inyectar(monkeypatch, cliente_nuevo)
    with pytest.raises(llm.LlmNoDisponible):
        await llm.clasificar("s", "u", ESQUEMA_INTENT)
    assert cliente_nuevo.llamadas == []


async def test_breaker_medio_abierto_se_cierra_con_un_exito(con_key, monkeypatch):
    _inyectar(monkeypatch, _ClienteFake(error=_error_conexion()))
    for _ in range(3):
        with pytest.raises(llm.LlmNoDisponible):
            await llm.clasificar("s", "u", ESQUEMA_INTENT)
    assert llm.llm_disponible() is False

    # simula el paso de los 60 s: la ventana de apertura expira (medio-abierto)
    monkeypatch.setattr(llm, "_abierto_hasta", time.monotonic() - 1)
    assert llm.llm_disponible() is True

    _inyectar(monkeypatch, _ClienteFake())
    resultado = await llm.clasificar("s", "u", ESQUEMA_INTENT)
    assert resultado["intent"] == "recuperar_correo"
    assert llm.estado_llm() == "configured"


async def test_dos_fallos_no_abren_el_breaker(con_key, monkeypatch):
    _inyectar(monkeypatch, _ClienteFake(error=_error_conexion()))
    for _ in range(2):
        with pytest.raises(llm.LlmNoDisponible):
            await llm.clasificar("s", "u", ESQUEMA_INTENT)
    assert llm.llm_disponible() is True
    assert llm.estado_llm() == "configured"
