# Integración del Chatbot en WordPress (FIIS–UNAC)

**Asistente Virtual del CTIC** — botón flotante en todas las páginas del sitio
institucional WordPress.

Este documento responde, en un solo lugar, a lo pedido para entrega e
integración: código, instalación, script, URLs, API, dependencias, ejecución
local/producción, actualización de la base de conocimiento y confirmación de
compatibilidad con WordPress.

---

## 0. Confirmación: ¿se puede integrar como botón flotante en WordPress?

**Sí.** El widget ya es un **botón flotante** (burbuja 💬 abajo a la derecha)
que se inyecta en cualquier página HTML/WordPress con **una sola línea** de
script. No requiere plugin de chat de terceros ni Node.js en el sitio FIIS.

Al cargar `widget.js`, el script:

1. Inyecta sus estilos (`widget.css`).
2. Crea el botón flotante y la ventana de chat.
3. Habla con la API del chatbot (`data-api`).

Funciona en temas clásicos y block themes, siempre que el script se cargue en
todas las páginas (recomendado: pie de página / `wp_footer`).

---

## 1. Código fuente completo del chatbot

El código vive en este repositorio. Partes relevantes:

| Componente | Ruta |
|---|---|
| Widget (HTML demo, JS, CSS) | `widget/public/` → `demo.html`, `widget.js`, `widget.css` |
| Backend conversacional + IA/RAG | `services/chatbot-api/` |
| Backend tickets + panel staff | `services/ticket-service/` |
| Proxy / estáticos (producción) | `deploy/nginx/` |
| Especificación API | `prd/04-api.md` |
| Despliegue | `manuales/01-despliegue.md`, `prd/07-despliegue.md` |
| Panel (KB, tickets, handoffs) | `manuales/02-manual-del-panel.md` |

**Entrega ZIP:** use el archivo
`chatbot_gestion_tickets-INTEGRACION-WORDPRESS.zip` (carpeta Downloads) o el
ZIP más reciente del proyecto. Incluye HTML, CSS, JS, backends Python, PRD,
manuales, e2e y scripts.

Snippet listo para WordPress (también en disco):

- `widget/wordpress-snippet.html`

---

## 2. Manual de instalación paso a paso (visión general)

### A. Levantar el backend (servidor del chatbot)

1. Requisitos: Linux (prod) o Windows/macOS (dev), **Docker Engine 24+** y
   **Docker Compose v2**, 2 vCPU / 4 GB RAM / 20 GB disco (mínimo prod).
2. Clonar o descomprimir el proyecto.
3. Copiar entorno: `cp .env.example .env` y reemplazar todos los `cambiar`.
4. Arrancar:

```bash
docker compose up -d --build
docker compose exec -T chatbot-api python -m app.scripts.cargar_kb
```

5. Verificar: `curl http://localhost/healthz`
6. Probar widget: `http://localhost/demo.html`
7. Panel: `http://localhost/panel` → `admin@ctic.local` / (password del `.env`)

Detalle completo: `manuales/01-despliegue.md`.

### B. Integrar en WordPress (sitio FIIS)

1. Desplegar el chatbot en un **subdominio HTTPS** (ej.
   `https://chatbot.fiis.unac.edu.pe`).
2. En WordPress, pegar el script de la sección 3 (abajo) para que cargue en
   **todas** las páginas.
3. Probar en una página pública: debe aparecer la burbuja 💬.
4. Abrir el chat y verificar menú / FAQ / registro.

---

## 3. Script de integración (HTML / JavaScript)

### Producción (recomendado)

```html
<!-- Asistente Virtual CTIC — botón flotante en todas las páginas -->
<script
  src="https://chatbot.fiis.unac.edu.pe/widget/widget.js"
  data-api="https://chatbot.fiis.unac.edu.pe/api"
  defer>
</script>
```

### Desarrollo local (solo en su PC; no pegar esto en WordPress de producción)

Sirva `widget/public/` (ej. puerto 5500) y use:

