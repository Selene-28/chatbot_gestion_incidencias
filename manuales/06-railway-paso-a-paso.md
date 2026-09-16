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

En un proyecto **vacío** Railway **no muestra** un botón que diga “agregar
variable”. El menú *GitHub Repository / Database / Template / Function* sirve
para **crear una caja**, no para pegar claves.

Haz **una** de estas dos rutas (la B es la más fácil si no ves Variables).

### Ruta A — Si ya ves Variables en el proyecto

1. Cierra el menú de cajas (clic fuera o Escape).
2. Icono de **engranaje** (Settings) a la izquierda, o pestaña **Variables**
   arriba del lienzo.
3. **Shared Variables** / **Variable Set** → **Raw Editor**.
4. Pega el bloque de 13 variables (abajo) y guarda.
5. Márcalas como compartidas con **todos** los servicios.

### Ruta B — La que funciona con el menú de la foto (recomendado)

1. En ese menú pulsa **GitHub Repository** (no Database, no Function, no
   Template).
2. Elige el repo `chatbot_gestion_incidencias`.
3. Cuando aparezca la primera caja, **haz clic en ella**.
4. Arriba verás pestañas: **Deployments**, **Variables**, **Settings**, etc.
   Entra a **Variables**.
5. **Raw Editor** (o **+ New Variable** si no está el editor).
6. Pega las 13 líneas, guarda.
7. Si Railway ofrece **Share** / **Add to shared variable set** / compartir
   con el proyecto: **acepta**. Así las otras cajas las heredan.

Las 13 líneas (puedes pegarlas tal cual en la tesis). Si **ya las pegaste**,
no las borres: en `mysql` agrega solo `MYSQL_ROOT_PASSWORD` (paso 4.1).

```
TZ=America/Lima
DB_ROOT_PASSWORD=TesisCtic2026Root
DB_CHATBOT_PASSWORD=TesisCtic2026Chatbot
DB_TICKETS_PASSWORD=TesisCtic2026Tickets
TICKETS_API_KEY=TesisCtic2026ApiKey
JWT_SECRET=TesisCtic2026JwtSecretoLargoParaFirmarElPanel
SEED_ADMIN_PASSWORD=TesisCtic2026Admin
SEED_TECNICO_PASSWORD=TesisCtic2026Tecnico
ANTHROPIC_API_KEY=cambiar
LLM_MODEL=claude-opus-4-8
LLM_MODEL_ROUTER=claude-haiku-4-5
RAG_UMBRAL_SIMILITUD=0.83
ALLOWED_ORIGINS=https://fiis.unac.edu.pe,https://www.fiis.unac.edu.pe
```

`ANTHROPIC_API_KEY` puede quedarse en `cambiar`: el chat funciona igual, sin
redacción “bonita” de IA. Si más adelante tienes una clave `sk-ant-...`, la
pones aquí y vuelves a desplegar **chatbot-api**.

Después de pegarlas, esa primera caja debe llamarse **`mysql`** (Settings →
nombre) y seguir el resto del paso 4.1 (rama correcta, Dockerfile
`db/Dockerfile` y volumen `/var/lib/mysql`).

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
   - Nombre: `mysql` (lápiz **Edit service name** en el título, no un campo
     “Service name”).
   - **Source → Branch:** `cursor/demo-api-same-origin-2754`  
     **No dejes `master`.** En `master` no existe `db/Dockerfile` y el build
     sale rojo al instante (“Failed to build an image”).
   - **Root Directory:** vacío (no pongas `db`).
   - **Build → Builder:** **Dockerfile** (no Railpack).
   - **Build → Dockerfile Path:** `db/Dockerfile`
4. **Variables** de **esta** caja (además de las 13 compartidas). Pulsa
   **+ New Variable**. Aparecen dos cajas (no un bloque `CLAVE=valor`):
   - En **VARIABLE_NAME** escribe: `MYSQL_ROOT_PASSWORD`
   - En **VALUE or ${{REF}}** escribe: `TesisCtic2026Root`
   - No uses **Add Reference**. Pulsa el botón **Add** de esa fila
     (un clic en el fondo **no** la guarda).
   - Cuando `MYSQL_ROOT_PASSWORD` aparezca en la lista con puntos
     (`******`), arriba a la izquierda pulsa **Apply N change**.
     Aún **no** pulses **Deploy**.

   (el mismo valor que `DB_ROOT_PASSWORD`; MySQL solo reconoce este nombre).
5. Volumen: clic derecho en el lienzo o **Ctrl+K** → **New Volume**, adjúntalo
   a `mysql`, **Mount path:** `/var/lib/mysql`
