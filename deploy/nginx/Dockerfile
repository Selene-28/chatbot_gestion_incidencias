# Nginx with widget + reverse-proxy config baked in.
# Evita plantillas envsubst: $host se corrompe y Railway marca Crashed.
FROM nginx:1.27-alpine

COPY deploy/nginx/conf.d/_app.inc /etc/nginx/conf.d/_app.inc
COPY deploy/nginx/docker-entrypoint.d/15-upstreams.sh /docker-entrypoint.d/15-upstreams.sh
COPY deploy/nginx/html/maintenance.html /usr/share/nginx/html/maintenance.html
COPY widget/public /usr/share/nginx/html/widget

RUN chmod +x /docker-entrypoint.d/15-upstreams.sh \
    && rm -f /etc/nginx/conf.d/default.conf

ENV LISTEN_PORT=80 \
    CHATBOT_UPSTREAM=http://chatbot-api:8000 \
    TICKETS_UPSTREAM=http://ticket-service:8001
