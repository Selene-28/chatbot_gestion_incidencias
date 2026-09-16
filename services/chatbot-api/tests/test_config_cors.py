"""CORS: PUBLIC_APP_URL se suma a la lista de orígenes."""

from app.core.config import Settings, get_settings


def test_public_app_url_se_agrega_a_cors() -> None:
    get_settings.cache_clear()
    s = Settings(
        ALLOWED_ORIGINS="https://fiis.unac.edu.pe",
        PUBLIC_APP_URL="https://demo.up.railway.app/",
    )
    assert "https://fiis.unac.edu.pe" in s.allowed_origins_list
    assert "https://demo.up.railway.app" in s.allowed_origins_list


def test_public_app_url_vacio_no_agrega_nada() -> None:
    get_settings.cache_clear()
    s = Settings(ALLOWED_ORIGINS="http://localhost", PUBLIC_APP_URL="")
    assert s.allowed_origins_list == ["http://localhost"]