6. Arriba a la derecha, **Apply** si aparece. Espera a que **Deployments**
   diga **Success**. El build bueno tarda **1–3 minutos** (baja la imagen
   MySQL). Si falla en 0–3 segundos, estás en la rama `master`: vuelve al
   punto 3.

#### Si ves FAILED / “Failed to build an image” (pantalla roja)

No pulses **Diagnosis**. Haz esto, en este orden:

1. En la misma caja `mysql`, pestaña **Settings** (no Project Settings).
2. Baja a **Source**.
3. En **Branch**, abre el desplegable y elige  
   **`cursor/demo-api-same-origin-2754`**.
4. Comprueba que **Dockerfile Path** sigue siendo `db/Dockerfile` y **Builder**
   es **Dockerfile**.
5. Pulsa **Update** / **Apply** (el botón morado de cambios pendientes).
6. Vuelve a **Deployments**. Debe aparecer un deploy nuevo. El título ya
   **no** debe ser el de `master` (“Panel: el desplegable de estado…”).
7. Espera. Si otra vez sale rojo, pulsa **View logs** (arriba a la derecha
   del recuadro rojo) y manda captura **del texto del log**, no de esta
   lista de pasos.

Hasta que `mysql` esté **Success** (verde) o el recuadro de la caja diga
**Online**, **no** crees `ticket-service`.

En **Settings de mysql** deja todo como está: rama
`cursor/demo-api-same-origin-2754`, **sin** Root Directory, **sin** pulsar
**Disconnect**.

### 4.2 Caja `ticket-service`

1. En el lienzo (la zona de la izquierda), pulsa **+** → **GitHub Repo** →
   el mismo repo `chatbot_gestion_incidencias`.
2. Clic en la caja nueva. Lápiz **Edit service name** → `ticket-service`.
3. **Settings:**
   - **Source → Branch:** `cursor/demo-api-same-origin-2754` (no `master`).
   - Pulsa **Add Root Directory** y escribe exactamente:
     `services/ticket-service`
     **sin** barra al inicio (no `/services/ticket-service`).
     Enter o el visto para guardar. **Wait for CI** déjalo apagado.
4. Pestaña **Variables**. En una caja **nueva** sale *No Environment
   Variables* (las de mysql **no** se copian solas). Haz **una** de estas:

   **A (si ves Shared Variable y las mismas claves que mysql):** pulsa
   **Shared Variable** y comparte el conjunto con `ticket-service`. Luego
   **Raw Editor** y añade solo las 2 líneas de `DB_URL` y `UPLOADS_DIR`.

   **B (la más simple, recomendada):** pulsa **Raw Editor** (arriba a la
   derecha) y pega **todo** este bloque. Guarda / **Update**.

   ```
   TZ=America/Lima
   DB_ROOT_PASSWORD=TesisCtic2026Root
   MYSQL_ROOT_PASSWORD=TesisCtic2026Root
   DB_CHATBOT_PASSWORD=TesisCtic2026Chatbot
   DB_TICKETS_PASSWORD=TesisCtic2026Tickets
   TICKETS_API_KEY=TesisCtic2026ApiKey
   JWT_SECRET=TesisCtic2026JwtSecretoLargoParaFirmarElPanel
   SEED_ADMIN_PASSWORD=TesisCtic2026Admin
   SEED_TECNICO_PASSWORD=TesisCtic2026Tecnico
   ANTHROPIC_API_KEY=cambiar
   LLM_MODEL=claude-opus-4-8
   LLM_MODEL_ROUTER=claude-haiku-4-5
   RAG_UMBRAL_SIMILITUD=0.83
   ALLOWED_ORIGINS=https://fiis.unac.edu.pe,https://www.fiis.unac.edu.pe
   DB_URL=mysql+asyncmy://tickets:${{DB_TICKETS_PASSWORD}}@mysql.railway.internal:3306/tickets_db
   UPLOADS_DIR=/data/uploads
   ```

5. Volumen: **Ctrl+K** → **New Volume**, adjúntalo a `ticket-service`,
   **Mount path:** `/data/uploads`
6. Arriba a la izquierda pulsa **Apply N changes** (eso **sí** guarda).
   Si **Deployments** dice *There is no active deployment*, entonces sí
   pulsa el botón morado **Deploy** (o el enlace **Deploy the repo …**).
   En **Deployments** espera **Success** (unos minutos).
   *Unexposed service* es correcto: esta caja no se publica a internet.
   Si sale rojo al instante, la rama o el Root Directory están mal.

### 4.3 Caja `chatbot-api`

El primer build **tarda 15–25 minutos** (baja el modelo). No se puede
acortar. Mientras construye, puedes armar `nginx` (paso 4.4).

1. Lienzo **+** → **GitHub Repo** → `Selene-28/chatbot_gestion_incidencias`
   (no el otro repo).
