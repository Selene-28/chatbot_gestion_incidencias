"""Técnico único (Paul Barzola), columna ``respuesta`` y adjuntos del panel.

- Renombra al técnico semilla a «Paul Barzola» y desactiva ``tecnico2``
  (Carlos/María ya no aparecen en «Asignar técnico»).
- Agrega ``tickets.respuesta`` (VARCHAR 1000) para la nota del técnico
  que el estudiante ve al consultar un ticket Resuelto/Cerrado.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Aplica el técnico único y la columna de respuesta."""
    op.execute("ALTER TABLE tickets ADD COLUMN respuesta VARCHAR(1000) NULL")
    op.execute(
        "UPDATE usuarios SET nombre = 'Paul Barzola' "
        "WHERE correo = 'tecnico1@ctic.local'"
    )
    op.execute("UPDATE usuarios SET activo = 0 WHERE correo = 'tecnico2@ctic.local'")


def downgrade() -> None:
    """Revierte la columna y reactiva el segundo técnico semilla."""
    op.execute("UPDATE usuarios SET activo = 1 WHERE correo = 'tecnico2@ctic.local'")
    op.execute(
        "UPDATE usuarios SET nombre = 'Carlos Ramírez' "
        "WHERE correo = 'tecnico1@ctic.local'"
    )
    op.execute("ALTER TABLE tickets DROP COLUMN respuesta")
