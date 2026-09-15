# Nginx with widget + reverse-proxy config baked in.
# Avoids host bind-mounts (they are empty when the Docker daemon is remote).
# Plantillas + envsubst: en Railway escucha $PORT y resuelve *.railway.internal.
FROM nginx:1.27-alpine

COPY deploy/nginx/templates/ /etc/nginx/templates/
COPY deploy/nginx/docker-entrypoint.d/15-upstreams.sh /docker-entrypoint.d/15-upstreams.sh
COPY deploy/nginx/html/maintenance.html /usr/share/nginx/html/maintenance.html
COPY widget/public /usr/share/nginx/html/widget

RUN chmod +x /docker-entrypoint.d/15-upstreams.sh

ENV LISTEN_PORT=80 \
    CHATBOT_UPSTREAM=http://chatbot-api:8000 \
    TICKETS_UPSTREAM=http://ticket-service:8001
