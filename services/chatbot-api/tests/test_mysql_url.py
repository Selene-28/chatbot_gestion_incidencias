"""La URL de MySQL en Railway prueba IPv6/IPv4 e interpola ${{VAR}}."""

import socket

from app.core import mysql_url
from app.core.mysql_url import interpolar_url, url_mysql_railway, url_mysql_sync


def setup_function() -> None:
    mysql_url.reset_cache()


def test_localhost_no_cambia() -> None:
    url = "mysql+asyncmy://chatbot:x@localhost:3306/chatbot_db"
    assert url_mysql_railway(url) == url


def test_sync_convierte_asyncmy() -> None:
    url = "mysql+asyncmy://chatbot:x@localhost:3306/chatbot_db"
    assert url_mysql_sync(url) == "mysql+pymysql://chatbot:x@localhost:3306/chatbot_db"


def test_interpola_referencia_railway(monkeypatch) -> None:
    monkeypatch.setenv("DB_CHATBOT_PASSWORD", "secreto")
    url = "mysql+asyncmy://chatbot:${{DB_CHATBOT_PASSWORD}}@localhost:3306/chatbot_db"
    assert interpolar_url(url) == "mysql+asyncmy://chatbot:secreto@localhost:3306/chatbot_db"


def test_railway_elige_ipv6_si_conecta(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    def fake_getaddrinfo(host, port, family, *args, **kwargs):
        if family == socket.AF_INET6:
            return [(None, None, None, None, ("fd12::10", 3306, 0, 0))]
        return []

    def fake_conecta(url_sync: str) -> BaseException | None:
        if "fd12::10" in url_sync:
            return None
        return OSError("connection refused")

    monkeypatch.setattr("app.core.mysql_url.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("app.core.mysql_url._conecta", fake_conecta)
    url = "mysql+asyncmy://chatbot:secreto@mysql.railway.internal:3306/chatbot_db"
    out = url_mysql_railway(url)
    assert "fd12::10" in out
    assert "secreto" in out
