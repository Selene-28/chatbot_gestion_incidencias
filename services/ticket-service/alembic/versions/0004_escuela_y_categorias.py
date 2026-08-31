"""Escuela (Industrial/Sistemas) y nuevas categorías de incidencia.

Reemplaza por completo el antiguo concepto de "Área":

- `usuarios.area`: el ENUM pasa a tener SOLO 'Industrial' y 'Sistemas' (los
  valores que envía el flujo "Registrar incidencia" del chatbot, que ahora
  pregunta "Escuela" en vez de "Área"). Los valores previos
  ('Docente','Administrativo','Estudiante','Otro') ya no se usan en ninguna
  parte del sistema (chatbot, API directa, panel) y se retiran del ENUM;
  cualquier fila existente con un valor antiguo se reasigna a 'Industrial'
  antes de angostar la columna para que el ALTER no falle.
- `categorias`: se insertan 5 categorías nuevas (upsert por `nombre`, que ya
  es UNIQUE). Las categorías anteriores NO se tocan ni desactivan, para no
  romper flujos internos que todavía las usan (p. ej. los árboles de
  diagnóstico F-05 de "Aula Virtual" y "Software Institucional").

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27
"""

from alembic import op
from sqlalchemy import text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

CATEGORIAS_NUEVAS = (
    "Problemas con la página web de la facultad",
    "SGA",
    "Equipos Tecnológicos",
    "Laboratorios",
    "Solicitudes Tecnológicas",
)


def upgrade() -> None:
    """Reemplaza el ENUM de escuela (retira los valores antiguos) e inserta
    las categorías nuevas."""
    conexion = op.get_bind()
    # Amplía temporalmente el ENUM para permitir la reasignación de valores sin
    # chocar con el modo estricto de MySQL.
    op.execute(
        """
        ALTER TABLE usuarios
        MODIFY COLUMN area
        ENUM('Docente','Administrativo','Estudiante','Otro','Industrial','Sistemas')
        NOT NULL DEFAULT 'Industrial'
        """
    )
    # Reasigna cualquier fila con un valor antiguo antes de angostar el ENUM,
    # para que el ALTER no falle por datos fuera de rango.
    conexion.execute(
        text("UPDATE usuarios SET area = 'Industrial' WHERE area NOT IN ('Industrial','Sistemas')")
    )
    op.execute(
        """
        ALTER TABLE usuarios
        MODIFY COLUMN area
        ENUM('Industrial','Sistemas')
        NOT NULL DEFAULT 'Industrial'
        """
    )
    for nombre in CATEGORIAS_NUEVAS:
        conexion.execute(
            text(
                """
                INSERT INTO categorias (nombre, descripcion, activo)
                VALUES (:nombre, NULL, 1)
                ON DUPLICATE KEY UPDATE activo = 1
                """
            ),
            {"nombre": nombre},
        )


def downgrade() -> None:
    """Revierte el ENUM a los valores originales y desactiva las categorías
    agregadas (best-effort)."""
    conexion = op.get_bind()
    # No se eliminan las categorías (podrían tener tickets asociados por FK);
    # se desactivan para que dejen de ofrecerse.
    for nombre in CATEGORIAS_NUEVAS:
        conexion.execute(
            text("UPDATE categorias SET activo = 0 WHERE nombre = :nombre"),
            {"nombre": nombre},
        )
    # Reasigna cualquier usuario con los valores nuevos antes de ampliar el
    # ENUM de vuelta al esquema original, para que el ALTER no falle.
    op.execute("UPDATE usuarios SET area = 'Otro' WHERE area IN ('Industrial','Sistemas')")
    op.execute(
        """
        ALTER TABLE usuarios
        MODIFY COLUMN area
        ENUM('Docente','Administrativo','Estudiante','Otro')
        NOT NULL DEFAULT 'Otro'
        """
    )
