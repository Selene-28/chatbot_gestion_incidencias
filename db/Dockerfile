# MySQL con el script de esquemas/usuarios horneado (sin bind-mount de db/init).
#
# En Railway el contexto de build es la RAÍZ del repo:
#   Root Directory = (vacío)
#   Dockerfile Path = db/Dockerfile
#   Branch = la que contiene este archivo (no master hasta que se una).
FROM mysql:8.4
COPY db/init/01-init.sh /docker-entrypoint-initdb.d/01-init.sh
RUN chmod +x /docker-entrypoint-initdb.d/01-init.sh
