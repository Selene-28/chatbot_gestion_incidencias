# PRD 04 — Contratos de API

Dos superficies REST:

- **`ticket-service`** (`/api/incidencias`, `/api/encuesta`) — implementa los contratos **API-01 a API-03 y API-06 del DRS**, que son el contrato de integración con el futuro sistema real.
- **`chatbot-api`** (`/api/chat/*`, `/api/faq`, `/api/kb`, `/api/metricas`) — superficie propia del chatbot (incluye API-04 y API-05 del DRS).

Todo en JSON UTF-8. Versionado por prefijo cuando se publique al exterior (`/api/v1/...`); en este documento se omite `v1` por brevedad.

---

## 1. Autenticación

| Tráfico | Mecanismo |
|---|---|
| Widget → `chatbot-api` | Token de sesión de chat (`sessionToken`, opaco, emitido al crear la sesión). Header `X-Session-Token`. |
| `chatbot-api` → `ticket-service` | API key de servicio. Header `X-Api-Key` (variable `TICKETS_API_KEY`). En producción con el sistema real: el mecanismo que este defina (el cliente HTTP lo abstrae). |
| Panel de agentes | Login → JWT (exp. 8 h) en cookie `HttpOnly` + CSRF token. Roles: `tecnico`, `admin`. |
| `/api/metricas`, `/api/kb` (escritura) | JWT con rol `admin`. |

## 2. Envelope estándar (DRS)

**Éxito:**
```json
{ "success": true, "code": 200, "message": "Operación realizada correctamente.", "data": { } }
```

**Error:**
```json
{
  "success": false, "code": 400, "message": "Los datos enviados son inválidos.",
  "errors": [ { "field": "correo", "description": "El correo institucional es obligatorio." } ]
}
```

Códigos: `200` OK, `201` creado, `400` validación, `401` no autenticado, `403` sin permiso, `404` no encontrado, `409` conflicto de estado, `422` regla de negocio, `429` rate limit, `500` error interno (mensaje genérico, detalle solo en logs).

---

## 3. `ticket-service` — contratos del DRS

### API-01 · Registrar incidencia
`POST /api/incidencias` — auth: `X-Api-Key`

```json
// Request
{
  "nombre": "Juan Pérez",
  "correo": "jperez@unac.edu.pe",
  "area": "Industrial",
  "categoria": "Correo Institucional",
  "subcategoria": "Recuperación de contraseña",
  "descripcion": "No puedo acceder a mi correo institucional.",
  "prioridad": "Media",
  "origen": "chatbot",
  "conversacionCodigo": "3f2a...-uuid",
  "adjuntoId": "adj_9f31"        // opcional, ver API-01b
}
```
```json
// Response 201
{ "success": true, "code": 201, "message": "La incidencia fue registrada correctamente.",
  "data": { "ticketId": "INC-2026-0001", "estado": "Registrado" } }
```
Notas: si el `correo` no existe en `usuarios`, se crea el usuario (rol `usuario`). El código se genera con `ticket_secuencias` en la misma transacción (RN-01). Se inserta la fila inicial en `ticket_historial`.

### API-01b · Subir adjunto (previo al registro)
`POST /api/incidencias/adjuntos` — `multipart/form-data`, campo `file`.
Valida MIME real (JPG/JPEG/PNG/PDF) y tamaño ≤ 5 MB (RF-13). Devuelve `{ "adjuntoId": "adj_9f31" }`. Los adjuntos huérfanos (> 24 h sin ticket) se purgan con un job.

### API-02 · Consultar estado
`GET /api/incidencias/{ticketId}?correo={correo}` — auth: `X-Api-Key`
El parámetro `correo` implementa RN-03: si no coincide con el propietario → `403`.

```json
// Response 200
{ "success": true, "code": 200, "message": "OK", "data": {
    "ticketId": "INC-2026-0001",
    "estado": "En Proceso",
    "categoria": "Correo Institucional",
    "fechaRegistro": "2026-06-18T09:15:00",
    "tecnico": "Paul Barzola",
    "ultimaActualizacion": "2026-06-18T10:30:00",
    "observaciones": "Incidencia asignada al área de soporte.",
    "respuesta": null
} }
```

