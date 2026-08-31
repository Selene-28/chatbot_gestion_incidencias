# Manual de Despliegue e Instalación

Chatbot para la Gestión de Incidencias — **CTIC-FIIS UNAC**

Este manual está dirigido al personal de **DevOps / TI** que instala y opera el
sistema en el servidor de la universidad. Describe cómo levantar los servicios
con Docker, cómo configurarlos, cómo cargar la base de conocimiento, cómo
habilitar TLS en producción, y cómo hacer copias de seguridad, monitoreo,
actualizaciones y resolución de problemas.

> Todos los comandos se ejecutan desde la **raíz del repositorio** salvo que se
> indique lo contrario.

---

## 1. Requisitos del servidor

De `prd/07-despliegue.md` §1 (mínimos de producción):

| Recurso | Mínimo recomendado |
|---|---|
| Sistema operativo | Linux (Ubuntu Server 22.04+ o similar) |
| CPU | 2 vCPU |
| RAM | 4 GB (el modelo de embeddings usa ~0.5–1 GB) |
| Disco | 20 GB |
| Docker | Docker Engine **24+** y Docker Compose **v2** |
| Red saliente | Salida HTTPS hacia `api.anthropic.com` (para el LLM) |
| Dominio | Un subdominio institucional (ej. `chatbot.fiis.unac.edu.pe`) con certificado TLS |

Comprobar versiones:

```bash
docker --version          # Docker version 24.x o superior
docker compose version    # Docker Compose version v2.x
```

### Arquitectura de contenedores

El `docker-compose.yml` define cuatro servicios en una red interna de Docker:

| Servicio | Imagen / origen | Puerto interno | ¿Publicado al host? |
|---|---|---|---|
| `nginx` | `nginx:1.27-alpine` | 80 (y 443 en prod) | **Sí** — único punto de entrada |
| `chatbot-api` | build `./services/chatbot-api` | 8000 | No (solo red interna) |
| `ticket-service` | build `./services/ticket-service` | 8001 | No (solo red interna) |
| `mysql` | `mysql:8.4` | 3306 | No (solo red interna) |

Volúmenes persistentes: `mysql_data` (base de datos), `chroma_data` (índice
vectorial RAG del chatbot) y `uploads` (adjuntos de incidencias).

Solo Nginx expone puertos al exterior. Las peticiones se enrutan así (ver
`deploy/nginx/conf.d/default.conf`):

- `/api/chat/…`, `/api/faq`, `/api/kb`, `/api/metricas`, `/healthz` → `chatbot-api`
- `/api/incidencias`, `/api/encuesta`, `/api/auth`, `/api/panel`, `/panel` → `ticket-service`
- `/widget/…` y `/demo.html` → estáticos del widget

---

## 2. Instalación paso a paso

### 2.1 Clonar el repositorio

```bash
git clone <url-del-repositorio> chatbot-ctic
cd chatbot-ctic
```

### 2.2 Crear el archivo `.env`

El archivo `.env` **nunca se versiona** (está en `.gitignore`). Se crea a partir
de la plantilla `.env.example`:

```bash
cp .env.example .env
```

Luego editar `.env` y reemplazar **todos** los valores `cambiar`. Explicación de
cada variable:

