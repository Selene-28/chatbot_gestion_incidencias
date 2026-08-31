"""Entorno de Alembic: migra chatbot_db usando la variable de entorno DB_URL.

El runtime usa el driver async `mysql+asyncmy`; para migrar se convierte al
driver síncrono `mysql+pymysql` (Alembic corre en modo síncrono).
"""

import os

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

DEFAULT_DB_URL = "mysql+asyncmy://chatbot:chatbot@localhost:3306/chatbot_db"


def _sync_db_url() -> str:
    """Lee DB_URL y la normaliza al driver síncrono pymysql."""
    url = os.environ.get("DB_URL", DEFAULT_DB_URL)
    return url.replace("mysql+asyncmy://", "mysql+pymysql://").replace(
        "mysql+aiomysql://", "mysql+pymysql://"
    )


# Migraciones escritas a mano con SQL explícito: no hay metadata objetivo
target_metadata = None


def run_migrations_offline() -> None:
    """Modo offline: emite el SQL sin conectarse a la BD."""
    context.configure(
        url=_sync_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online: conecta y aplica las migraciones."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _sync_db_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