```html
<script
  src="http://127.0.0.1:5500/widget.js"
  data-api="http://127.0.0.1:8000/api"
  defer>
</script>
```

> En producción WordPress **siempre** use HTTPS y configure `ALLOWED_ORIGINS`
> con el dominio real del sitio FIIS (si no, el navegador mostrará
> “No se pudo conectar con el asistente”).

### Cómo insertarlo en WordPress (elige una)

**Opción A — Plugin “Insert Headers and Footers” / Code Snippets (recomendada)**  
1. Instalar el plugin.  
2. Pegar el `<script …>` en **Footer** (todas las páginas).  
3. Guardar.

**Opción B — `functions.php` del tema hijo**

```php
<?php
add_action('wp_footer', function () {
    ?>
    <script
      src="https://chatbot.fiis.unac.edu.pe/widget/widget.js"
      data-api="https://chatbot.fiis.unac.edu.pe/api"
      defer></script>
    <?php
});
```

**Opción C — Bloque HTML personalizado en plantilla / Elementor**  
Pegar el mismo `<script>` en un bloque que se renderice en todo el sitio
(no solo en una página).

---

## 4. URL del chatbot (servidor)

| Entorno | URL widget / demo | URL panel | Health |
|---|---|---|---|
| **Producción (ejemplo institucional)** | `https://chatbot.fiis.unac.edu.pe/widget/widget.js` y sitio FIIS embebe el script | `https://chatbot.fiis.unac.edu.pe/panel` | `https://chatbot.fiis.unac.edu.pe/healthz` |
| **Local con Docker + nginx** | `http://localhost/demo.html` | `http://localhost/panel` | `http://localhost/healthz` |
| **Local sin Docker (dev actual)** | `http://127.0.0.1:5500/demo.html` | `http://127.0.0.1:8001/panel` | `http://127.0.0.1:8000/healthz` |

El sitio WordPress de la FIIS **no aloja** el backend: solo carga el JS desde
la URL del chatbot.

---

## 5. API — documentación y credenciales

### Documentación

| Recurso | Ubicación |
|---|---|
| Contrato completo | `prd/04-api.md` |
| Swagger local chatbot | `http://localhost:8000/docs` (o `:8000` sin nginx) |
| Swagger tickets | `http://localhost:8001/docs` |
| Contrato widget | `widget/README.md` |

### Endpoints que usa el widget (públicos vía navegador)

| Método | Ruta | Auth |
|---|---|---|
| `POST` | `/api/chat/sesiones` | Ninguna (crea sesión) |
| `POST` | `/api/chat/mensajes` | Header `X-Session-Token` |
| `POST` | `/api/chat/adjuntos` | Header `X-Session-Token` |
| `GET` | `/api/chat/stream` | Query `token` + `sessionId` (SSE) |

Envelope de respuesta: `{ success, code, message, data }`.

### Credenciales

| Uso | Credencial | Notas |
|---|---|---|
| **Widget en WordPress** | **No requiere usuario/contraseña** | El visitante abre el chat; la sesión se crea sola. |
| Panel staff | `admin@ctic.local` / password de `SEED_ADMIN_PASSWORD` | Solo personal CTIC. |
| API tickets (servicio a servicio) | Header `X-Api-Key: <TICKETS_API_KEY>` | Lo usa `chatbot-api` → `ticket-service`; **no** se pone en WordPress. |
| JWT panel | Cookie `panel_token` (mismo `JWT_SECRET`) | Solo panel / admin KB. |
| LLM (opcional) | `ANTHROPIC_API_KEY` | Sin ella el sistema opera en modo degradado (válido). |

**Importante:** no incruste `TICKETS_API_KEY` ni `JWT_SECRET` en WordPress.

### CORS (obligatorio si WordPress y chatbot están en dominios distintos)

En `chatbot-api`, variable `ALLOWED_ORIGINS`, por ejemplo:

```text
https://fiis.unac.edu.pe,https://www.fiis.unac.edu.pe,https://chatbot.fiis.unac.edu.pe
```

