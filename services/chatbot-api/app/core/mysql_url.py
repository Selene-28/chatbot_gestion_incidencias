"""Railway: probar hostname e IPs (IPv6 y IPv4) hasta que MySQL acepte TCP.

El A de *.railway.internal suele rechazar; a veces la AAAA tampoco basta
(contraseña sin interpolar, puerto, usuario). Se prueba cada candidato.
"""

from __future__ import annotations

import logging
import os
import re
import socket

from sqlalchemy.engine.url import make_url

logger = logging.getLogger("app.mysql_url")

_url_ok: str | None = None
_ultimo_error: str = ""

_REF = re.compile(r"\$\{\{([A-Za-z0-9_]+)\}\}")


def reset_cache() -> None:
    """Solo tests: olvida el host que ya funcionó."""
    global _url_ok, _ultimo_error
    _url_ok = None
    _ultimo_error = ""


def ultimo_error_mysql() -> str:
    return _ultimo_error


def interpolar_url(url: str) -> str:
    """Expande `${{VAR}}` si Railway no lo hizo (queda literal en DB_URL)."""

    def _repl(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), match.group(0))

    return _REF.sub(_repl, url)


def _en_railway() -> bool:
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"):
        return True
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:
            return "railway.internal" in fh.read()
    except OSError:
        return False


def _sanitizar(msg: str, url: str) -> str:
    try:
        password = make_url(url).password
        if password:
            msg = msg.replace(password, "***")
    except Exception:  # noqa: BLE001
        pass
    return msg.replace("\n", " ")[:240]


def registrar_error(msg: str, url: str) -> None:
    global _ultimo_error
    _ultimo_error = _sanitizar(msg, url)


def a_sync(url: str) -> str:
    if "+pymysql" in url:
        return url
    if "+asyncmy" in url:
        return url.replace("+asyncmy", "+pymysql")
    if "+aiomysql" in url:
        return url.replace("+aiomysql", "+pymysql")
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+pymysql://", 1)
    return url


def _conecta(url_sync: str) -> BaseException | None:
    from sqlalchemy import create_engine

    try:
        engine = create_engine(url_sync, connect_args={"connect_timeout": 3})
        try:
            engine.connect().close()
        finally:
            engine.dispose()
    except BaseException as exc:  # noqa: BLE001 — queremos el motivo real
        return exc
    return None


def _search_domains() -> list[str]:
    dominios: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("search") or line.startswith("domain"):
                    dominios.extend(line.split()[1:])
    except OSError:
        pass
    return dominios


def _hosts_desde_entorno() -> list[str]:
    claves = (
        "MYSQLHOST",
        "MYSQL_HOST",
        "DB_HOST",
        "MYSQL_PRIVATE_HOST",
        "RAILWAY_PRIVATE_DOMAIN",
    )
    return [os.environ[k] for k in claves if os.environ.get(k)]


def diagnostico_dns() -> str:
    """Texto corto para /healthz: si mysql resuelve y qué nameserver hay."""
    partes: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:
            ns = [ln.split()[1] for ln in fh if ln.startswith("nameserver")]
            if ns:
                partes.append("ns=" + ",".join(ns[:3]))
    except OSError:
        partes.append("ns=?")
    for h in ("mysql", "mysql.railway.internal"):
        try:
            ips = sorted({info[4][0] for info in socket.getaddrinfo(h, 3306)})
            partes.append(f"{h}={','.join(ips) or 'vacio'}")
        except OSError as exc:
            partes.append(f"{h}=err{getattr(exc, 'errno', '')}")
    extra = _hosts_desde_entorno()
    if extra:
        partes.append("env=" + ",".join(extra))
    return ";".join(partes)


def _hosts_candidatos(host: str, port: int) -> list[str]:
    vistos: list[str] = []

    def add(nombre: str) -> None:
        if nombre and nombre not in vistos:
            vistos.append(nombre)

    add(host)
    if host == "mysql":
        add("mysql.railway.internal")
    elif host.endswith(".railway.internal"):
        add(host.split(".", 1)[0])
    for extra in _hosts_desde_entorno():
        add(extra)
        if "." not in extra:
            add(f"{extra}.railway.internal")
    for dominio in _search_domains():
        if host and "." not in host:
            add(f"{host}.{dominio}")
        add(f"mysql.{dominio}")
    for family in (socket.AF_INET6, socket.AF_INET):
        try:
            for info in socket.getaddrinfo(host, port, family, socket.SOCK_STREAM):
                add(info[4][0])
        except OSError:
            continue
    return vistos


def url_mysql_railway(url: str) -> str:
    """URL lista para el engine: interpolada y, en Railway, con un host que conecta."""
    global _url_ok, _ultimo_error
    url = interpolar_url(url)
    if _url_ok:
        return _url_ok
    try:
        parsed = make_url(url)
    except Exception:  # noqa: BLE001
        return url
    host = parsed.host
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return url
    if not _en_railway() and not host.endswith(".railway.internal") and host != "mysql":
        return url

    port = parsed.port or 3306
    ultimo: BaseException | None = None
    for candidato in _hosts_candidatos(host, port):
        tentativa = parsed.set(host=candidato).render_as_string(hide_password=False)
        err = _conecta(a_sync(tentativa))
        if err is None:
            logger.info("MySQL ok vía host=%s", candidato)
            _url_ok = tentativa
            _ultimo_error = ""
            return tentativa
        ultimo = err
        logger.warning("MySQL falló host=%s: %s", candidato, _sanitizar(str(err), tentativa))
    if ultimo is not None:
        _ultimo_error = _sanitizar(str(ultimo), url)
    return url


def url_mysql_sync(url: str) -> str:
    """DB_URL de runtime → pymysql, con host Railway ya elegido."""
    return a_sync(url_mysql_railway(url))
