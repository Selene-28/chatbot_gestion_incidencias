"""Routers HTTP del servicio.

`routers` se expone con carga perezosa (módulo __getattr__) para que main.py
pueda montar los routers del dominio sin acoplarse a cada módulo y sin romper
la importación del paquete si alguno falta.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "routers":
        from app.api import encuestas, incidencias, metricas

        return [incidencias.router, encuestas.router, metricas.router]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