| Variable | Para qué sirve | Recomendación |
|---|---|---|
| `DB_ROOT_PASSWORD` | Contraseña del usuario `root` de MySQL. La usa `db/init/01-init.sh` para crear los esquemas y usuarios por servicio. | Cadena larga y aleatoria. |
| `DB_CHATBOT_PASSWORD` | Contraseña del usuario MySQL `chatbot` (solo sobre `chatbot_db`, más `SELECT` sobre `tickets_db` para métricas). | Aleatoria, distinta de las demás. |
| `DB_TICKETS_PASSWORD` | Contraseña del usuario MySQL `tickets` (solo sobre `tickets_db`). | Aleatoria, distinta de las demás. |
| `TICKETS_API_BASE_URL` | URL base del Sistema de Tickets que consume el chatbot. En la tesis apunta al `ticket-service` simulado: `http://ticket-service:8001`. En producción real: la URL del sistema CTIC (ver manual `03-integracion-sistema-real.md`). | Dejar `http://ticket-service:8001` hasta integrar el sistema real. |
| `TICKETS_API_KEY` | Clave de servicio. El `chatbot-api` la envía en el header `X-Api-Key` y el `ticket-service` la valida. **Debe ser idéntica** en ambos lados (ambos leen la misma variable). | Cadena larga y aleatoria. |
| `ANTHROPIC_API_KEY` | Clave de la API de Claude (Anthropic) para la IA/RAG. Formato `sk-ant-...`. **Si se deja `cambiar` o vacía, el chatbot entra en modo degradado** (ver abajo). | La clave real emitida por Anthropic. |
| `LLM_MODEL` | Modelo principal (generación de respuestas RAG). Default `claude-opus-4-8`. | Dejar el default salvo indicación. |
| `LLM_MODEL_ROUTER` | Modelo económico para clasificar intenciones. Default `claude-haiku-4-5`. | Dejar el default. |
| `JWT_SECRET` | Secreto para firmar los tokens JWT del panel de agentes (HS256, 8 h). Lo emite `ticket-service` y lo valida `chatbot-api`; **debe ser el mismo valor** en ambos. | 64 caracteres aleatorios. |
| `ALLOWED_ORIGINS` | Orígenes CORS permitidos por el `chatbot-api`, separados por coma. Debe incluir el sitio donde se embebe el widget. | Ej. `https://fiis.unac.edu.pe` |
| `SEED_ADMIN_PASSWORD` | Contraseña inicial del usuario **administrador** del panel (se crea al aplicar las migraciones/seeds). | Cambiar tras el primer ingreso. |
| `SEED_TECNICO_PASSWORD` | Contraseña inicial de los usuarios **técnicos** del panel (seed). | Cambiar tras el primer ingreso. |
| `TZ` | Zona horaria. Todas las fechas se manejan en `America/Lima`. | Dejar `America/Lima`. |

Ejemplo para generar secretos robustos:

```bash
openssl rand -hex 32   # sirve para TICKETS_API_KEY, contraseñas de BD
openssl rand -hex 64   # sirve para JWT_SECRET
```

> **Modo degradado (sin `ANTHROPIC_API_KEY`):** el sistema **arranca y funciona**
> igual, pero sin IA. Los flujos guiados (registrar incidencia, consultar estado,
> escalar, encuesta) y los menús con botones operan con normalidad porque son
> deterministas. Lo que se pierde es la respuesta en lenguaje natural del RAG:
> `/healthz` reportará `"llm": "disabled"` y las preguntas abiertas caerán al
> flujo de fallback / handoff en lugar de responderse con un artículo. Esto
> permite hacer demos o mantener el servicio si la clave caduca. Al configurar la
> clave y reiniciar `chatbot-api`, la IA vuelve a estar disponible.

### 2.3 Levantar los servicios

```bash
docker compose up -d --build
```

Esto construye las imágenes, crea la red y los volúmenes, y arranca los cuatro
servicios. Notas importantes:

- **En el primer arranque**, `db/init/01-init.sh` crea los esquemas `chatbot_db`
  y `tickets_db` y los usuarios `chatbot` / `tickets` con mínimo privilegio.
- El `entrypoint.sh` de cada servicio **espera a que MySQL acepte conexiones**
  (hasta 30 intentos) y luego aplica las migraciones Alembic (`alembic upgrade
  head`) antes de arrancar Uvicorn. Los seeds del panel (usuario admin y
  técnicos) y los artículos mínimos de KB se crean en esas migraciones.
- Nginx solo arranca cuando `chatbot-api` y `ticket-service` están *healthy*.

Atajo equivalente con el `Makefile`: `make up`.

> **Desarrollo local:** existe un `docker-compose.override.yml` que Docker Compose
> carga automáticamente. Publica los puertos `8000`, `8001` y `3306` al host,
> monta el código con *hot-reload* y agrega **Adminer** en `http://localhost:8080`.
> **En producción no debe usarse** (para desplegar solo el compose base, use
> `docker compose -f docker-compose.yml up -d --build`).

### 2.4 Verificación

