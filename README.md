# Chatbot para la Gestión de Incidencias — CTIC FIIS UNAC

Asistente virtual basado en IA que automatiza la atención inicial de incidencias del **Centro de Tecnologías de Información y Comunicación (CTIC)** de la Facultad de Ingeniería Industrial y de Sistemas de la **Universidad Nacional del Callao**.

Proyecto de tesis: *"Chatbot para mejorar la gestión de incidencias en la CTIC-FIIS UNAC, 2026"*.

## ¿Qué hace?

| Capacidad | Descripción |
|---|---|
| 📝 **Registrar incidencias** | Conversación guiada que captura los datos, valida el correo institucional y genera un ticket real (`INC-2026-0001`) |
| 🔍 **Consultar estado** | Por número de ticket o por correo, mostrando estado, técnico asignado e historial |
| ❓ **Preguntas frecuentes (IA)** | Responde en lenguaje natural usando una base de conocimiento institucional (búsqueda semántica + LLM opcional, arquitectura RAG) |
| 🩺 **Diagnóstico guiado** | Árboles de decisión para WiFi, Aula Virtual, correo y software; si no resuelve, registra el ticket con los datos ya capturados |
| 🧑‍💻 **Transferencia a humano** | Si el bot no entiende (3 intentos) o el usuario lo pide, un agente del CTIC atiende el chat **en vivo** desde el panel (tiempo real vía SSE) |
| ⭐ **Encuesta de satisfacción** | Calificación 1–5 al finalizar cada atención |
| 📊 **Panel del personal CTIC** | Gestión de tickets, atención de chats, edición de la base de conocimiento y dashboard de métricas |

**Estado: implementación funcional completa.** Los 11 criterios de aceptación del DRS (QA-01…QA-11) pasan en la suite E2E automatizada.

---

# Cómo correr el proyecto (guía desde cero)

