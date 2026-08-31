# Cuerpo común del servidor (rutas y proxy) — incluido por el server :80
# (deploy/nginx/conf.d/default.conf) y por el server :443 de producción
# (deploy/nginx/conf.d/tls.conf, desde tls.conf.example). No editar en dos sitios.
# Nota: los archivos .inc no son cargados directamente por nginx (solo *.conf).

# Resolver interno de Docker con TTL corto: sin esto nginx fija la IP del
# upstream al arrancar y un redeploy del servicio deja 502 hasta reiniciarlo.
resolver 127.0.0.11 valid=10s ipv6=off;
set $upstream_chatbot http://chatbot-api:8000;
set $upstream_tickets http://ticket-service:8001;

# Adjuntos ≤ 5 MB (margen para overhead multipart)
client_max_body_size 6m;

# Timeouts de proxy
proxy_connect_timeout 30s;
proxy_send_timeout    30s;
proxy_read_timeout    30s;

# Cabeceras estándar hacia los upstreams
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host  $host;

# ---------- API ----------
location /api/ {
    limit_req zone=api_limit burst=20 nodelay;

    # Ruta /api/ sin match específico
    return 404;

    # chatbot-api (proxy_pass sin URI: conserva la URI completa)
    # Endpoint SSE de larga vida: /api/chat/stream (handoff en tiempo real).
    location /api/chat/ {
        proxy_buffering off;          # entrega inmediata de eventos SSE
        proxy_cache off;
        proxy_set_header Connection "";  # keepalive HTTP/1.1 hacia el upstream
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_read_timeout 1h;        # el stream vive mucho más que 30 s (heartbeat 20 s)
        proxy_pass $upstream_chatbot;
    }
    location /api/faq {
        proxy_pass $upstream_chatbot;
    }
    location /api/kb {
        proxy_pass $upstream_chatbot;
    }
    location /api/metricas {
        proxy_pass $upstream_chatbot;
    }

    # ticket-service
    location /api/incidencias {
        proxy_pass $upstream_tickets;
    }
    location /api/encuesta {
        proxy_pass $upstream_tickets;
    }
    location /api/auth {
        proxy_pass $upstream_tickets;
    }
    location /api/panel {
        proxy_pass $upstream_tickets;
    }
}

# ---------- Panel de agentes (UI server-rendered) ----------
location /panel {
    limit_req zone=api_limit burst=20 nodelay;
    proxy_pass $upstream_tickets;
}

# ---------- Monitoreo simple ----------
location /healthz {
    proxy_pass $upstream_chatbot;
}

# ---------- Estáticos del widget ----------
location /widget/ {
    alias /usr/share/nginx/html/widget/;
    expires 5m;
    add_header Cache-Control "public, max-age=300";
}

# Página de prueba del widget
location = /demo.html {
    root /usr/share/nginx/html/widget;
}

# ---------- Página de mantenimiento ----------
error_page 502 503 504 /maintenance.html;
location = /maintenance.html {
    root /usr/share/nginx/html;
    internal;
}
