"""Esquema inicial de chatbot_db según prd/03-modelo-de-datos.md §3.

Tablas: conversaciones, mensajes, kb_articulos, handoffs
(con índices, FKs y FULLTEXT ft_kb).

Revision ID: 0001
Revises:
Create Date: 2026-07-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversaciones (
          id                    BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          codigo                CHAR(36)     NOT NULL UNIQUE
                                COMMENT 'UUID v4 = sessionId del widget',
          usuario_correo        VARCHAR(150) NULL
                                COMMENT 'se llena al identificarse (RF-15)',
          usuario_nombre        VARCHAR(120) NULL,
          canal                 ENUM('web_widget') NOT NULL DEFAULT 'web_widget',
          estado_bot            ENUM('ACTIVE','PAUSED') NOT NULL DEFAULT 'ACTIVE',
          estado                ENUM('abierta','cerrada') NOT NULL DEFAULT 'abierta',
          fallback_consecutivos TINYINT UNSIGNED NOT NULL DEFAULT 0,
          flujo_activo          VARCHAR(40)  NULL
                                COMMENT 'registrar_incidencia|consultar_estado|...',
          flujo_contexto        JSON         NULL
                                COMMENT 'datos parciales del flujo en curso',
          iniciada_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          finalizada_at         DATETIME     NULL,
          motivo_cierre         VARCHAR(30)  NULL,
          INDEX idx_conv_estado (estado),
          INDEX idx_conv_correo (usuario_correo)
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    op.execute(
        """
        CREATE TABLE mensajes (
          id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          conversacion_id BIGINT UNSIGNED NOT NULL,
          emisor          ENUM('usuario','bot','agente') NOT NULL,
          contenido       TEXT         NOT NULL,
          intent          VARCHAR(40)  NULL,
          confianza       DECIMAL(4,3) NULL,
          latencia_ms     INT UNSIGNED NULL COMMENT 'para KPI de tiempo de respuesta',
          created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          FOREIGN KEY (conversacion_id) REFERENCES conversaciones(id) ON DELETE CASCADE,
          INDEX idx_msg_conv (conversacion_id),
          INDEX idx_msg_intent (intent),
          INDEX idx_msg_fecha (created_at)
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    op.execute(
        """
        CREATE TABLE kb_articulos (
          id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          titulo     VARCHAR(200)  NOT NULL,
          contenido  MEDIUMTEXT    NOT NULL
                     COMMENT 'markdown; fuente de verdad del índice vectorial',
          categoria  VARCHAR(80)   NOT NULL,
          etiquetas  VARCHAR(300)  NULL
                     COMMENT 'keywords separadas por coma (matching por reglas)',
          activo     BOOLEAN       NOT NULL DEFAULT TRUE,
          version    INT UNSIGNED  NOT NULL DEFAULT 1,
          updated_by BIGINT UNSIGNED NULL,
          updated_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                     ON UPDATE CURRENT_TIMESTAMP,
          FULLTEXT KEY ft_kb (titulo, contenido)
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    op.execute(
        """
        CREATE TABLE handoffs (
          id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          conversacion_id BIGINT UNSIGNED NOT NULL,
          motivo          VARCHAR(40)  NOT NULL
                          COMMENT 'fallback_x3|solicitud_usuario|diagnostico_fallido',
          ticket_codigo   VARCHAR(20)  NULL,
          agente_id       BIGINT UNSIGNED NULL
                          COMMENT 'id de usuarios (tickets_db), referencia lógica',
          estado          ENUM('pendiente','atendido','cerrado','expirado')
                          NOT NULL DEFAULT 'pendiente',
          solicitado_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          atendido_at     DATETIME NULL,
          cerrado_at      DATETIME NULL,
          FOREIGN KEY (conversacion_id) REFERENCES conversaciones(id) ON DELETE CASCADE,
          INDEX idx_handoff_estado (estado)
        ) ENGINE=InnoDB
          DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def downgrade() -> None:
    # Orden inverso por dependencias de FK
    op.execute("DROP TABLE IF EXISTS handoffs")
    op.execute("DROP TABLE IF EXISTS kb_articulos")
    op.execute("DROP TABLE IF EXISTS mensajes")
    op.execute("DROP TABLE IF EXISTS conversaciones")
