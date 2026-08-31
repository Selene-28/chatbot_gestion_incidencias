# PRD 00 — Resumen Ejecutivo

**Proyecto:** Chatbot para mejorar la gestión de incidencias en la CTIC-FIIS UNAC, 2026
**Tipo:** Proyecto de tesis (investigación aplicada, diseño pre-experimental con pre-test/post-test)
**Duración de desarrollo:** 6 semanas
**Documentos fuente:** `docs/contexto.md` (planteamiento del problema) y `docs/DOCUMENTO DE REQUERIMIENTOS TÉCNICOS Y FUNCIONALES.docx` (DRS)

---

## 1. Problema

El CTIC de la FIIS-UNAC gestiona incidencias tecnológicas mediante el **Sistema de Tickets CTIC**, único canal oficial de soporte. Toda consulta —incluso las repetitivas y de baja complejidad (recuperación de contraseñas, acceso a plataformas, horarios, configuración de cuentas)— debe atravesar el mismo proceso de registro, clasificación, asignación y atención. Esto genera:

- Demora en la respuesta y acumulación de casos pendientes.
- Sobrecarga del personal técnico con consultas que podrían autoservirse.
- Dificultad para priorizar incidencias que sí requieren intervención especializada.
- Ausencia de atención fuera del horario de oficina.

## 2. Solución propuesta

Un **asistente virtual (chatbot) basado en IA**, desplegado como widget web en el sitio institucional, que:

1. **Resuelve consultas frecuentes** en lenguaje natural consultando una base de conocimiento institucional (arquitectura RAG), sin generar tickets innecesarios.
2. **Registra incidencias** mediante un flujo guiado que valida datos y genera un ticket en el sistema.
3. **Consulta el estado** de tickets existentes.
4. **Ejecuta diagnósticos básicos guiados** (WiFi, aula virtual, software institucional).
5. **Escala al personal humano (handoff)** cuando no puede resolver, adjuntando el contexto de la conversación.
6. **Mide la satisfacción** (encuesta 1–5) y registra métricas para la evaluación pre/post-test de la tesis.

### Enfoque conversacional: híbrido

| Capa | Tecnología | Se usa para |
|---|---|---|
| **Flujos guiados deterministas** | Máquina de estados + botones/formularios | Registrar incidencia, consultar estado, escalar, encuesta — operaciones críticas que deben ser 100 % predecibles (QA-11) |
| **NLP / LLM con RAG** | API de Claude + búsqueda semántica sobre la base de conocimiento | Preguntas frecuentes en lenguaje natural, detección de intención cuando el usuario escribe libremente |

Este enfoque cumple el DRS (que exige IA/NLP con detección de intenciones) minimizando costo y riesgo: el LLM nunca ejecuta acciones directamente, solo clasifica intenciones y redacta respuestas fundamentadas en la base de conocimiento.

## 3. Objetivos y KPIs (alineados a la tesis)

| Objetivo | KPI | Instrumentación |
|---|---|---|
| Reducir el tiempo de primera respuesta | Tiempo promedio entre consulta y primera respuesta útil (< 3 s para el bot, REN-01) | Timestamps en tabla `mensajes` |
| Reducir la carga de tickets repetitivos | % de conversaciones resueltas sin generar ticket (tasa de autoservicio) | `conversaciones` sin `ticket` asociado y cerradas con resolución |
| Mejorar el registro y trazabilidad | 100 % de incidencias del chatbot con ticket, historial de estados y conversación almacenada | Tablas `tickets`, `ticket_historial`, `mensajes` |
| Elevar la calidad del servicio | Calificación promedio de satisfacción (escala 1–5) | Tabla `encuestas` |
| Disponibilidad del canal | Servicio 24/7 salvo mantenimiento (REN-03) | Healthchecks + uptime del contenedor |

> **Nota de consistencia:** el DRS menciona en un pasaje calificación "del 1 al 10" y en QA-10/API-06 escala **1 a 5**. Se adopta **1–5** como escala oficial (prevalecen los criterios de aceptación y el contrato de API).

## 4. Alcance

### Dentro del alcance (In Scope)
- Registrar incidencia (con adjuntos JPG/JPEG/PNG/PDF).
- Consultar estado de incidencia por número de ticket o correo.
- Preguntas frecuentes (FAQ) con base de conocimiento + RAG.
- Diagnóstico básico guiado (WiFi/Internet, Aula Virtual, software institucional, correo institucional).
- Escalamiento de incidencias y handoff a agente humano.
- Contacto e información institucional del CTIC.
- Encuesta de satisfacción (1–5).
- Panel interno mínimo para agentes/técnicos (ver tickets, atender handoffs, cerrar casos).
- **Sistema de tickets simulado** (`ticket-service`): como no hay acceso al sistema real durante la tesis, se implementa el backend completo de tickets exponiendo los contratos API-01 a API-03 del DRS, diseñado para ser reemplazado por el sistema real en producción con un cambio de configuración.
- Métricas para el análisis pre/post-test.