```bash
# Estado de los contenedores (todos "running"; api's "healthy")
docker compose ps

# Salud del chatbot-api a través de Nginx
curl http://localhost/healthz
# → {"status":"ok","db":"ok","llm":"configured"}   (o "llm":"disabled" en modo degradado)
```

Comprobaciones manuales en el navegador:

| Qué | URL |
|---|---|
| Página de prueba del widget | `http://<host>/demo.html` |
| Panel de agentes | `http://<host>/panel` |

En `demo.html` debe aparecer la burbuja del chat abajo a la derecha; al abrirla,
el bot saluda con el menú principal. En `/panel` debe cargar la pantalla de login.

---

## 3. Carga inicial de la base de conocimiento

Las migraciones dejan un conjunto **mínimo** de artículos. Para cargar el catálogo
completo (artículos provisionales, a validar con el CTIC) y construir el índice
vectorial, ejecutar el script dentro del contenedor `chatbot-api`:

```bash
docker compose exec chatbot-api python -m app.scripts.cargar_kb
```

Salida esperada (ejemplo):

```
Carga de la base de conocimiento (CONTENIDO PROVISIONAL — validar con el CTIC):
  - artículos creados:      16
  - artículos actualizados: 0
  - sin cambios:            0
  - artículos indexados:    16  (Chroma: /data/chroma)
```

El script es **idempotente**: se puede volver a ejecutar; solo crea los que faltan
y actualiza los que cambiaron (nunca borra artículos ajenos). Al terminar
reconstruye el índice Chroma.

Para reconstruir **solo el índice vectorial** (por ejemplo tras restaurar un
backup de MySQL sin el volumen `chroma_data`, o al cambiar el modelo de
embeddings):

```bash
docker compose exec chatbot-api python -m app.scripts.reindex
```

> A partir de ahí, la administración de artículos se hace en caliente desde el
> **panel de administración** (ver manual `02-manual-del-panel.md`), sin
> reiniciar: cada alta/edición reindexa el artículo afectado automáticamente.

---

## 4. TLS en producción

**Estado actual del repositorio:** el `docker-compose.yml` publica solo el puerto
`:80` y Nginx sirve en HTTP. Las líneas para `:443` y el volumen `certs` están
presentes pero **comentadas** (ver `docker-compose.yml` y
`deploy/nginx/conf.d/default.conf`). Esto es adecuado para desarrollo y demos,
pero **en producción es obligatorio HTTPS**.

Pasos para habilitar TLS:

1. **Obtener el certificado.** Dos caminos:
   - **Certificado institucional:** solicitar al área de infraestructura de la UNAC
     un certificado para el subdominio (ej. `chatbot.fiis.unac.edu.pe`). Se
     obtienen los archivos `fullchain.pem` (certificado + cadena) y `privkey.pem`
     (clave privada).
   - **Let's Encrypt (gratuito, automatizable):** con el subdominio apuntando al
     servidor y el puerto 80 accesible desde internet:
     ```bash
     sudo apt install certbot
     sudo certbot certonly --standalone -d chatbot.fiis.unac.edu.pe
     # certificados en /etc/letsencrypt/live/chatbot.fiis.unac.edu.pe/
     ```
     Programar la renovación automática (`certbot renew`) por cron y recargar Nginx
     tras renovar.

