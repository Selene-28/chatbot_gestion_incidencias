"""Panel de agentes server-rendered (Jinja2 + htmx) — RF-11.

Expone ``router`` (rutas HTML bajo /panel) para su registro en app.main.
"""

from app.panel.routes import router

__all__ = ["router"]
