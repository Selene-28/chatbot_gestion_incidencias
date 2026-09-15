# Subir el chatbot a internet con Railway (paso a paso)

Esta guía es para **una persona que no programa**. No instales Docker ni Python
en tu PC. El código ya está en GitHub.

**Qué vas a lograr:** una dirección `https://algo.up.railway.app` donde abre el
chat (`/demo.html`) y el panel del personal (`/panel`). Después pegas un botón
en la web de la FIIS (o en cualquier página).

**Tiempo:** la primera vez, 30–60 minutos de clics + 15–25 minutos de espera
mientras Railway construye la parte de inteligencia (es normal).

**Costo:** plan **Hobby** de Railway (tarjeta; unos 5 USD/mes de base, y un poco
más según uso). Este chatbot **no cabe** en el plan gratuito: se queda sin
memoria o se apaga.

**Producción en la universidad:** Railway sirve para la tesis y para demos. Los
datos de alumnos/docentes, a largo plazo, deberían vivir en un servidor de la
UNAC (Ley 29733).

---

## Vídeos (para ver la pantalla de Railway)

No hay un vídeo de *este* chatbot. Estos dos enseñan **solo** a entrar a
Railway y a conectar GitHub. La parte de los **cuatro servicios** la haces con
esta guía (abajo), no con el vídeo.

1. Cómo entrar a Railway y elegir un repo de GitHub (el ejemplo es Node; **no
   copies su código**):  
   <https://www.youtube.com/watch?v=U2zkg410twQ>
2. Misma idea, otro recorrido de cuenta + GitHub:  
   <https://www.youtube.com/watch?v=UWRsyP7iAnU>

Pausa el vídeo cuando elijan el repositorio. A partir de ahí, **sigue esta
página**: nuestro proyecto son **4 cajas**, no una.

Documentación oficial (en inglés, con dibujos):  
<https://docs.railway.com/guides/getting-started>  
<https://docs.railway.com/guides/docker-compose>

---

## Antes de empezar (checklist)

- [ ] Tienes cuenta de **GitHub** (ya usas `Selene-28/chatbot_gestion_incidencias`).
- [ ] Puedes pagar el plan Hobby de Railway (tarjeta).
- [ ] Vas a usar la rama que tenga esta guía. Hoy:  
      `cursor/demo-api-same-origin-2754`  
      Cuando se una a `master`, usa `master`.
- [ ] Anota en un papel las contraseñas que vas a inventar (no las publiques).

---

## Paso 1 — Crear la cuenta

1. Abre <https://railway.com> (o <https://railway.app>).
2. Pulsa **Login** / **Start a New Project**.
3. Elige **Login with GitHub** y acepta los permisos.
4. Si pide un plan, elige **Hobby** (no Trial/Free para este proyecto).

---

## Paso 2 — Proyecto vacío

1. **New Project**.
2. Elige **Empty project** (proyecto vacío).  
   No elijas “Deploy from GitHub” todavía: si lo haces, Railway intentará
   adivinar **un** programa y este sistema son **cuatro**.
3. Arriba, ponle nombre al proyecto, por ejemplo `chatbot-ctic`.

---

## Paso 3 — Variables compartidas (contraseñas)

Estas claves las usan varias cajas. Se pegan **una vez** en el proyecto.

1. En el proyecto, abre **Variables** (o **Shared Variables** / variables
   compartidas).
2. Pulsa **Raw Editor** (editor en bruto).
3. Abre en GitHub el archivo  
   [`deploy/railway/variables.compartidas.env`](../deploy/railway/variables.compartidas.env).
4. Cópialo, **cambia todos los `CAMBIAR-...`** por frases secretas largas.
5. Pégalo y guarda.

`ANTHROPIC_API_KEY` puede quedarse en `cambiar`: el chat funciona igual, sin
redacción “bonita” de IA. Si más adelante tienes una clave `sk-ant-...`, la
pones aquí y vuelves a desplegar **chatbot-api**.

---

## Paso 4 — Crear las 4 cajas (servicios)

Vas a pulsar **+ New** cuatro veces. **El nombre tiene que ser exacto**
(minúsculas, con guion). Si le pones otro nombre, las cajas no se encuentran.

| Orden | Nombre del servicio | Qué es, en simple |
|---|---|---|
| 1 | `mysql` | La base de datos (memoria de tickets y chats) |
| 2 | `ticket-service` | Tickets y panel del personal |
| 3 | `chatbot-api` | El cerebro del chat |
| 4 | `nginx` | La puerta de internet (la única pública) |

### 4.1 Caja `mysql`

1. **+ New** → **GitHub Repo**.
2. Elige `chatbot_gestion_incidencias`. Si no aparece: **Configure GitHub App**
   y dale acceso a ese repo.
3. **Settings** del servicio:
   - **Service name:** `mysql`
   - **Source → Branch:** la rama de esta guía (ver “Antes de empezar”).
   - **Root Directory:** vacío / `/` (la raíz).
   - **Build → Dockerfile path:** `db/Dockerfile`
4. **Settings → Volumes → Add Volume**
   - Mount path: `/var/lib/mysql`
5. Espera a que el deploy diga **Success**. La primera vez tarda un poco.

### 4.2 Caja `ticket-service`

