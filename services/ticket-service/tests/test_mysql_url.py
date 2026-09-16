"""La URL de MySQL en Railway debe usar AAAA (IPv6), no el A que rechaza TCP."""

import socket

from app.core.mysql_url import url_mysql_railway, url_mysql_sync


def test_localhost_no_cambia() -> None:
    url = "mysql+asyncmy://tickets:x@localhost:3306/tickets_db"
    assert url_mysql_railway(url) == url


def test_sync_convierte_asyncmy() -> None:
    url = "mysql+asyncmy://tickets:x@localhost:3306/tickets_db"
    assert url_mysql_sync(url) == "mysql+pymysql://tickets:x@localhost:3306/tickets_db"


def test_railway_sustituye_host_por_ipv6(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    def fake_getaddrinfo(host, port, family, *args, **kwargs):
        assert host == "mysql.railway.internal"
        assert family == socket.AF_INET6
        return [(None, None, None, None, ("fd12::10", 3306, 0, 0))]

    monkeypatch.setattr("app.core.mysql_url.socket.getaddrinfo", fake_getaddrinfo)
    url = "mysql+asyncmy://tickets:secreto@mysql.railway.internal:3306/tickets_db"
    out = url_mysql_railway(url)
    assert "fd12::10" in out
    assert "secreto" in out
    assert "mysql.railway.internal" not in out
