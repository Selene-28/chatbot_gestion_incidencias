"""Esquema inicial de tickets_db (DDL exacto de prd/03 §2).

Revision ID: 0001
Revises:
Create Date: 2026-07-03
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea las tablas del dominio de tickets."""
    op.execute(
        """
        CREATE TABLE usuarios (
          id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          nombre        VARCHAR(120)  NOT NULL,
          correo        VARCHAR(150)  NOT NULL UNIQUE,
          area          ENUM('Docente','Administrativo','Estudiante','Otro')
                        NOT NULL DEFAULT 'Otro',
          rol           ENUM('usuario','tecnico','admin') NOT NULL DEFAULT 'usuario',
          password_hash VARCHAR(255)  NULL COMMENT 'Solo staff (tecnico/admin), Argon2id',
          activo        BOOLEAN       NOT NULL DEFAULT TRUE,
          created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT chk_correo_unac CHECK (correo LIKE '%@unac.edu.pe' OR rol <> 'usuario')
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        """
        CREATE TABLE categorias (
          id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          nombre      VARCHAR(80)  NOT NULL UNIQUE,
          descripcion VARCHAR(255) NULL,
          activo      BOOLEAN      NOT NULL DEFAULT TRUE
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        """
        CREATE TABLE tickets (
          id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          codigo              VARCHAR(20)   NOT NULL UNIQUE COMMENT 'INC-AAAA-NNNN (RN-01)',
          usuario_id          BIGINT UNSIGNED NOT NULL,
          categoria_id        INT UNSIGNED  NOT NULL,
          subcategoria        VARCHAR(120)  NULL,
          descripcion         TEXT          NOT NULL,
          prioridad           ENUM('Baja','Media','Alta') NOT NULL DEFAULT 'Media',
          estado              ENUM('Registrado','Asignado','En Proceso','Escalado',
                                   'Resuelto','Cerrado')
                              NOT NULL DEFAULT 'Registrado',
          tecnico_id          BIGINT UNSIGNED NULL,
          origen              ENUM('chatbot','web') NOT NULL DEFAULT 'chatbot',
          conversacion_codigo CHAR(36)      NULL COMMENT 'UUID de la conversación de origen',
          created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,
          resuelto_at         DATETIME      NULL,
          FOREIGN KEY (usuario_id)   REFERENCES usuarios(id),
          FOREIGN KEY (categoria_id) REFERENCES categorias(id),
          FOREIGN KEY (tecnico_id)   REFERENCES usuarios(id),
          INDEX idx_tickets_estado (estado),
          INDEX idx_tickets_usuario (usuario_id),
          INDEX idx_tickets_created (created_at)
        ) ENGINE=InnoDB
        """
    )
    # Correlativo anual para RN-01 (generación transaccional del código)
    op.execute(
        """
        CREATE TABLE ticket_secuencias (
          anio        SMALLINT UNSIGNED PRIMARY KEY,
          ultimo_nro  INT UNSIGNED NOT NULL DEFAULT 0
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        """
        CREATE TABLE ticket_historial (
          id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          ticket_id       BIGINT UNSIGNED NOT NULL,
          estado_anterior VARCHAR(20) NULL,
          estado_nuevo    VARCHAR(20) NOT NULL,
          comentario      TEXT        NULL,
          actor_id        BIGINT UNSIGNED NULL COMMENT 'NULL = acción del sistema/chatbot',
          created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
          FOREIGN KEY (actor_id)  REFERENCES usuarios(id),
          INDEX idx_hist_ticket (ticket_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        """
        CREATE TABLE ticket_adjuntos (
          id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          ticket_id       BIGINT UNSIGNED NOT NULL,
          nombre_original VARCHAR(255) NOT NULL,
          ruta_almacenada VARCHAR(500) NOT NULL
                          COMMENT 'fuera del árbol web, nombre aleatorio',
          mime_type       VARCHAR(100) NOT NULL
                          COMMENT 'image/jpeg|image/png|application/pdf (RF-13)',
          tamano_bytes    INT UNSIGNED NOT NULL COMMENT 'máx 5 MB',
          created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        """
        CREATE TABLE encuestas (
          id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
          ticket_id           BIGINT UNSIGNED NULL,
          conversacion_codigo CHAR(36) NULL,
          calificacion        TINYINT UNSIGNED NOT NULL,
          comentario          VARCHAR(500) NULL,
          created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          -- Sin ON DELETE SET NULL: MySQL (err. 3823) prohíbe acciones referenciales
          -- sobre columnas usadas en un CHECK; los tickets se cierran, no se eliminan.
          FOREIGN KEY (ticket_id) REFERENCES tickets(id),
          CONSTRAINT chk_calificacion CHECK (calificacion BETWEEN 1 AND 5),
          CONSTRAINT chk_encuesta_origen
            CHECK (ticket_id IS NOT NULL OR conversacion_codigo IS NOT NULL)
        ) ENGINE=InnoDB
        """
    )


def downgrade() -> None:
    """Elimina las tablas en orden inverso de dependencias."""
    for table in (
        "encuestas",
        "ticket_adjuntos",
        "ticket_historial",
        "ticket_secuencias",
        "tickets",
        "categorias",
        "usuarios",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