`respuesta` es la nota del técnico (máx. 1000 caracteres). Solo se expone cuando el ticket está `Resuelto` o `Cerrado`; en el resto de estados va `null` y `observaciones` muestra el último comentario del historial.

`GET /api/incidencias?correo={correo}` — lista los tickets del correo (para consulta "por correo" de RF-02), ordenados por fecha desc, máx. 10.

### API-03 · Escalar incidencia
`PUT /api/incidencias/escalar` — auth: `X-Api-Key`

```json
// Request
{ "ticketId": "INC-2026-0001", "motivo": "No fue posible resolver mediante el chatbot.", "correo": "jperez@unac.edu.pe" }
// Response 200
{ "success": true, "code": 200, "message": "La incidencia fue derivada al personal técnico.",
  "data": { "estado": "Escalado" } }
```
Reglas: solo desde `Registrado`, `Asignado` o `En Proceso` (si no → `409`); escribe en `ticket_historial`.

### API-06 · Registrar encuesta de satisfacción
`POST /api/encuesta` — auth: `X-Api-Key`

```json
// Request (ticketId o conversacionCodigo, al menos uno)
{ "ticketId": "INC-2026-0001", "conversacionCodigo": null, "calificacion": 5, "comentario": "La atención fue rápida y clara." }
// Response 201
{ "success": true, "code": 201, "message": "Gracias por valorar nuestro servicio.", "data": { } }
```
`calificacion` entero 1–5 (RN-04). Segunda encuesta para la misma atención → `409`.

### Endpoints del panel (no-DRS, internos)
- `POST /api/auth/login` → JWT (staff).
- `GET /api/panel/tickets?estado=&categoria=&tecnico=` — listado con filtros.
- `PATCH /api/panel/tickets/{ticketId}` — `{ "estado": "...", "tecnicoId": 2, "comentario": "...", "respuesta": "..." }` (el panel admite cualquiera de los 6 estados; `respuesta` máx. 1000).
- `GET /api/panel/tickets/{ticketId}` — detalle con historial, `respuesta` y `adjuntos`.
- `GET /panel/tickets/{codigo}/adjuntos/{adjuntoId}` — descarga del archivo (cookie `panel_token`, RF-13).

---

## 4. `chatbot-api` — superficie de chat

### Crear sesión
`POST /api/chat/sesiones`
```json
// Request
{ "canal": "web_widget" }
// Response 201
{ "success": true, "code": 201, "message": "OK", "data": {
    "sessionId": "3f2a...-uuid", "sessionToken": "opaque-token",
    "mensajeBienvenida": "¡Hola! Soy el Asistente Virtual del CTIC...",
    "menu": [ {"id":"registrar_incidencia","texto":"📝 Registrar incidencia"},
              {"id":"consultar_estado","texto":"🔍 Consultar estado de mi incidencia"},
              {"id":"faq_general","texto":"❓ Preguntas frecuentes"},
              {"id":"contactar_soporte","texto":"🧑‍💻 Contactar con soporte"},
              {"id":"info_ctic","texto":"ℹ️ Información del CTIC"} ] } }
```

### Enviar mensaje
`POST /api/chat/mensajes` — auth: `X-Session-Token`
```json
// Request (uno de "texto" u "opcionId"; "opcionId" cuando el usuario pulsa un botón)
{ "sessionId": "3f2a...", "texto": "no puedo entrar a mi correo", "opcionId": null }
```
```json
// Response 200 — estructura de mensaje del bot
{ "success": true, "code": 200, "message": "OK", "data": {
    "mensajes": [ {
      "tipo": "texto",                    // texto | opciones | formulario | encuesta | handoff
      "texto": "Puede restablecer su contraseña desde el portal institucional...",
      "opciones": [ {"id":"crear_ticket","texto":"Registrar incidencia"},
                    {"id":"menu","texto":"Volver al menú"} ],
      "meta": { "intent": "recuperar_correo", "confianza": 0.94, "fuentesKb": [12, 31] }
    } ],
    "estadoBot": "ACTIVE"
} }
```

