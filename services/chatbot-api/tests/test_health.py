"""/healthz debe responder 200 aunque la BD no esté disponible."""


def test_healthz_responde_200_con_db_down(client):
    """Sin MySQL accesible, la app vive y reporta db=down, llm=disabled."""
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "db": "down", "llm": "disabled"}


def test_healthz_no_usa_envelope(client):
    """Es un endpoint de infraestructura: sin success/code/message/data."""
    body = client.get("/healthz").json()
    assert "success" not in body
    assert "data" not in body


def test_healthz_reporta_llm_configured(client, monkeypatch):
    """Con ANTHROPIC_API_KEY seteada, llm pasa a 'configured'."""
    from app.core.config import get_settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    try:
        body = client.get("/healthz").json()
        assert body["llm"] == "configured"
    finally:
        get_settings.cache_clear()


def test_healthz_reporta_llm_degraded_con_breaker_abierto(client, monkeypatch):
    """Con key configurada pero circuit breaker abierto → 'degraded' (prd/06 §6)."""
    import time

    from app.core.config import get_settings
    from app.ia import llm

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    monkeypatch.setattr(llm, "_abierto_hasta", time.monotonic() + 60)
    try:
        body = client.get("/healthz").json()
        assert body["llm"] == "degraded"
    finally:
        llm.reset_estado()
        get_settings.cache_clear()