2. Lápiz **Edit service name** → `chatbot-api`.
3. **Settings:**
   - **Branch:** `cursor/demo-api-same-origin-2754`
   - **Add Root Directory:** `services/chatbot-api` (sin `/` al inicio)
   - **Wait for CI** apagado
   - Baja (no escribas en *Filter Settings*) hasta **Replica Limits** →
     **Memory**. Pon **al menos 2 GB**. **8 GB está bien** (es un tope, no
     un gasto fijo). No bajes de 2 GB. **CPU** puede quedarse alto.
4. **Variables.** Si aparece *Suggested Variables* (`UV_LINK_MODE`,
   `HF_HOME`, etc.), puedes pulsar **Add** o ignorarlas: ya van en la
   imagen. **No sustituyen** las claves. Luego **Raw Editor**, pega todo,
   guarda:

   ```
   TZ=America/Lima
   DB_ROOT_PASSWORD=TesisCtic2026Root
   MYSQL_ROOT_PASSWORD=TesisCtic2026Root
   DB_CHATBOT_PASSWORD=TesisCtic2026Chatbot
   DB_TICKETS_PASSWORD=TesisCtic2026Tickets
   TICKETS_API_KEY=TesisCtic2026ApiKey
   JWT_SECRET=TesisCtic2026JwtSecretoLargoParaFirmarElPanel
   SEED_ADMIN_PASSWORD=TesisCtic2026Admin
   SEED_TECNICO_PASSWORD=TesisCtic2026Tecnico
   ANTHROPIC_API_KEY=cambiar
   LLM_MODEL=claude-opus-4-8
   LLM_MODEL_ROUTER=claude-haiku-4-5
   RAG_UMBRAL_SIMILITUD=0.83
   ALLOWED_ORIGINS=https://fiis.unac.edu.pe,https://www.fiis.unac.edu.pe
   DB_URL=mysql+asyncmy://chatbot:${{DB_CHATBOT_PASSWORD}}@mysql.railway.internal:3306/chatbot_db
   TICKETS_API_BASE_URL=http://ticket-service.railway.internal:8001
   CHROMA_DIR=/data/chroma
   CARGAR_KB_AL_ARRANCAR=1
   ```

5. **Ctrl+K** → **New Volume**, a `chatbot-api`, **Mount path:** `/data/chroma`
6. **Apply N changes**. Si Deployments está vacío, **Deploy**.
   Espera **Success** / **Online**. *Unexposed* es correcto.

### 4.4 Caja `nginx` (la puerta)

Puedes crearla **mientras** `chatbot-api` está en BUILDING.

1. **+** → **GitHub Repo** → el mismo repo.
2. Nombre: `nginx`.
3. **Settings:**
   - **Branch:** `cursor/demo-api-same-origin-2754`
   - **Root Directory:** vacío (**no** pulses **Add Root Directory**)
   - En el menú **derecho** pulsa **Build** (no está en Source).
     Vacía *Filter Settings* si escribiste algo.
   - **Builder:** **Dockerfile** (no Railpack)
   - **Dockerfile Path:** `deploy/nginx/Dockerfile`
   - **Wait for CI** apagado
4. **Raw Editor:**

   ```
   CHATBOT_UPSTREAM=http://chatbot-api.railway.internal:8000
   TICKETS_UPSTREAM=http://ticket-service.railway.internal:8001
   ```

5. **Apply**, luego **Deploy** si Deployments está vacío.
6. Cuando `nginx` esté en marcha: **Settings → Networking → Generate Domain**.
   Copia la URL `https://….up.railway.app` (sin barra al final).
7. En **chatbot-api** → **Variables** → **+ New Variable** → **Add**:
   - `PUBLIC_APP_URL` = esa URL
   Luego **Apply**. Railway redespliega `chatbot-api` (más corto que el
   primer build).

Hasta que `chatbot-api` esté **Online**, `nginx` puede mostrar 502; es
normal. Recarga un par de minutos después.

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
| `mysql` FAILED en **Build > Build image** (0–3 s) | **Branch** está en `master`. Cámbiala a `cursor/demo-api-same-origin-2754` y **Apply** |
| Variable nueva y solo aparece **Add** | Pulsa **Add**; un clic vacío no guarda. Luego **Apply N change** |
| `ticket-service` Variables vacío (*No Environment Variables*) | **Raw Editor** y pega el bloque del paso 4.2 (incluye `DB_URL`) |
| Duda **Apply** vs **Deploy** | Primero **Apply N changes**. Si Deployments está vacío, entonces sí **Deploy** |
| `chatbot-api` *Suggested Variables* (`UV_*`, `HF_HOME`) | Opcional **Add**. Las claves van en **Raw Editor** (bloque del paso 4.3) |
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