Luego recrear el servicio: `docker compose up -d --force-recreate chatbot-api`.

---

## 6. Archivos del proyecto (ZIP)

Generar/entregar el ZIP desde la raíz del repo (excluyendo `.venv` y cachés):

Contenido esperado:

- `widget/public/` — HTML, CSS, JS del botón flotante  
- `services/chatbot-api/` — backend FastAPI + RAG  
- `services/ticket-service/` — tickets + panel  
- `deploy/` — nginx, TLS  
- `prd/`, `manuales/`, `e2e/`, `evidencia/`, `db/`  
- `docker-compose.yml`, `.env.example`, `README.md`

---

## 7. Dependencias y requisitos

| Capa | Tecnología |
|---|---|
| Widget | **Ninguna** en el navegador (JS/CSS vanilla). WordPress no necesita Node. |
| Backend | **Python 3.12**, **uv**, FastAPI, MySQL 8, ChromaDB, embeddings `multilingual-e5-small` |
| Orquestación recomendada | **Docker** + **Docker Compose v2** + **Nginx** |
| Opcional | Clave **Anthropic** (LLM); sin ella funciona en modo degradado |
| WordPress | Cualquier WP reciente; solo debe poder insertar un `<script>` en el footer |

No se requiere Node.js ni React para el widget.

---

## 8. Ejecución local y en producción

### Local (Docker — recomendado para demos)

```bash
cp .env.example .env
# editar secretos
docker compose up -d --build
docker compose exec -T chatbot-api python -m app.scripts.cargar_kb
# abrir http://localhost/demo.html  y  http://localhost/panel
```

### Local sin Docker (como en desarrollo Windows)

1. MySQL 8 local con `chatbot_db` y `tickets_db`.  
2. `ticket-service` en `:8001`, `chatbot-api` en `:8000`.  
3. Servir `widget/public` (ej. puerto 5500).  
4. CORS debe incluir `http://127.0.0.1:5500`.

### Producción

```bash
# certificados en deploy/certs + tls.conf (ver manual 01)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec -T chatbot-api python -m app.scripts.cargar_kb
```

Luego pegar el script HTTPS en WordPress (sección 3).

---

## 9. Actualizar la base de conocimiento

### Ya se puede (sin redeploy del widget)

**Vía panel (recomendado en producción):**

1. Entrar a `https://<host>/panel` como **admin**.  
2. Ir a **Base de conocimiento**.  
3. Crear / editar / desactivar artículos (título, contenido, categoría, etiquetas).  
4. El índice vectorial se actualiza en caliente (RF-12); si hace falta
   reconstrucción total: acción de **reindex** en el panel o:

```bash
docker compose exec -T chatbot-api python -m app.scripts.reindex
```

**Vía script (carga masiva inicial):**

```bash
docker compose exec -T chatbot-api python -m app.scripts.cargar_kb
```

Los artículos fuente están en `services/chatbot-api/app/scripts/datos_kb.py`.

### WordPress

WordPress **no** edita la KB. Quien actualiza FAQs / info FIIS es el personal
CTIC desde el **panel**, o DevOps con los scripts anteriores.

---

## 10. Checklist de entrega al área de TI / FIIS

- [ ] Backend chatbot desplegado con HTTPS  
- [ ] `ALLOWED_ORIGINS` incluye el dominio WordPress de la FIIS  
- [ ] Script del footer WordPress publicado en todas las páginas  
- [ ] Burbuja 💬 visible en inicio y en una página interna  
- [ ] Chat crea sesión y muestra menú  
- [ ] Panel accesible solo a staff; KB editable por admin  
- [ ] Credenciales de servicio **no** expuestas en el tema WP  

---

## Contacto técnico de referencia (proyecto)

- Widget: `widget/README.md`  
- Despliegue: `manuales/01-despliegue.md`  
- Panel / KB: `manuales/02-manual-del-panel.md`  
- Integración tickets reales: `manuales/03-integracion-sistema-real.md`  
- Este documento: `manuales/04-integracion-wordpress-fiis.md`
