# Nginx with widget + reverse-proxy config baked in.
# Avoids host bind-mounts (they are empty when the Docker daemon is remote).
FROM nginx:1.27-alpine

COPY deploy/nginx/conf.d /etc/nginx/conf.d
COPY deploy/nginx/html/maintenance.html /usr/share/nginx/html/maintenance.html
COPY widget/public /usr/share/nginx/html/widget
