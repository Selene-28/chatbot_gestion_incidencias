"""Idempotencia de API-01 y staging de adjuntos (API-01b).

- idempotency_keys: clave enviada en el header Idempotency-Key; ante un
  reintento con la misma clave se devuelve el ticket original sin duplicar.
- adjuntos_staging: adjuntos subidos antes de que exista el ticket; un job
  purga los huérfanos con más de 24 h.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea las tablas de idempotencia y de staging de adjuntos."""
    op.execute(
        """
        CREATE TABLE idempotency_keys (
          clave         VARCHAR(64) PRIMARY KEY
                        COMMENT 'header Idempotency-Key de API-01',
          ticket_codigo VARCHAR(20) NOT NULL,
          created_at    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        """
        CREATE TABLE adjuntos_staging (
          id              CHAR(12)     PRIMARY KEY COMMENT 'token corto adj_XXXXXXXX',
          nombre_original VARCHAR(255) NOT NULL,
          ruta_almacenada VARCHAR(500) NOT NULL
                          COMMENT 'fuera del árbol web, nombre aleatorio',
          mime_type       VARCHAR(100) NOT NULL
                          COMMENT 'image/jpeg|image/png|application/pdf (RF-13)',
          tamano_bytes    INT UNSIGNED NOT NULL COMMENT 'máx 5 MB',
          created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
    )


def downgrade() -> None:
    """Elimina las tablas de idempotencia y staging."""
    op.execute("DROP TABLE IF EXISTS adjuntos_staging")
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
