# PRD 07 — Contenedores y Despliegue

---

## 1. Evaluación: ¿por qué contenedores? (decisión ADR-07)

El objetivo declarado es llevar la propuesta a **producción dentro del sistema de la universidad**. Opciones evaluadas:

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| **Docker + docker-compose** | Despliegue reproducible (misma imagen en dev/tesis/prod); aislamiento del servidor existente (que corre XAMPP/PHP sin conflicto de versiones); rollback = volver a la imagen anterior; secretos y config por entorno; healthchecks y reinicio automático; curva de adopción baja para el personal CTIC | Requiere Docker Engine en el servidor; disciplina de volúmenes/backups | ✅ **Elegido** |
| Instalación nativa (systemd + venv + MySQL del host) | Sin dependencia de Docker | Conflictos con el stack existente; "funciona en mi máquina"; despliegue manual propenso a errores; difícil rollback | ❌ |
| Kubernetes (k3s) | Escalado y auto-reparación | Complejidad totalmente desproporcionada para 2 servicios y un servidor | ❌ (documentado como evolución futura si la universidad centraliza infraestructura) |
| PaaS externo (Railway/Render/Fly) | Cero administración | Datos personales de la comunidad universitaria fuera de la infraestructura institucional (riesgo de cumplimiento — Ley N.º 29733 de Protección de Datos Personales); costo recurrente | ❌ para producción; ✔ aceptable para demo temporal de la tesis |

**Requisitos del servidor de producción (mínimos):** Linux (Ubuntu Server 22.04+ o similar), 2 vCPU, 4 GB RAM (el modelo de embeddings usa ~0.5–1 GB), 20 GB disco, Docker Engine 24+ y Docker Compose v2, salida HTTPS hacia `api.anthropic.com`, y un subdominio institucional (ej. `chatbot.fiis.unac.edu.pe`) con certificado TLS.

## 2. Topología de despliegue

```mermaid
flowchart TB
    subgraph inet["Internet / red universitaria"]
        USR["Usuarios (widget en el sitio FIIS)"]
        STAFF["Personal CTIC (panel)"]
    end
    subgraph host["Servidor universitario (Linux + Docker)"]
        subgraph net["red docker interna (bridge)"]
            NG["nginx<br/>:80/:443 (únicos puertos publicados)"]
            CA["chatbot-api :8000<br/>(interno)"]
            TS["ticket-service :8001<br/>(interno)"]
            MY["mysql :3306<br/>(interno)"]
        end
        V1[("vol: mysql_data")]
        V2[("vol: chroma_data")]
        V3[("vol: uploads")]
        V4[("vol: certs")]
    end
    ANT["☁️ api.anthropic.com"]

    USR & STAFF -->|HTTPS| NG
    NG --> CA & TS
    CA --> TS
    CA --> MY
    TS --> MY
    CA -->|HTTPS saliente| ANT
    MY --- V1
    CA --- V2
    TS --- V3
    NG --- V4
```

## 3. `docker-compose.yml` (referencia)

```yaml
name: chatbot-ctic

services:
  nginx:
    image: nginx:1.27-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./deploy/nginx/conf.d:/etc/nginx/conf.d:ro
      - certs:/etc/nginx/certs:ro
      - ./widget/dist:/usr/share/nginx/html/widget:ro
    depends_on: [chatbot-api, ticket-service]
    restart: unless-stopped

  chatbot-api:
    build: ./services/chatbot-api
    env_file: .env
    environment:
      DB_URL: mysql+asyncmy://chatbot:${DB_CHATBOT_PASSWORD}@mysql:3306/chatbot_db
      TICKETS_API_BASE_URL: http://ticket-service:8001   # ← en prod real: URL del sistema CTIC
      TICKETS_API_KEY: ${TICKETS_API_KEY}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      LLM_MODEL: ${LLM_MODEL:-claude-opus-4-8}
      LLM_MODEL_ROUTER: ${LLM_MODEL_ROUTER:-claude-haiku-4-5}
      CHROMA_DIR: /data/chroma
      ALLOWED_ORIGINS: ${ALLOWED_ORIGINS}
    volumes: [chroma_data:/data/chroma]
    depends_on:
      mysql: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8000/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  ticket-service:
    build: ./services/ticket-service
    env_file: .env
    environment:
      DB_URL: mysql+asyncmy://tickets:${DB_TICKETS_PASSWORD}@mysql:3306/tickets_db
      JWT_SECRET: ${JWT_SECRET}
      UPLOADS_DIR: /data/uploads
    volumes: [uploads:/data/uploads]
    depends_on:
      mysql: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8001/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  mysql:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
      - ./db/init:/docker-entrypoint-initdb.d:ro   # crea esquemas y usuarios por-servicio
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-p${DB_ROOT_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 10
    restart: unless-stopped

volumes:
  mysql_data:
  chroma_data:
  uploads:
  certs:
```