1. **+ New** → **GitHub Repo** → el mismo repo.
2. **Settings:**
   - Nombre: `ticket-service`
   - Branch: la misma.
   - **Root Directory:** `services/ticket-service`
3. **Variables** (además de las compartidas), pega:

```
DB_URL=mysql+asyncmy://tickets:${{DB_TICKETS_PASSWORD}}@mysql.railway.internal:3306/tickets_db
UPLOADS_DIR=/data/uploads
```

4. **Volume:** mount path `/data/uploads`
5. **Settings → Resources:** 512 MB alcanza.

### 4.3 Caja `chatbot-api`

1. **+ New** → **GitHub Repo** → el mismo repo.
2. **Settings:**
   - Nombre: `chatbot-api`
   - Branch: la misma.
   - **Root Directory:** `services/chatbot-api`
3. **Variables:**

```
DB_URL=mysql+asyncmy://chatbot:${{DB_CHATBOT_PASSWORD}}@mysql.railway.internal:3306/chatbot_db
TICKETS_API_BASE_URL=http://ticket-service.railway.internal:8001
CHROMA_DIR=/data/chroma
CARGAR_KB_AL_ARRANCAR=1
```

4. **Volume:** `/data/chroma`
5. **Resources:** pon **al menos 2 GB de RAM**. Si dejas 512 MB, se cae al
   cargar el modelo.
6. El **primer build tarda 15–25 minutos**. Toma un té. En **Deployments** debe
   terminar en verde.

### 4.4 Caja `nginx` (la puerta)

1. **+ New** → **GitHub Repo** → el mismo repo.
2. **Settings:**
   - Nombre: `nginx`
   - Branch: la misma.
   - **Root Directory:** vacío / `/`
   - **Dockerfile path:** `deploy/nginx/Dockerfile`
3. **Variables:**

```
CHATBOT_UPSTREAM=http://chatbot-api.railway.internal:8000
TICKETS_UPSTREAM=http://ticket-service.railway.internal:8001
```

4. **Settings → Networking → Generate Domain**.  
   Te da algo como `https://chatbot-ctic-production.up.railway.app`.
5. Copia esa URL.
6. En la caja **chatbot-api** → Variables, añade:

```
PUBLIC_APP_URL=https://TU-URL.up.railway.app
```

   (sin barra al final). Guarda: Railway vuelve a desplegar **chatbot-api**.

7. Si en Networking te pide **puerto**, usa el que Railway asigne (`PORT`) o
   **80**. Nuestra puerta escucha los dos.

---

## Paso 5 — Probar

Abre en el navegador (cambia la URL por la tuya):

| Dirección | Qué deberías ver |
|---|---|
| `https://TU-URL/healthz` | Un texto con `"status"` y `"db"` en ok |
| `https://TU-URL/demo.html` | Página de prueba y burbuja de chat abajo a la derecha |
| `https://TU-URL/panel` | Login del personal |

Usuario del panel (desarrollo): `admin@ctic.local`  
Contraseña: la que pusiste en `SEED_ADMIN_PASSWORD`.

Si `/healthz` dice `llm: disabled`, es normal sin clave de Anthropic.

Si ves “mantenimiento” o 502: espera 1–2 minutos y mira **Logs** de
`chatbot-api` (a veces MySQL aún está arrancando). Recarga.

---

## Paso 6 — Poner el botón en tu página web

Cuando el paso 5 funcione, en WordPress (pie de **todas** las páginas):

```html
<script
  src="https://TU-URL/widget/widget.js"
  data-api="https://TU-URL/api"
  defer>
</script>
```

Plugin fácil: **Insert Headers and Footers** o **Code Snippets** → Footer.

Además, en **chatbot-api** → `ALLOWED_ORIGINS`, agrega el dominio de la FIIS
si aún no está, por ejemplo:

`https://fiis.unac.edu.pe,https://www.fiis.unac.edu.pe`

y también tu `https://TU-URL.up.railway.app` (o deja `PUBLIC_APP_URL`, que ya
lo cubre).

---

## Si algo falla

| Qué ves | Qué revisar |
|---|---|
| Railway no lista el repo | GitHub App: da acceso al repo privado |
| Build rojo en `chatbot-api` | Espera; si es RAM, súbela a 2 GB |
| 502 / mantenimiento | Logs de `mysql` y `chatbot-api`; nombres de servicio exactos |
| Chat “no se pudo conectar” | `PUBLIC_APP_URL` y `ALLOWED_ORIGINS` con `https://` |
| Panel: credenciales inválidas | `SEED_ADMIN_PASSWORD` es la del **primer** arranque. Si la cambiaste después, no se actualiza sola |
| FAQ no responde | `CARGAR_KB_AL_ARRANCAR=1` y logs de `chatbot-api` con “Cargando base de conocimiento” |

---

## Qué hace cada archivo de este repo

| Archivo | Para qué |
|---|---|
| `docker-compose.railway.yml` | Mapa de las 4 cajas (referencia; Railway no lo ejecuta solo) |
| `deploy/railway/variables.compartidas.env` | Texto para pegar en Variables |
| `deploy/nginx/Dockerfile` | La puerta, lista para el `$PORT` de Railway |
| `services/*/railway.toml` | Chequeo de salud de las APIs |

Si te trabas en un clic, manda una captura de la pantalla de Railway (sin
mostrar contraseñas) y te decimos el siguiente botón.
