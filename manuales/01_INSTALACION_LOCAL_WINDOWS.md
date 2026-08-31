# Instalación local en Windows sin Docker

Guía para levantar esta versión del chatbot en un equipo Windows usando
Python, `uv` y MySQL local. WordPress no es necesario para esta prueba.

## 1. Requisitos

- Windows 10/11.
- Python 3.12.
- MySQL Server 8.x ejecutándose en `127.0.0.1:3306`.
- `uv` instalado.
- PowerShell.
- Aproximadamente 5 GB libres para las dependencias del modelo de embeddings.

El widget web no necesita Node.js, npm, React ni plugins de WordPress.

## 2. Descargar y abrir el proyecto

1. Descomprime el ZIP.
2. Abre PowerShell en la carpeta que contiene `docker-compose.yml`.
3. Define la variable de la ruta del proyecto:

```powershell
$ROOT = "C:\ruta\chatbot_gestion_tickets-main"
```

Sustituye la ruta por la ubicación real.

## 3. Instalar `uv`

Si `uv` no está instalado:

```powershell
winget install --id astral-sh.uv -e --source winget `
  --accept-package-agreements --accept-source-agreements
```

Cierra y vuelve a abrir PowerShell. Comprueba:

```powershell
uv --version
```

Si el comando aún no aparece, usa la ruta instalada por WinGet o reinicia
Cursor/PowerShell.

## 4. Instalar e iniciar MySQL

Instala MySQL Server 8.x y asegúrate de que escucha en el puerto `3306`.
Compruébalo:

```powershell
Test-NetConnection 127.0.0.1 -Port 3306
```

El resultado debe mostrar `TcpTestSucceeded : True`.

Con un usuario administrador de MySQL, crea las bases y usuarios del proyecto.
Ejemplo:

```sql
CREATE DATABASE IF NOT EXISTS chatbot_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS tickets_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'chatbot'@'127.0.0.1' IDENTIFIED BY 'chatbot';
CREATE USER IF NOT EXISTS 'tickets'@'127.0.0.1' IDENTIFIED BY 'tickets';

GRANT ALL PRIVILEGES ON chatbot_db.* TO 'chatbot'@'127.0.0.1';
GRANT ALL PRIVILEGES ON tickets_db.* TO 'tickets'@'127.0.0.1';
FLUSH PRIVILEGES;
```

No uses estas contraseñas en producción; son solo valores de desarrollo local.

## 5. Instalar dependencias Python

En PowerShell:

```powershell
cd "$ROOT\services\ticket-service"
uv sync

cd "$ROOT\services\chatbot-api"
uv sync
```

Esta versión incluye `cryptography`, necesaria para que `asyncmy` se autentique
con MySQL 8 usando `caching_sha2_password`.

## 6. Aplicar migraciones

Terminal 1:

```powershell
cd "$ROOT\services\ticket-service"
$env:DB_URL = "mysql+asyncmy://tickets:tickets@127.0.0.1:3306/tickets_db"
$env:JWT_SECRET = "cambia-este-secreto-local"
$env:TICKETS_API_KEY = "cambia-esta-api-key-local"
$env:SEED_ADMIN_PASSWORD = "cambiar"
$env:SEED_TECNICO_PASSWORD = "cambiar"
uv run alembic upgrade head
```

Terminal 2:

```powershell
cd "$ROOT\services\chatbot-api"
$env:DB_URL = "mysql+asyncmy://chatbot:chatbot@127.0.0.1:3306/chatbot_db"
$env:TICKETS_API_BASE_URL = "http://127.0.0.1:8001"
$env:TICKETS_API_KEY = "cambia-esta-api-key-local"
$env:JWT_SECRET = "cambia-este-secreto-local"
$env:ANTHROPIC_API_KEY = ""
$env:ALLOWED_ORIGINS = "http://127.0.0.1:8089,http://localhost:8089"
$env:CHROMA_DIR = "$ROOT\data\chroma"
uv run alembic upgrade head
```

## 7. Cargar la base de conocimiento

En la terminal del `chatbot-api`:

```powershell
New-Item -ItemType Directory -Force "$ROOT\data\chroma" | Out-Null
uv run python -m app.scripts.cargar_kb
```

La primera ejecución puede tardar porque descarga el modelo
`multilingual-e5-small`. Debe terminar mostrando los artículos creados o
actualizados y los artículos indexados.

## 8. Levantar los servicios

Mantén abiertas tres terminales.

### Terminal A: servicio de tickets y panel

```powershell
cd "$ROOT\services\ticket-service"
$env:DB_URL = "mysql+asyncmy://tickets:tickets@127.0.0.1:3306/tickets_db"
$env:JWT_SECRET = "cambia-este-secreto-local"
$env:TICKETS_API_KEY = "cambia-esta-api-key-local"
$env:SEED_ADMIN_PASSWORD = "cambiar"
$env:SEED_TECNICO_PASSWORD = "cambiar"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

