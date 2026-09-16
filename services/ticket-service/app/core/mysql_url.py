"""Railway: el hostname *.railway.internal tiene A (IPv4) que rechaza TCP.

El mesh solo enruta AAAA (IPv6). Hay que conectar a esa IP, no al A.
"""

from __future__ import annotations

import logging
import os
import socket

from sqlalchemy.engine.url import make_url

logger = logging.getLogger("app.mysql_url")


def _en_railway() -> bool:
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"):
        return True
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:
            return "railway.internal" in fh.read()
    except OSError:
        return False


def url_mysql_railway(url: str) -> str:
    """Si el host es de Railway, sustituye por la IPv6 (AAAA). Si no, no toca."""
    try:
        parsed = make_url(url)
    except Exception:  # noqa: BLE001 — URL rara: dejarla igual
        return url
    host = parsed.host
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return url
    if not _en_railway() and not host.endswith(".railway.internal"):
        return url
    port = parsed.port or 3306
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
    except OSError as exc:
        logger.warning("Sin AAAA para %s:%s (%s); se deja el hostname", host, port, exc)
        return url
    if not infos:
        return url
    ipv6 = infos[0][4][0]
    nueva = parsed.set(host=ipv6)
    logger.info("MySQL %s → [%s]:%s", host, ipv6, port)
    return nueva.render_as_string(hide_password=False)


def url_mysql_sync(url: str) -> str:
    """DB_URL de runtime (asyncmy) → pymysql, con host Railway ya resuelto."""
    resuelta = url_mysql_railway(url)
    if "+pymysql" in resuelta:
        return resuelta
    if "+asyncmy" in resuelta:
        return resuelta.replace("+asyncmy", "+pymysql")
    if resuelta.startswith("mysql://"):
        return resuelta.replace("mysql://", "mysql+pymysql://", 1)
    return resuelta