### Fuera del alcance (Out of Scope — según DRS)
- Soporte técnico de segundo y tercer nivel.
- Control remoto de equipos.
- Administración de infraestructura tecnológica.
- Modificación de información institucional.
- Consultas ajenas al CTIC (LF-01).
- Integración con sistemas externos no autorizados.
- IA de propósito general (el bot solo responde del dominio CTIC).
- Gestión automática completa de incidencias (asignación/resolución humanas siguen existiendo).
- Canales WhatsApp / Facebook / Instagram (el DRS marca solo Web Widget).
- Procesamiento de voz, imágenes o video como entrada (LF-02). Los adjuntos son solo evidencia, no se interpretan.
- Idiomas distintos del español (LF-10).

## 5. Usuarios y roles

| Rol | Descripción | Acceso |
|---|---|---|
| **Usuario final** | Docentes, personal administrativo y estudiantes de la FIIS (los tres perfiles incluidos desde el inicio y contemplados en el pre/post-test) | Widget web; se identifica con correo institucional `@unac.edu.pe` |
| **Agente / Técnico CTIC** | Atiende handoffs, gestiona y resuelve tickets | Panel interno con login |
| **Administrador CTIC** | Gestiona base de conocimiento, categorías, usuarios staff; consulta métricas | Panel interno con login |

## 6. Restricciones y supuestos

- **Restricción de stack de la universidad:** el sistema de tickets real es PHP + MySQL + Apache (XAMPP). Por ello la BD del proyecto es **MySQL 8** y la integración se hace por **API REST** (agnóstica del lenguaje del otro lado).
- **Presupuesto reducido (tesis):** los embeddings son locales (open-source, sin costo por consulta); el único costo variable es la API del LLM, acotada por diseño (ver `prd/06-ia-rag.md`, sección de costos).
- **Producción:** se desplegará en un servidor de la universidad usando **contenedores Docker** (ver `prd/07-despliegue.md`). Se asume un servidor Linux con Docker Engine disponible o instalable.
- **Supuesto de integración:** cuando el Sistema de Tickets CTIC real exponga los endpoints API-01..03 (o un adaptador sobre su MySQL), el chatbot se reconecta cambiando `TICKETS_API_BASE_URL` y credenciales; no requiere cambios de código.

## 7. Requerimientos no funcionales (resumen del DRS)

| ID | Requerimiento | Valor objetivo |
|---|---|---|
| REN-01 | Tiempo de respuesta promedio | ≤ 3 segundos (respuestas de flujo; para respuestas LLM se usa streaming para que el primer token llegue < 3 s) |
| REN-02 | Registro de incidencias sin pérdida de información | Transaccional (ACID en MySQL) |
| REN-03 | Disponibilidad | 24/7 salvo mantenimiento programado |
| REN-04 | Concurrencia | Múltiples usuarios simultáneos (objetivo inicial: 50 sesiones concurrentes) |
| REN-05 | Recuperación ante errores | Mensaje claro + opción de reintentar o derivar a personal técnico |
| REN-06 | Escalabilidad | Nuevas FAQs, categorías y funcionalidades sin afectar el servicio |
| SEG-01..05 | Seguridad | Identificación por correo institucional, control de acceso por rol, HTTPS, validación de entradas, auditoría (ver `prd/02-arquitectura.md` §7) |
| PRI-01..04 | Privacidad | Datos usados solo para gestión de incidencias; acceso restringido al propietario y personal autorizado |
| LF-01..12 | Limitaciones de formato/contenido | Dominio CTIC, español, respuestas basadas solo en la base de conocimiento, registro de conversaciones para auditoría |

## 8. Entregables del proyecto

1. **Documentación** (este repositorio): PRD, arquitectura, modelo de datos, contratos de API, flujos, plan.
2. **Software**: `chatbot-api`, `ticket-service`, widget web, panel de agentes, migraciones de BD, imágenes Docker y `docker-compose`.
3. **Base de conocimiento inicial**: artículos FAQ del CTIC cargados y vectorizados.
4. **Evidencia para la tesis**: consultas SQL/endpoint de métricas que alimentan el análisis pre/post-test.