### Streaming (respuestas RAG)
`GET /api/chat/stream?sessionId=...` — SSE (auth por token). Cuando la respuesta la genera el LLM, el backend responde al `POST` con `{"tipo":"stream_pendiente"}` y emite por SSE eventos `token` (fragmentos), `fin` (mensaje completo + meta) y `agente` (mensajes del agente humano durante handoff). El widget degrada a polling si SSE no está disponible.

### API-04 · Buscar en base de conocimiento
`POST /api/faq` — interno (lo usa el propio motor; expuesto también para pruebas)
```json
// Request
{ "pregunta": "¿Cómo recupero mi contraseña del correo institucional?" }
// Response 200
{ "success": true, "code": 200, "message": "OK", "data": {
    "intent": "recuperar_correo",
    "respuesta": "Puede restablecer su contraseña desde el portal institucional siguiendo...",
    "confianza": 0.96,
    "fuentes": [ { "articuloId": 12, "titulo": "Recuperación de contraseña de correo" } ]
} }
```

### API-05 · Registrar conversación
Cumplido **internamente**: `chatbot-api` persiste cada mensaje en `mensajes` (RF-09). Se expone lectura para auditoría:
`GET /api/chat/conversaciones/{sessionId}/mensajes` — JWT staff (QA-07).

### Handoff
- `POST /api/chat/handoff` — `{ "sessionId": "...", "motivo": "solicitud_usuario" }` → crea `handoffs(pendiente)`, pausa el bot, devuelve mensaje de transición.
- `GET /api/panel/handoffs?estado=pendiente` — JWT staff: cola con resumen + últimos 20 mensajes.
- `POST /api/panel/handoffs/{id}/atender` — asigna al agente autenticado; sus mensajes van por `POST /api/panel/handoffs/{id}/mensajes` y llegan al usuario vía SSE.
- `POST /api/panel/handoffs/{id}/cerrar` — reactiva el bot (RN-06) y dispara la encuesta.

### Base de conocimiento (RF-12)
- `GET /api/kb/articulos` (staff) · `POST /api/kb/articulos` · `PUT /api/kb/articulos/{id}` · `DELETE` (desactiva) — JWT `admin`.
- `POST /api/kb/reindex` — reconstruye el índice vectorial desde `kb_articulos` (idempotente). Tras cada escritura se reindexa incrementalmente el artículo afectado.

### Métricas (RF-14)
`GET /api/metricas/resumen?desde=2026-08-01&hasta=2026-08-31` — JWT `admin`
```json
{ "success": true, "code": 200, "message": "OK", "data": {
    "conversaciones": 412, "mensajes": 3120,
    "tasaAutoservicio": 0.63, "latenciaPromMs": 820,
    "calificacionProm": 4.4, "encuestas": 180,
    "ticketsPorEstado": { "Registrado": 12, "En Proceso": 30, "Escalado": 4, "Resuelto": 95, "Cerrado": 80 },
    "intentsTop": [ { "intent": "recuperar_correo", "total": 96 } ]
} }
```

### Salud
`GET /healthz` en ambos servicios → `{ "status": "ok", "db": "ok", "llm": "ok|degraded" }` (usado por healthchecks Docker y monitoreo).

---

## 5. Reglas transversales

- **Idempotencia:** `POST /api/incidencias` acepta header `Idempotency-Key` (el chatbot envía el UUID del paso del flujo) para evitar tickets duplicados ante reintentos (REN-02/REN-05).
- **Timeouts del cliente interno:** `chatbot-api` → `ticket-service`: 5 s con 1 reintento (solo GET). Errores → mensaje de disculpa + opción reintentar (REN-05).
- **Paginación:** listados con `?page=&size=` (default 20, máx 100), respuesta con `data.items` y `data.total`.
- **Fechas:** ISO 8601, zona `America/Lima`.
- **CORS:** `chatbot-api` permite solo los orígenes del sitio institucional configurados en `ALLOWED_ORIGINS`.
