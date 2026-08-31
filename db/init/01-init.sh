#!/usr/bin/env bash
# Init de MySQL (montado en /docker-entrypoint-initdb.d).
# Crea los esquemas chatbot_db y tickets_db y un usuario por servicio con
# mínimo privilegio. Excepción: `chatbot` recibe SELECT sobre tickets_db.*
# (lo necesita una vista de métricas).
#
# Requiere en el entorno: MYSQL_ROOT_PASSWORD, DB_CHATBOT_PASSWORD, DB_TICKETS_PASSWORD.
# Idempotente: puede re-ejecutarse sin efectos adversos.

set -euo pipefail

: "${DB_CHATBOT_PASSWORD:?falta DB_CHATBOT_PASSWORD}"
: "${DB_TICKETS_PASSWORD:?falta DB_TICKETS_PASSWORD}"

mysql --user=root --password="${MYSQL_ROOT_PASSWORD}" <<-EOSQL
	CREATE DATABASE IF NOT EXISTS chatbot_db
	  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
	CREATE DATABASE IF NOT EXISTS tickets_db
	  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

	CREATE USER IF NOT EXISTS 'chatbot'@'%' IDENTIFIED BY '${DB_CHATBOT_PASSWORD}';
	ALTER USER 'chatbot'@'%' IDENTIFIED BY '${DB_CHATBOT_PASSWORD}';

	CREATE USER IF NOT EXISTS 'tickets'@'%' IDENTIFIED BY '${DB_TICKETS_PASSWORD}';
	ALTER USER 'tickets'@'%' IDENTIFIED BY '${DB_TICKETS_PASSWORD}';

	-- Mínimo privilegio: cada usuario solo sobre su propio esquema.
	GRANT ALL PRIVILEGES ON chatbot_db.* TO 'chatbot'@'%';
	GRANT ALL PRIVILEGES ON tickets_db.* TO 'tickets'@'%';

	-- Excepción documentada: vista de métricas del chatbot lee tickets_db.
	GRANT SELECT ON tickets_db.* TO 'chatbot'@'%';

	FLUSH PRIVILEGES;
EOSQL

echo "[init] esquemas chatbot_db/tickets_db y usuarios chatbot/tickets listos."