### Terminal B: API del chatbot

```powershell
cd "$ROOT\services\chatbot-api"
$env:DB_URL = "mysql+asyncmy://chatbot:chatbot@127.0.0.1:3306/chatbot_db"
$env:TICKETS_API_BASE_URL = "http://127.0.0.1:8001"
$env:TICKETS_API_KEY = "cambia-esta-api-key-local"
$env:JWT_SECRET = "cambia-este-secreto-local"
$env:ANTHROPIC_API_KEY = ""
$env:ALLOWED_ORIGINS = "http://127.0.0.1:8089,http://localhost:8089"
$env:CHROMA_DIR = "$ROOT\data\chroma"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Terminal C: página de demostración

```powershell
cd "$ROOT\widget\public"
python -m http.server 8089 --bind 127.0.0.1
```

## 9. Abrir y comprobar

- Chatbot: <http://127.0.0.1:8089/demo.html>
- Panel: <http://127.0.0.1:8001/panel>
- Salud chatbot: <http://127.0.0.1:8000/healthz>
- Swagger chatbot: <http://127.0.0.1:8000/docs>
- Swagger tickets: <http://127.0.0.1:8001/docs>

Credenciales locales del panel:

- Usuario: `admin@ctic.local`
- Contraseña: el valor usado en `SEED_ADMIN_PASSWORD`.

La respuesta de `/healthz` debe indicar `db: ok`. La API del chatbot debe crear
una sesión al abrir la burbuja del widget.

## 10. Si aparece “No se pudo conectar”

Comprueba, en este orden:

1. MySQL responde en `3306`.
2. `/healthz` responde en `8000`.
3. `/panel` responde en `8001`.
4. La demo se abrió en el puerto `8089`.
5. `ALLOWED_ORIGINS` incluye `http://127.0.0.1:8089`.
6. `demo.html` usa:

```html
<script src="./widget.js"
        data-api="http://127.0.0.1:8000/api" defer></script>
```

7. El paquete `cryptography` está instalado en el entorno de `chatbot-api`:

```powershell
cd "$ROOT\services\chatbot-api"
uv run python -c "import cryptography; print(cryptography.__version__)"
```

## 11. Actualizar la base de conocimiento

Para cargar los artículos incluidos en el código:

```powershell
cd "$ROOT\services\chatbot-api"
$env:DB_URL = "mysql+asyncmy://chatbot:chatbot@127.0.0.1:3306/chatbot_db"
$env:CHROMA_DIR = "$ROOT\data\chroma"
uv run python -m app.scripts.cargar_kb
```

En producción, el método recomendado es editar artículos desde
`/panel` → **Base de conocimiento**. No se deben exponer las claves del backend
en WordPress.

## 12. Detener el sistema

En cada terminal donde corre Uvicorn o el servidor estático, presiona `Ctrl+C`.
MySQL puede permanecer activo para el siguiente uso.
