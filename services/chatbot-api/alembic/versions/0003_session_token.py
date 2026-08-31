"""Token de sesión del widget (autenticación del protocolo de chat).

Agrega a `conversaciones` la columna `session_token_hash`: SHA-256 (hex, 64
chars) del token opaco emitido al crear la sesión (`secrets.token_urlsafe(32)`).
El token en claro nunca se persiste; la comparación se hace por hash.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE conversaciones
          ADD COLUMN session_token_hash CHAR(64) NULL
              COMMENT 'SHA-256 hex del sessionToken opaco del widget'
              AFTER codigo,
          ADD UNIQUE INDEX uq_conv_token_hash (session_token_hash)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE conversaciones
          DROP INDEX uq_conv_token_hash,
          DROP COLUMN session_token_hash
        """
    )