2. **Montar los certificados y habilitar `:443`.** En `docker-compose.yml`,
   descomentar en el servicio `nginx`:
   ```yaml
       ports:
         - "80:80"
         - "443:443"          # ← habilitar
       volumes:
         - ./deploy/nginx/conf.d:/etc/nginx/conf.d:ro
         - ./deploy/nginx/html/maintenance.html:/usr/share/nginx/html/maintenance.html:ro
         - ./widget/public:/usr/share/nginx/html/widget:ro
         - certs:/etc/nginx/certs:ro   # ← montar los certificados
   ```
   y descomentar el volumen `certs:` al final del archivo. Copiar
   `fullchain.pem` y `privkey.pem` a ese volumen (o montar directamente el
   directorio de Let's Encrypt).

3. **Añadir el `server` de TLS en Nginx.** En `deploy/nginx/conf.d/default.conf`
   agregar un bloque `server { listen 443 ssl; ... }` que apunte a
   `/etc/nginx/certs/fullchain.pem` y `/etc/nginx/certs/privkey.pem`, y redirigir
   el `:80` a `:443`. El resto de `location` (proxys a los upstreams) se reutiliza.

4. **Actualizar `ALLOWED_ORIGINS`** en `.env` para que use `https://…` y recargar:
   `docker compose up -d nginx chatbot-api`.

Ver `prd/07-despliegue.md` §2 y §7 para la topología y el snippet del widget en
el sitio institucional.

---

## 5. Copias de seguridad (backups)

Qué respaldar:

| Dato | Dónde vive | ¿Crítico? |
|---|---|---|
| Esquema `chatbot_db` (conversaciones, mensajes, KB, handoffs) | volumen `mysql_data` | Sí |
| Esquema `tickets_db` (incidencias, usuarios, encuestas, historial) | volumen `mysql_data` | Sí |
| Adjuntos de incidencias | volumen `uploads` | Sí |
| Índice vectorial Chroma | volumen `chroma_data` | **No** — se reconstruye con `reindex` |

### Respaldo (recomendado: diario, retención 30 días)

```bash
# 1. Dump de ambos esquemas (un solo archivo comprimido)
docker compose exec -T mysql \
  mysqldump -u root -p"$DB_ROOT_PASSWORD" --databases chatbot_db tickets_db \
  | gzip > backup-db-$(date +%F).sql.gz

# 2. Respaldo del volumen de adjuntos
docker run --rm \
  -v chatbot-ctic_uploads:/data:ro \
  -v "$(pwd)":/backup alpine \
  tar czf /backup/backup-uploads-$(date +%F).tar.gz -C /data .
```

> El prefijo del volumen es el `name:` del compose (`chatbot-ctic`) más el nombre
> del volumen. Confirmar con `docker volume ls`.

Guardar ambos archivos en el almacenamiento del CTIC. El índice Chroma **no se
respalda**: tras restaurar se regenera con `python -m app.scripts.reindex`.

### Restauración

```bash
# Base de datos
gunzip < backup-db-2026-07-01.sql.gz | \
  docker compose exec -T mysql mysql -u root -p"$DB_ROOT_PASSWORD"

# Adjuntos
docker run --rm \
  -v chatbot-ctic_uploads:/data \
  -v "$(pwd)":/backup alpine \
  sh -c "cd /data && tar xzf /backup/backup-uploads-2026-07-01.tar.gz"

# Reconstruir el índice RAG
docker compose exec chatbot-api python -m app.scripts.reindex
```

**Probar la restauración periódicamente** en un entorno aparte: un backup que
nunca se ha restaurado no es un backup confiable.

---

## 6. Monitoreo

- **Healthchecks de Docker:** ambos servicios de API tienen healthcheck integrado
  (cada 30 s). `docker compose ps` muestra `healthy` / `unhealthy`.
- **Endpoint `/healthz`** (en ambos servicios): responde
  `{"status": "...", "db": "ok", "llm": "configured|degraded|disabled"}`.
  - `db` distinto de `ok` → problema de conexión a MySQL.
  - `llm: "degraded"` → el *circuit breaker* del LLM está abierto (tras 3 fallos
    consecutivos a la API de Claude, se abre 60 s). Suele ser transitorio.
  - `llm: "disabled"` → no hay `ANTHROPIC_API_KEY` configurada (modo degradado).
- **Alerta simple recomendada** (`prd/07` §6): un cron que consulte `/healthz` cada
  pocos minutos y envíe correo al CTIC si el estado no es saludable.
- **Logs:** JSON estructurado a stdout. Consultar con `docker compose logs -f`
  (o por servicio: `docker compose logs -f chatbot-api`). En producción, configurar
  rotación del driver de logs (`max-size 10m`, `max-file 5`).
- **Costo del LLM:** el panel de métricas incluye el contador de tokens consumidos
  para vigilar el presupuesto de la API.

---

## 7. Actualización de versión y rollback

El despliegue usa imágenes construidas desde el repositorio. Flujo de
actualización:

```bash
# 1. Traer la nueva versión del código (tag de release)
git fetch --tags
git checkout v0.2.0

# 2. Reconstruir y recrear los contenedores (las migraciones Alembic corren
#    automáticamente en el entrypoint, con espera a MySQL)
docker compose up -d --build

# 3. Smoke test
curl http://localhost/healthz
```

**Rollback:** volver al tag anterior y recrear.

```bash
git checkout v0.1.0
docker compose up -d --build
```

Recomendaciones:

- Desplegar **solo versiones etiquetadas** (`v0.1.0`, `v0.2.0`, …), nunca ramas en
  movimiento.
- Las migraciones se aplican con espera/reintentos hacia MySQL y abortan ante un
  error real de SQL (el DDL de MySQL no es transaccional). Antes de una
  actualización que incluya migraciones, **hacer un backup de la BD** (sección 5).
- Si el sistema real de tickets se integró (manual 03), un rollback del chatbot no
  toca esa base: solo cambia la imagen del `chatbot-api`.

---

## 8. Solución de problemas comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Un contenedor no arranca / reinicia en bucle | Falta una variable en `.env` o tiene valor inválido | `docker compose logs <servicio>`; verificar que todas las variables `cambiar` fueron reemplazadas. |
| `chatbot-api` / `ticket-service` no conectan a MySQL | MySQL aún inicializando o contraseña incorrecta | El entrypoint reintenta 30 veces. Si persiste, revisar `DB_*_PASSWORD` y `docker compose logs mysql`. |
| Error de permisos en MySQL tras cambiar contraseñas | El init `01-init.sh` solo corre en el **primer** arranque (volumen vacío) | Para reinicializar usuarios/esquemas: `docker compose down -v` **borra los datos** y vuelve a ejecutar el init; usar solo en entornos sin datos que conservar. |
| Nginx responde 502 / página de mantenimiento | Un upstream (`chatbot-api`/`ticket-service`) está caído o no *healthy* | `docker compose ps`; revisar logs del servicio afectado. Nginx sirve `maintenance.html` en 502/503/504. |
| `/healthz` reporta `"llm": "disabled"` | No hay `ANTHROPIC_API_KEY` | Es el **modo degradado** esperado. Configurar la clave en `.env` y `docker compose up -d chatbot-api`. |
| `/healthz` reporta `"llm": "degraded"` | *Circuit breaker* abierto tras fallos de la API de Claude | Suele ser transitorio (se cierra a los 60 s). Verificar salida a `api.anthropic.com`, cuota y validez de la clave. |
| El bot no responde preguntas abiertas (siempre cae a fallback) | LLM en modo degradado, o la KB no está indexada | Revisar `/healthz`; ejecutar `python -m app.scripts.cargar_kb` / `reindex`. |
| Los mensajes del agente no llegan al usuario en vivo (SSE) | Buffering del proxy o timeout corto en la ruta SSE | El bloque `location /api/chat/` de Nginx ya desactiva buffering y usa `proxy_read_timeout 1h`. Verificar que no haya otro proxy/CDN intermedio que corte conexiones largas o haga buffer. |
| Imagen de Docker muy grande / build lento | El modelo de embeddings se descarga en build (capa cacheada) | Es esperado la primera vez. Los builds siguientes reutilizan la capa. No borrar la caché de Docker innecesariamente. |
| Adjuntos rechazados | Tamaño > 5 MB o tipo no permitido | Se aceptan JPG/JPEG/PNG/PDF ≤ 5 MB. Nginx limita el cuerpo a 6 MB (`client_max_body_size`). |

---

## 9. Referencia rápida de comandos

```bash
docker compose up -d --build          # levantar / actualizar
docker compose ps                     # estado de los contenedores
docker compose logs -f chatbot-api    # logs en vivo de un servicio
docker compose exec chatbot-api python -m app.scripts.cargar_kb   # cargar KB
docker compose exec chatbot-api python -m app.scripts.reindex     # reindexar RAG
docker compose down                   # detener (conserva volúmenes/datos)
docker compose down -v                # detener y BORRAR volúmenes (¡destruye datos!)
```
</content>
</invoke>
