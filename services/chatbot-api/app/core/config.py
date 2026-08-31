"""Configuración del servicio vía variables de entorno (pydantic-settings).

Las variables coinciden con las definidas en `prd/07-despliegue.md` §3-4.
Todas tienen defaults sensatos para desarrollo local.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno del servicio."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de datos (runtime usa driver async; las migraciones lo convierten a pymysql)
    DB_URL: str = "mysql+asyncmy://chatbot:chatbot@localhost:3306/chatbot_db"

    # Integración con el servicio de tickets (ADR-03)
    TICKETS_API_BASE_URL: str = "http://localhost:8001"
    TICKETS_API_KEY: str = "dev-key"

    # Autenticación del staff (prd/04 §1): el JWT lo emite ticket-service y este
    # servicio lo VALIDA con el mismo secreto (HS256, cookie HttpOnly panel_token).
    # El default de dev coincide con el .env compartido del proyecto.
    JWT_SECRET: str = "cambiar"

    # LLM (opcional en dev; la integración real llega en semanas 3-4)
    ANTHROPIC_API_KEY: str | None = None
    LLM_MODEL: str = "claude-opus-4-8"
    LLM_MODEL_ROUTER: str = "claude-haiku-4-5"

    # Índice vectorial (RAG, semanas 3-4)
    CHROMA_DIR: str = "/data/chroma"
    # Umbral de similitud coseno (0-1) para aceptar un artículo del RAG.
    # Calibrado para intfloat/multilingual-e5-small: consultas relevantes ~0.88-0.92,
    # irrelevantes ~0.75-0.82; 0.83 separa ambas y evita responder fuera de tema
    # (RN-08/QA-03). Ajustable con corpus real del CTIC sin tocar código.
    RAG_UMBRAL_SIMILITUD: float = 0.83

    # CORS: orígenes permitidos separados por coma
    ALLOWED_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5500,http://127.0.0.1:5500,"
        "http://localhost:8089,http://127.0.0.1:8089,"
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:8001,http://127.0.0.1:8001"
    )

    # Zona horaria (fechas ISO 8601 en America/Lima según prd/04 §5)
    TZ: str = "America/Lima"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Devuelve los orígenes CORS como lista, ignorando entradas vacías."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Instancia cacheada de la configuración (limpiar cache en tests)."""
    return Settings()
