"""Vistas de métricas (prd/03 §4) y seeds mínimos de kb_articulos.

- v_autoservicio_diario referencia tickets_db.tickets: si ese esquema aún no
  existe (arranque en paralelo de servicios), se registra un warning y se
  continúa; la vista puede recrearse re-ejecutando la migración o a mano.
- v_latencia_bot y v_intents_frecuentes solo usan chatbot_db.
- Seed: 3 artículos de ejemplo de la base de conocimiento (el set completo de
  15+ artículos validado por el CTIC llega en semanas posteriores).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03
"""

import logging
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# --- Vistas (prd/03 §4) -----------------------------------------------------

V_AUTOSERVICIO_DIARIO = """
CREATE OR REPLACE VIEW v_autoservicio_diario AS
SELECT DATE(c.iniciada_at) AS fecha,
       COUNT(*) AS conversaciones,
       SUM(CASE WHEN t.codigo IS NULL THEN 1 ELSE 0 END) AS sin_ticket,
       ROUND(100 * SUM(CASE WHEN t.codigo IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS pct_autoservicio
FROM conversaciones c
LEFT JOIN tickets_db.tickets t ON t.conversacion_codigo = c.codigo
WHERE c.estado = 'cerrada'
GROUP BY DATE(c.iniciada_at)
"""

V_LATENCIA_BOT = """
CREATE OR REPLACE VIEW v_latencia_bot AS
SELECT DATE(created_at) AS fecha,
       COUNT(*) AS respuestas,
       ROUND(AVG(latencia_ms)) AS latencia_prom_ms,
       MAX(latencia_ms) AS latencia_max_ms
FROM mensajes
WHERE emisor = 'bot' AND latencia_ms IS NOT NULL
GROUP BY DATE(created_at)
"""

V_INTENTS_FRECUENTES = """
CREATE OR REPLACE VIEW v_intents_frecuentes AS
SELECT intent, COUNT(*) AS total
FROM mensajes
WHERE emisor = 'usuario' AND intent IS NOT NULL
GROUP BY intent ORDER BY total DESC
"""

# --- Seeds: 3 artículos iniciales de la base de conocimiento -----------------

SEED_KB = [
    {
        "titulo": "Recuperación de contraseña del correo institucional",
        "categoria": "Correo Institucional",
        "etiquetas": "correo,contraseña,password,recuperar,restablecer,outlook,acceso",
        "contenido": (
            "# Recuperación de contraseña del correo institucional\n\n"
            "Si olvidó la contraseña de su correo `@unac.edu.pe`, siga estos pasos:\n\n"
            "1. Ingrese al portal institucional: <https://correo.unac.edu.pe>.\n"
            "2. Haga clic en **¿Olvidó su contraseña?**.\n"
            "3. Escriba su correo institucional completo y valide el captcha.\n"
            "4. Recibirá un enlace de restablecimiento en su correo personal alterno "
            "registrado en la Oficina de Registros Académicos.\n"
            "5. Cree una contraseña nueva de al menos 8 caracteres con mayúsculas, "
            "minúsculas y números.\n\n"
            "> Si no tiene correo alterno registrado o el enlace no llega, acérquese al "
            "CTIC con su DNI o carné universitario, o registre una incidencia desde este "
            "mismo chat."
        ),
    },
    {
        "titulo": "Horario de atención y contacto del CTIC",
        "categoria": "Información CTIC",
        "etiquetas": "fiis,facultad,ingeniería industrial,ingeniería de sistemas,misión,visión",
        "contenido": (
            "# Información de la Facultad de Ingeniería Industrial y de Sistemas "
            "(FIIS)\n\n"
            "La Facultad de Ingeniería Industrial y de Sistemas de la Universidad "
            "Nacional del Callao (FIIS) es una de las facultades de ingeniería de "
            "la Universidad Nacional del Callao, ubicada en el campus "
            "universitario de Bellavista, Callao.\n\n"
            "Forma ingenieros industriales e ingenieros de sistemas con sólidos "
            "conocimientos científicos, tecnológicos y empresariales, fomentando "
            "la innovación, la investigación y el desarrollo profesional bajo "
            "principios éticos, humanísticos y de responsabilidad social.\n\n"
            "Este resumen es el seed mínimo de arranque; el contenido completo se "
            "carga con `python -m app.scripts.cargar_kb` (ver `datos_kb.py`)."
        ),
    },
    {
        "titulo": "Conexión a la red WiFi de la UNAC",
        "categoria": "Internet/WiFi",
        "etiquetas": "wifi,internet,red,conexión,inalámbrica,eduroam,campus",
        "contenido": (
            "# Conexión a la red WiFi de la UNAC\n\n"
            "Para conectarse a la red inalámbrica del campus:\n\n"
            "1. Active el WiFi de su dispositivo y seleccione la red **UNAC-CAMPUS**.\n"
            "2. Ingrese como usuario su **correo institucional** completo "
            "(ej. `jperez@unac.edu.pe`).\n"
            "3. Ingrese la **misma contraseña** de su correo institucional.\n"
            "4. Si el navegador muestra un portal cautivo, acepte los términos de uso.\n\n"
            "**Problemas frecuentes:**\n\n"
            "- *Credenciales rechazadas:* verifique que su contraseña de correo esté "
            "vigente; si la olvidó, consulte el artículo de recuperación de contraseña.\n"
            "- *Conecta pero sin internet:* olvide la red desde la configuración del "
            "dispositivo y vuelva a conectarse.\n"
            "- *Cobertura débil:* la señal es más estable en pabellones, biblioteca y "
            "cafetería central.\n\n"
            "Si el problema persiste, registre una incidencia indicando la sede, el "
            "pabellón y el tipo de dispositivo."
        ),
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    # Vista con referencia cruzada a tickets_db: tolerante a que aún no exista
    try:
        conn.execute(text(V_AUTOSERVICIO_DIARIO))
    except Exception as exc:  # noqa: BLE001 — el otro esquema puede no existir todavía
        logger.warning(
            "No se pudo crear v_autoservicio_diario (¿tickets_db aún no existe?): %s. "
            "Se continúa; la vista puede crearse luego re-aplicando esta migración.",
            exc,
        )

    conn.execute(text(V_LATENCIA_BOT))
    conn.execute(text(V_INTENTS_FRECUENTES))

    # Seed idempotente de artículos de ejemplo
    insert_stmt = text(
        "INSERT INTO kb_articulos (titulo, contenido, categoria, etiquetas) "
        "SELECT :titulo, :contenido, :categoria, :etiquetas "
        "WHERE NOT EXISTS (SELECT 1 FROM kb_articulos WHERE titulo = :titulo)"
    )
    for articulo in SEED_KB:
        conn.execute(insert_stmt, articulo)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP VIEW IF EXISTS v_intents_frecuentes"))
    conn.execute(text("DROP VIEW IF EXISTS v_latencia_bot"))
    conn.execute(text("DROP VIEW IF EXISTS v_autoservicio_diario"))
    for articulo in SEED_KB:
        conn.execute(
            text("DELETE FROM kb_articulos WHERE titulo = :titulo"),
            {"titulo": articulo["titulo"]},
        )