Esta guía asume que **nunca has corrido un proyecto de software**: empieza por instalar las herramientas. Si ya las tienes, salta al [inicio rápido](#inicio-rápido-si-ya-tienes-todo-instalado).

## Paso 0 — Qué vas a instalar y para qué

| Herramienta | Para qué sirve | Obligatoria |
|---|---|---|
| **Cursor** (o VS Code) | El editor de código (IDE) donde verás y modificarás el proyecto. Cursor además trae un asistente de IA integrado | Recomendada |
| **Git** | Descarga el proyecto desde GitHub y gestiona las versiones del código | ✅ Sí |
| **Docker Desktop** | Ejecuta el proyecto completo (base de datos, servicios, servidor web) en "contenedores", sin que tengas que instalar nada de eso a mano | ✅ Sí |
| **uv** (Python) | Solo si quieres correr los tests fuera de Docker | Opcional |

> 💡 La gracia de Docker es que **no necesitas instalar Python, MySQL ni Nginx**: todo viene empaquetado y se levanta con un solo comando.

## Paso 1 — Instalar Cursor

1. Entra a <https://cursor.com> y pulsa **Download**.
2. **macOS:** abre el `.dmg` descargado y arrastra Cursor a la carpeta *Aplicaciones*.
   **Windows:** ejecuta el instalador `.exe` y sigue el asistente (siguiente → siguiente).
3. Ábrelo. La primera vez te pedirá crear una cuenta (puedes usar Google) y elegir preferencias — los valores por defecto están bien.

> Cursor incluye una **terminal integrada** (menú `Terminal → New Terminal`). Todos los comandos de esta guía se escriben ahí.

## Paso 2 — Instalar Git

- **macOS:** abre la terminal de Cursor y escribe `git --version`. Si no está instalado, macOS te ofrecerá instalar las *Command Line Tools* automáticamente — acepta y espera.
- **Windows:** descarga **Git for Windows** desde <https://git-scm.com/download/win>, instálalo con las opciones por defecto, y reinicia Cursor.

Verifica en la terminal:

```bash
git --version        # debe responder algo como: git version 2.4x.x
```

## Paso 3 — Instalar Docker Desktop

1. Descarga **Docker Desktop** desde <https://www.docker.com/products/docker-desktop/> (elige tu sistema: Apple Silicon / Intel para Mac, o Windows).
2. **macOS:** abre el `.dmg` y arrastra Docker a *Aplicaciones*. Ábrelo y acepta los permisos que pida.
   **Windows:** ejecuta el instalador. Si te pregunta por **WSL 2**, acepta (es el motor que usa Docker en Windows); puede pedir reiniciar la PC.
3. Abre Docker Desktop y **espera a que el ícono de la ballena quede fijo** (estado "running"). Debe quedar abierto mientras uses el proyecto.

Verifica en la terminal de Cursor:

```bash
docker --version           # Docker version 2x.x
docker compose version     # Docker Compose version v2.x
```

> ⚠️ Requisitos mínimos: ~10 GB de disco libres (las imágenes del proyecto ocupan ~4 GB) y 4 GB de RAM asignados a Docker (en Docker Desktop → Settings → Resources).

## Paso 4 — Descargar el proyecto

En la terminal de Cursor:

```bash
# 1. Ve a la carpeta donde quieras guardar el proyecto (ejemplo: Documentos)
cd ~/Documents        # Windows: cd %USERPROFILE%\Documents

# 2. Clona el repositorio
git clone https://github.com/iach33/chatbot_gestion_tickets.git

# 3. Entra a la carpeta
cd chatbot_gestion_tickets
```

Luego, en Cursor: `File → Open Folder…` y selecciona la carpeta `chatbot_gestion_tickets`. Verás toda la estructura del proyecto en el panel izquierdo.

## Paso 5 — Configurar las variables de entorno (`.env`)

El proyecto se configura con un archivo `.env` (contraseñas, claves). Nunca se sube a GitHub, así que debes crearlo copiando la plantilla:

```bash
cp .env.example .env       # Windows (PowerShell): copy .env.example .env
```

Para **probar en tu máquina no necesitas editar nada**: los valores `cambiar` funcionan como contraseñas de desarrollo. Dos notas:

- **`ANTHROPIC_API_KEY`** — es la clave del modelo de IA (Claude). **Es opcional**: sin ella, el chatbot funciona completo en "modo degradado" (los flujos, tickets, panel y la búsqueda semántica de FAQ operan normal; solo se desactiva la redacción de respuestas con LLM y la capa 2 del clasificador). Si tienes una clave (se obtiene en <https://console.anthropic.com>), reemplaza `cambiar` por tu `sk-ant-...`.
- Para un despliegue **real** (servidor de la universidad) sí debes cambiar todas las contraseñas — ver [`manuales/01-despliegue.md`](manuales/01-despliegue.md).

## Paso 6 — Levantar el proyecto

Antes de arrancar, puedes verificar que todo esté listo (Docker corriendo, `.env` presente, puertos libres):

```bash
./scripts/verificar_requisitos.sh
```

Con Docker Desktop corriendo, en la terminal (dentro de la carpeta del proyecto):

```bash
docker compose up -d --build
```

**La primera vez tarda 10–20 minutos** (descarga MySQL, Python, el modelo de IA de embeddings, etc. — depende de tu internet). Las siguientes veces tarda segundos. Sabrás que terminó cuando la terminal te devuelva el control y veas los contenedores como `Started` / `Healthy`.

Verifica que todo está sano:

```bash
docker compose ps          # 5 contenedores: nginx, chatbot-api, ticket-service, mysql, adminer
curl http://localhost/healthz    # → {"status":"ok","db":"ok","llm":"disabled"}
```

> `llm: "disabled"` es normal si no pusiste una API key — el sistema opera en modo degradado.

## Paso 7 — Cargar la base de conocimiento

Una sola vez (llena los artículos de FAQ y construye el índice de búsqueda semántica):

```bash
docker compose exec -T chatbot-api python -m app.scripts.cargar_kb
```

Verás algo como `artículos creados: 13 … artículos indexados: 16`.

## Paso 8 — ¡Probarlo! 🎉

Abre tu navegador:

| URL | Qué es | Credenciales |
|---|---|---|
| **<http://localhost/demo.html>** | Página de prueba con el **widget de chat** (burbuja 💬 abajo a la derecha). Conversa: registra una incidencia, pregunta "¿cómo recupero mi contraseña del correo?", escribe 3 mensajes sin sentido para forzar la transferencia a un humano | — |
| **<http://localhost/panel>** | **Panel del personal CTIC**: tickets, chats en vivo (handoffs), base de conocimiento y métricas | `admin@ctic.local` / `cambiar` (o `tecnico1@ctic.local` / `cambiar`) |
| <http://localhost:8080> | Adminer: explorar la base de datos MySQL directamente | servidor `mysql`, usuario `root`, contraseña `cambiar` |
| <http://localhost:8000/docs> y <http://localhost:8001/docs> | Documentación interactiva (Swagger) de las APIs de cada servicio | — |

**Prueba el ciclo completo:** en `demo.html` escribe 3 veces "asdfgh" → el bot te transfiere → abre `/panel/handoffs` en otra pestaña como técnico → pulsa **Atender** → escribe un mensaje → aparece **al instante** en el chat del usuario. Al cerrar la atención, el bot se reactiva y ofrece la encuesta.

## Paso 9 — Apagar, reiniciar, resetear

```bash
docker compose down              # apagar (los datos se conservan)
docker compose up -d             # volver a encender
docker compose logs -f chatbot-api   # ver los logs de un servicio
docker compose down -v           # ⚠️ RESET TOTAL: borra la base de datos (volver al paso 6)
```

---

## Inicio rápido (si ya tienes todo instalado)

```bash
git clone https://github.com/iach33/chatbot_gestion_tickets.git
cd chatbot_gestion_tickets
cp .env.example .env
docker compose up -d --build
docker compose exec -T chatbot-api python -m app.scripts.cargar_kb
open http://localhost/demo.html       # panel: http://localhost/panel (admin@ctic.local / cambiar)
```

## Correr los tests (opcional)

Requiere [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`; en Windows ver su web). Con el stack de Docker levantado:

```bash
# Tests de cada servicio (unitarios + integración contra el MySQL de Docker)
cd services/chatbot-api  && uv run pytest -m "not llm"   # ~250 tests
cd ../ticket-service     && uv run pytest                # ~206 tests

# Suite E2E: verifica los 11 criterios de aceptación del DRS contra el stack completo
cd ../../e2e && uv run pytest -q                         # → "QA-01..QA-11: 11/11 verdes"
```

## Solución de problemas frecuentes

| Problema | Causa y solución |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop no está corriendo. Ábrelo y espera la ballena fija. |
| El puerto 80 está ocupado (`address already in use`) | Otro programa usa el puerto 80 (ej. Skype, IIS, otro servidor). Ciérralo, o edita `docker-compose.yml` cambiando `"80:80"` por `"8088:80"` y usa `http://localhost:8088`. |
| `http://localhost` muestra "Servicio en mantenimiento" | Los servicios aún están arrancando (espera ~30 s) o alguno falló: revisa `docker compose ps` y `docker compose logs chatbot-api`. |
| El login del panel dice "Credenciales inválidas" | La contraseña es el valor de `SEED_ADMIN_PASSWORD` de **tu** `.env` (por defecto `cambiar`, no `cambiar123`). |
| El chat no responde a preguntas de FAQ | Falta cargar la base de conocimiento (paso 7). |
| El build falla o es lentísimo | Verifica espacio en disco y recursos de Docker Desktop (Settings → Resources: ≥4 GB RAM). Reintenta: `docker compose build --no-cache chatbot-api`. |
| Cambié código y no se refleja | En desarrollo el código se monta con hot-reload, pero en macOS a veces no dispara: `docker compose restart chatbot-api`. Si agregaste una **dependencia** nueva, necesitas rebuild: `docker compose up -d --build`. |

---

## Estructura del repositorio

```
├── prd/                  📘 Especificación completa (fuente de verdad): requisitos,
│                            arquitectura, modelo de datos, APIs, flujos, plan
├── manuales/             📗 Documentación operativa (despliegue, panel, integración)
├── services/
│   ├── chatbot-api/      🤖 Servicio conversacional: diálogo, IA/RAG, handoff, métricas
│   └── ticket-service/   🎫 Dominio de tickets (contratos del DRS) + panel del personal
├── widget/public/        💬 Widget de chat embebible (JS/CSS vanilla) + demo.html
├── e2e/                  ✅ Suite E2E de los criterios QA-01..QA-11 (gate de release)
├── evidencia/            📊 Instrumentos de la tesis: carga, precisión, recall, KPIs
├── deploy/               🚀 Nginx, TLS, backup/restore/monitoreo
├── db/init/              🗄️ Bootstrap de MySQL (esquemas y usuarios)
├── docker-compose*.yml   🐳 Orquestación (base + override dev + overlay producción)
└── CLAUDE.md             🧠 Guía para agentes de IA que trabajen en este repo
```

## Documentación

**Especificación (PRD)** — el diseño completo del sistema:

| Documento | Contenido |
|---|---|
| [prd/00-resumen-ejecutivo.md](prd/00-resumen-ejecutivo.md) | Visión, objetivos, alcance, KPIs de la tesis |
| [prd/01-requerimientos-funcionales.md](prd/01-requerimientos-funcionales.md) | Requerimientos, matriz de intenciones, criterios QA-01..11 |
| [prd/02-arquitectura.md](prd/02-arquitectura.md) | Diagramas C4, componentes, decisiones técnicas (ADRs) |
| [prd/03-modelo-de-datos.md](prd/03-modelo-de-datos.md) | Diagrama entidad-relación y DDL MySQL |
| [prd/04-api.md](prd/04-api.md) | Contratos REST (API-01..06 + chat), autenticación |
| [prd/05-flujos-conversacionales.md](prd/05-flujos-conversacionales.md) | Flujos del diálogo, fallback y handoff (diagramas) |
| [prd/06-ia-rag.md](prd/06-ia-rag.md) | Motor híbrido: router 2 capas, RAG, prompts, costos |
| [prd/07-despliegue.md](prd/07-despliegue.md) | Contenedores y ruta a producción |
| [prd/08-plan-implementacion.md](prd/08-plan-implementacion.md) | Plan de 6 semanas (ejecutado ✅) |

**Manuales operativos:**

| Manual | Dirigido a |
|---|---|
| [manuales/01-despliegue.md](manuales/01-despliegue.md) — instalación en servidor, TLS, backups, monitoreo | DevOps / TI |
| [manuales/02-manual-del-panel.md](manuales/02-manual-del-panel.md) — uso del panel paso a paso | Personal CTIC |
| [manuales/03-integracion-sistema-real.md](manuales/03-integracion-sistema-real.md) — contrato REST para conectar el sistema de tickets real | Equipo de desarrollo UNAC |

## Decisiones técnicas (resumen)

| Aspecto | Decisión |
|---|---|
| Enfoque conversacional | **Híbrido**: flujos guiados deterministas para operaciones críticas + **IA (RAG/LLM)** para preguntas en lenguaje natural |
| Backend | Python 3.12 + **FastAPI** (2 servicios), SQLAlchemy 2 async |
| Base de datos | **MySQL 8** (2 esquemas desacoplados, compatible con el stack de la universidad) |
| Búsqueda semántica | Embeddings locales (`multilingual-e5-small`, CPU, costo cero) + **ChromaDB** |
| LLM | API de Claude (Anthropic), **opcional** — sin clave opera en modo degradado correcto |
| Tiempo real | **SSE** (Server-Sent Events) para el chat agente↔usuario |
| Despliegue | **Docker Compose** (dev y producción), Nginx como único punto de entrada |
| Integración futura | `ticket-service` simula el sistema real; el cambio a producción es solo configuración ([manual 03](manuales/03-integracion-sistema-real.md)) |

## Para agentes de IA

Si vas a trabajar en este repositorio con Claude Code, Cursor u otro agente: lee **[CLAUDE.md](CLAUDE.md)** (comandos, convenciones y gotchas) y trata `prd/` como la fuente de verdad. La suite `e2e/` (QA-01..QA-11) es la definición de terminado: debe quedar en verde tras cualquier cambio.
