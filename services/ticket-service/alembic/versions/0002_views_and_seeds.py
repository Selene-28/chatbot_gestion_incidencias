"""Vistas de métricas y datos semilla (prd/03 §4 y §5).

- Vistas: v_satisfaccion, v_tiempo_resolucion.
- Seeds: 7 categorías, secuencia del año en curso y usuarios staff.
  Las contraseñas del staff vienen de las variables de entorno
  SEED_ADMIN_PASSWORD / SEED_TECNICO_PASSWORD (default de desarrollo:
  "cambiar123") y se hashean con Argon2id en el momento de la migración —
  nunca se almacenan hashes precalculados en el código.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03
"""

import os
from datetime import datetime

import sqlalchemy as sa
from argon2 import PasswordHasher

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CATEGORIAS = (
    "Correo Institucional",
    "Internet/WiFi",
    "Aula Virtual",
    "Software Institucional",
    "Equipos de Cómputo",
    "Cuentas y Accesos",
    "Otros",
)

STAFF_CORREOS = ("admin@ctic.local", "tecnico1@ctic.local")


def upgrade() -> None:
    """Crea las vistas de métricas e inserta los datos semilla."""
    # --- Vistas (prd/03 §4) ---
    op.execute(
        """
        CREATE OR REPLACE VIEW v_satisfaccion AS
        SELECT DATE(created_at) AS fecha,
               COUNT(*) AS encuestas,
               ROUND(AVG(calificacion), 2) AS calificacion_prom
        FROM encuestas GROUP BY DATE(created_at)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW v_tiempo_resolucion AS
        SELECT t.codigo, t.estado, c.nombre AS categoria,
               TIMESTAMPDIFF(HOUR, t.created_at, t.resuelto_at) AS horas_resolucion
        FROM tickets t JOIN categorias c ON c.id = t.categoria_id
        WHERE t.resuelto_at IS NOT NULL
        """
    )

    conn = op.get_bind()

    # --- Seeds: categorías ---
    for nombre in CATEGORIAS:
        conn.execute(
            sa.text("INSERT IGNORE INTO categorias (nombre) VALUES (:nombre)").bindparams(
                nombre=nombre
            )
        )

    # --- Seeds: secuencia del año en curso (RN-01) ---
    conn.execute(
        sa.text(
            "INSERT IGNORE INTO ticket_secuencias (anio, ultimo_nro) VALUES (:anio, 0)"
        ).bindparams(anio=datetime.now().year)
    )

    # --- Seeds: usuarios staff (contraseñas por env var, hasheadas con Argon2id) ---
    hasher = PasswordHasher()  # Argon2id es el modo por defecto
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "cambiar123")
    tecnico_password = os.environ.get("SEED_TECNICO_PASSWORD", "cambiar123")

    staff = [
        {
            "nombre": "Administrador CTIC",
            "correo": "admin@ctic.local",
            "rol": "admin",
            "password_hash": hasher.hash(admin_password),
        },
        {
            "nombre": "Paul Barzola",
            "correo": "tecnico1@ctic.local",
            "rol": "tecnico",
            "password_hash": hasher.hash(tecnico_password),
        },
    ]
    for user in staff:
        conn.execute(
            sa.text(
                """
                INSERT IGNORE INTO usuarios (nombre, correo, area, rol, password_hash)
                VALUES (:nombre, :correo, 'Otro', :rol, :password_hash)
                """
            ).bindparams(**user)
        )


def downgrade() -> None:
    """Elimina vistas y datos semilla."""
    op.execute("DROP VIEW IF EXISTS v_tiempo_resolucion")
    op.execute("DROP VIEW IF EXISTS v_satisfaccion")

    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM usuarios WHERE correo IN :correos").bindparams(
            sa.bindparam("correos", value=list(STAFF_CORREOS), expanding=True)
        )
    )
    conn.execute(
        sa.text("DELETE FROM ticket_secuencias WHERE anio = :anio").bindparams(
            anio=datetime.now().year
        )
    )
    conn.execute(
        sa.text("DELETE FROM categorias WHERE nombre IN :nombres").bindparams(
            sa.bindparam("nombres", value=list(CATEGORIAS), expanding=True)
        )
    )
