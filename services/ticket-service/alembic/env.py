"""Entorno de migraciones Alembic para tickets_db.

Lee la variable de entorno DB_URL (driver async asyncmy en runtime) y la
convierte a un driver síncrono (pymysql) para ejecutar las migraciones.
"""

import os

from sqlalchemy import create_engine, pool

from alembic import context

config = context.config

DEFAULT_DB_URL = "mysql+asyncmy://tickets:tickets@localhost:3306/tickets_db"


def _sync_db_url() -> str:
    """Convierte la DB_URL async (mysql+asyncmy) a una URL síncrona (mysql+pymysql)."""
    url = os.environ.get("DB_URL", DEFAULT_DB_URL)
    if "+asyncmy" in url:
        return url.replace("+asyncmy", "+pymysql")
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+pymysql://", 1)
    return url


# Migraciones escritas a mano (DDL del PRD): sin autogenerate ni metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo offline (emite SQL sin conectarse)."""
    context.configure(
        url=_sync_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta migraciones conectándose a la base de datos."""
    engine = create_engine(_sync_db_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
