# MySQL con el script de esquemas/usuarios horneado (sin bind-mount de db/init).
FROM mysql:8.4
COPY db/init/01-init.sh /docker-entrypoint-initdb.d/01-init.sh
RUN chmod +x /docker-entrypoint-initdb.d/01-init.sh