Notas:
- **Un usuario MySQL por servicio** con permisos solo sobre su esquema (mínimo privilegio).
- MySQL **no publica** el puerto 3306 al host; solo la red interna.
- Dockerfiles multi-stage (imagen final `python:3.12-slim`, usuario no-root, `--no-cache-dir`). El modelo de embeddings se descarga en build (capa cacheada) para que el arranque no dependa de internet.
- `docker-compose.override.yml` para desarrollo (hot-reload, puertos expuestos, Adminer).

## 4. Configuración por entorno (`.env.example`)

```dotenv
# Base de datos
DB_ROOT_PASSWORD=cambiar
DB_CHATBOT_PASSWORD=cambiar
DB_TICKETS_PASSWORD=cambiar

# Integración tickets (ADR-03: apuntar al sistema real en producción)
TICKETS_API_BASE_URL=http://ticket-service:8001
TICKETS_API_KEY=cambiar

# LLM
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-opus-4-8
LLM_MODEL_ROUTER=claude-haiku-4-5

# Seguridad
JWT_SECRET=cambiar-64-chars-aleatorios
ALLOWED_ORIGINS=https://fiis.unac.edu.pe

# Zona horaria
TZ=America/Lima
```

## 5. Pipeline de despliegue

```mermaid
flowchart LR
    DEV["Commit en rama main"] --> CI["CI (GitHub Actions):<br/>lint + tests unitarios<br/>+ suite E2E (QA-01..11)<br/>+ build de imágenes"]
    CI --> REG["Registro de imágenes<br/>(GHCR) con tag semver"]
    REG --> PROD["Servidor universitario:<br/>docker compose pull && up -d<br/>(migraciones Alembic al arrancar)"]
    PROD --> SMOKE["Smoke test:<br/>/healthz + conversación de prueba"]
    SMOKE -->|falla| RB["Rollback: tag anterior"]
```

- Las migraciones corren en el entrypoint con lock (aptas para reinicios).
- Releases etiquetadas (`v0.1.0`, …); producción solo despliega tags.

## 6. Operación

| Tema | Práctica |
|---|---|
| Backups | `mysqldump` diario de ambos esquemas + tar de `uploads` → almacenamiento del CTIC; retención 30 días; restauración documentada y probada. Chroma se puede reconstruir con `reindex` (no crítico). |
| Logs | JSON estructurado a stdout → `docker logs` / driver `local` con rotación (`max-size 10m, max-file 5`). |
| Monitoreo | Healthchecks Docker + cron sencillo que consulta `/healthz` y alerta por correo al CTIC si hay `degraded/down`. |
| Mantenimiento | Ventana declarada (REN-03); página estática de mantenimiento servida por Nginx cuando el backend está abajo. |
| Actualización de KB | Vía panel admin en caliente (RF-12), sin reinicio. |
| Costo LLM | Panel de métricas incluye tokens consumidos/día (contador propio) para vigilar presupuesto. |

## 7. Ruta de integración con el sistema real (producción)

1. **Hoy (tesis):** `TICKETS_API_BASE_URL` apunta al `ticket-service` simulado del compose.
2. **Integración:** el equipo CTIC implementa API-01, API-02 y API-03 (contratos exactos de `prd/04` §3) sobre su sistema PHP/MySQL — puede reutilizar el `ticket-service` de este repo como referencia o como **adaptador** (contenedor que traduce REST → BD MySQL del sistema real).
3. **Switch:** cambiar `TICKETS_API_BASE_URL` + `TICKETS_API_KEY` en `.env`, `docker compose up -d chatbot-api`. El esquema `tickets_db` local queda solo para el panel de handoffs o se retira.
4. **Widget:** el sitio institucional agrega el snippet:
   ```html
   <script src="https://chatbot.fiis.unac.edu.pe/widget/widget.js"
           data-api="https://chatbot.fiis.unac.edu.pe/api" defer></script>
   ```
5. **Identificación fuerte (posterior):** si la universidad lo aprueba, activar verificación por código al correo institucional o SSO — punto de extensión previsto en `prd/02` §7.
