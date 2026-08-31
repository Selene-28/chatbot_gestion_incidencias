"""Configuración del servicio vía variables de entorno (pydantic-settings)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno del servicio (ver prd/07 §3-§4)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos (driver async para runtime; Alembic la convierte a pymysql)
    DB_URL: str = "mysql+asyncmy://tickets:tickets@localhost:3306/tickets_db"

    # Seguridad
    JWT_SECRET: str = "cambiar-64-chars-aleatorios"
    TICKETS_API_KEY: str = "cambiar"  # clave que valida el header X-Api-Key de servicios

    # Almacenamiento de adjuntos
    UPLOADS_DIR: str = "/data/uploads"

    # Contraseñas iniciales del staff (solo para seeds de desarrollo)
    SEED_ADMIN_PASSWORD: str = "cambiar123"
    SEED_TECNICO_PASSWORD: str = "cambiar123"

    # Zona horaria
    TZ: str = "America/Lima"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cacheada (una sola lectura del entorno)."""
    return Settings()
