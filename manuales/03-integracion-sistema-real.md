# Guía de Integración con el Sistema de Tickets Real

Chatbot para la Gestión de Incidencias — **CTIC-FIIS UNAC**

Este documento está dirigido al **equipo técnico de la universidad** (desarrollo
PHP/MySQL del sistema de tickets existente). Explica cómo conectar el chatbot con
el **Sistema de Tickets CTIC real**, reemplazando el servicio simulado que se usa
durante la tesis. **No es necesario tocar el código del chatbot**: la integración
es un cambio de configuración más la implementación de un contrato REST.

---

## 1. Arquitectura actual (decisión ADR-03)

El chatbot **no gestiona los tickets por sí mismo**: los delega a un Sistema de
Tickets externo, al que llama por **REST**. Hoy ese sistema está **simulado** por
un servicio propio de este repositorio, `ticket-service` (Python/FastAPI), que
implementa el contrato completo.

```
  Widget web  ──►  chatbot-api  ──REST──►  Sistema de Tickets
  (usuario)        (diálogo/IA)   X-Api-Key   (hoy: ticket-service simulado
                                               mañana: sistema PHP/MySQL real)
```

El `chatbot-api` sabe a quién llamar por la variable de entorno
**`TICKETS_API_BASE_URL`** (ver `.env`), y se autentica con la clave
**`TICKETS_API_KEY`** enviada en el header **`X-Api-Key`**.

> **Objetivo de la integración:** hacer que el sistema real de la universidad
> hable el **mismo contrato** que hoy habla el `ticket-service`. Cuando lo haga,
> basta apuntar `TICKETS_API_BASE_URL` al sistema real y el chatbot funciona sin
> cambios.

---

## 2. Contrato REST que el sistema real debe implementar

Todo es **JSON UTF-8**. La autenticación de servicio es por header
**`X-Api-Key: <clave-acordada>`** en cada petición (la clave la define la
universidad y se configura en el `.env` del chatbot). Las fechas son ISO 8601 en
zona `America/Lima`.

### 2.1 Envelope estándar (obligatorio en TODAS las respuestas)

**Éxito:**
```json
{ "success": true, "code": 200, "message": "Operación realizada correctamente.", "data": { } }
```

**Error:**
```json
{
  "success": false,
  "code": 400,
  "message": "Los datos enviados son inválidos.",
  "errors": [ { "field": "correo", "description": "El correo institucional es obligatorio." } ]
}
```

Códigos usados: `200` OK · `201` creado · `400` validación · `401` no autenticado ·
`403` sin permiso · `404` no encontrado · `409` conflicto de estado · `422` regla
de negocio · `429` límite de peticiones · `500` error interno (mensaje genérico; el
detalle solo en logs, nunca al cliente).

El chatbot **espera este envelope**: lee `data` en caso de éxito y muestra
`message` al usuario en caso de error. Si el sistema real responde con otra
estructura, deberá envolverla (ver opción del adaptador, sección 3).

---

### API-01 · Registrar incidencia

`POST /api/incidencias` — auth `X-Api-Key`

**Request:**
```json
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
  "adjuntoId": "adj_9f31"
}
```

- `area` ∈ `Industrial | Sistemas` (nombre de campo histórico; representa la "Escuela").
- `prioridad` ∈ `Baja | Media | Alta`.
- `origen` ∈ `chatbot | web`.
- `subcategoria`, `conversacionCodigo` y `adjuntoId` son **opcionales**
  (`adjuntoId` se obtiene de API-01b).

**Response 201:**
```json
{ "success": true, "code": 201, "message": "La incidencia fue registrada correctamente.",
  "data": { "ticketId": "INC-2026-0001", "estado": "Registrado" } }
```

Reglas de negocio esperadas:
- Si el `correo` no existe entre los usuarios, **crearlo** (rol usuario).
- Generar el código con correlativo anual único **`INC-AAAA-NNNN`** (RN-01).
- Registrar la fila inicial en el historial del ticket con estado `Registrado`.
- **Idempotencia (recomendado):** aceptar el header `Idempotency-Key`. El chatbot
  envía el UUID del paso del flujo para que un reintento no cree tickets
  duplicados; si llega una clave repetida, devolver el ticket ya creado.

---

### API-01b · Subir adjunto (previo al registro)

`POST /api/incidencias/adjuntos` — auth `X-Api-Key`, `multipart/form-data`, campo `file`

- Validar el **tipo real** del archivo: JPG/JPEG/PNG/PDF, tamaño **≤ 5 MB** (RF-13).
- Devolver un identificador que luego se envía como `adjuntoId` en API-01.

**Response 201:**
```json
{ "success": true, "code": 201, "message": "Archivo recibido.", "data": { "adjuntoId": "adj_9f31" } }
```

Los adjuntos sin ticket (huérfanos por más de 24 h) deberían purgarse con un job.

---

### API-02 · Consultar estado

`GET /api/incidencias/{ticketId}?correo={correo}` — auth `X-Api-Key`

El parámetro `correo` implementa la regla RN-03: **si no coincide con el
propietario del ticket, responder `403`** (un usuario solo consulta lo suyo).

**Response 200:**
```json
{ "success": true, "code": 200, "message": "OK", "data": {
    "ticketId": "INC-2026-0001",
    "estado": "En Proceso",
    "categoria": "Correo Institucional",
    "fechaRegistro": "2026-06-18T09:15:00",
    "tecnico": "Paul Barzola",
    "ultimaActualizacion": "2026-06-18T10:30:00",
    "observaciones": "Incidencia asignada al área de soporte."
} }
```

`GET /api/incidencias?correo={correo}` — lista los tickets del correo, del más
reciente al más antiguo, **máximo 10** (para la consulta "por correo").

---

### API-03 · Escalar incidencia

`PUT /api/incidencias/escalar` — auth `X-Api-Key`

**Request:**
```json
{ "ticketId": "INC-2026-0001", "motivo": "No fue posible resolver mediante el chatbot.", "correo": "jperez@unac.edu.pe" }
```

**Response 200:**
```json
{ "success": true, "code": 200, "message": "La incidencia fue derivada al personal técnico.",
  "data": { "estado": "Escalado" } }
```

Reglas: solo se puede escalar desde `Registrado`, `Asignado` o `En Proceso`; en
otro caso responder **`409`**. El `correo` debe ser el del propietario (RN-03). Toda
transición deja traza en el historial.

---

### API-06 · Registrar encuesta de satisfacción

`POST /api/encuesta` — auth `X-Api-Key`

**Request** (indicar `ticketId` o `conversacionCodigo`, al menos uno):
```json
{ "ticketId": "INC-2026-0001", "conversacionCodigo": null, "calificacion": 5, "comentario": "La atención fue rápida y clara." }
```

**Response 201:**
```json
{ "success": true, "code": 201, "message": "Gracias por valorar nuestro servicio.", "data": { } }
```

Reglas: `calificacion` entero **1–5** (RN-04); una segunda encuesta para la misma
atención responde **`409`**.

---

### Métricas de tickets

`GET /api/metricas/tickets?desde=YYYY-MM-DD&hasta=YYYY-MM-DD` — auth `X-Api-Key`

Lo consume el panel de métricas del chatbot para combinar datos de conversaciones
con datos de tickets.

**Response 200:**
```json
{ "success": true, "code": 200, "message": "OK", "data": {
    "ticketsPorEstado": { "Registrado": 12, "En Proceso": 30, "Escalado": 4, "Resuelto": 95, "Cerrado": 80 },
    "calificacionProm": 4.4,
    "encuestas": 180
} }
```

> Este endpoint es **opcional** para arrancar: si el sistema real no lo expone, el
> chatbot degrada esa parte de las métricas (registra un aviso y muestra el resto).

---

### Resumen del contrato

| Contrato | Método y ruta | Autenticación |
|---|---|---|
| API-01 · Registrar | `POST /api/incidencias` | `X-Api-Key` (+ `Idempotency-Key` opcional) |
| API-01b · Adjunto | `POST /api/incidencias/adjuntos` (multipart) | `X-Api-Key` |
| API-02 · Consultar | `GET /api/incidencias/{id}?correo=` | `X-Api-Key` |
| API-02 · Listar | `GET /api/incidencias?correo=` | `X-Api-Key` |
| API-03 · Escalar | `PUT /api/incidencias/escalar` | `X-Api-Key` |
| API-06 · Encuesta | `POST /api/encuesta` | `X-Api-Key` |
| Métricas | `GET /api/metricas/tickets?desde=&hasta=` | `X-Api-Key` |

---

## 3. Dos caminos para integrar

### Opción A — Implementar los endpoints directamente en el sistema PHP/MySQL

El equipo agrega estas rutas REST al sistema de tickets existente, respetando el
contrato de la sección 2 (mismas rutas, payloads y envelope). Es la ruta más
limpia a largo plazo: el chatbot habla directo con el sistema real.

- **Ventaja:** sin componentes intermedios; una sola fuente de verdad.
- **Requiere:** modificar el sistema existente para exponer estas rutas y devolver
  el envelope estándar.

### Opción B — Adaptador delgado (contenedor traductor)

Se despliega un pequeño servicio (contenedor) que **expone el contrato REST** de la
sección 2 y por dentro **traduce** cada llamada a las tablas/consultas del sistema
real (o a sus APIs internas). El `ticket-service` de este repositorio sirve como
**referencia** de cómo debe comportarse cada endpoint.

- **Ventaja:** no se toca el sistema PHP existente; el adaptador absorbe las
  diferencias (nombres de campos, formato de respuesta, autenticación).
- **Requiere:** mantener un servicio adicional.

**Recomendación:** si el sistema real puede modificarse con comodidad, la **Opción
A** es preferible. Si el sistema es difícil de tocar o su calendario es distinto,
empezar con la **Opción B** (adaptador) y migrar a la A más adelante.

### El "switch": cómo apuntar el chatbot al sistema real

Sea cual sea la opción, **el cambio en el chatbot es solo de configuración**. En el
`.env` del despliegue:

```dotenv
# Antes (tesis, servicio simulado):
TICKETS_API_BASE_URL=http://ticket-service:8001
TICKETS_API_KEY=cambiar

# Después (sistema real o adaptador):
TICKETS_API_BASE_URL=https://tickets.ctic.unac.edu.pe
TICKETS_API_KEY=<clave-acordada-con-el-CTIC>
```

Y recrear **solo** el contenedor del chatbot (no toca la IA ni el widget):

```bash
docker compose up -d chatbot-api
```

A partir de ese momento el chatbot registra, consulta, escala y encuesta contra el
sistema real. El esquema `tickets_db` local queda solo para el panel de handoffs o
se retira, según se decida.

> **Nota sobre el panel de agentes:** el panel actual (gestión de tickets, KB y
> métricas) lo sirve el `ticket-service`. Si se reemplaza por completo el backend
> de tickets, la universidad decidirá si sigue usando este panel (apuntándolo al
> sistema real) o el suyo propio. La conmutación de la **integración del chatbot**
> descrita aquí es independiente de esa decisión.

---

## 4. Checklist de verificación de la integración

Con `TICKETS_API_BASE_URL` y `TICKETS_API_KEY` ya configurados, probar cada
endpoint con `curl` (sustituir `$BASE` por la URL del sistema real y `$KEY` por la
clave acordada). Todas las respuestas deben venir en el **envelope estándar**.

```bash
BASE="https://tickets.ctic.unac.edu.pe"
KEY="<clave-acordada>"

# 1) API-01 — registrar (debe devolver 201 con ticketId y estado "Registrado")
curl -sS -X POST "$BASE/api/incidencias" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"nombre":"Prueba QA","correo":"qa@unac.edu.pe","area":"Industrial",
       "categoria":"Correo Institucional","descripcion":"Prueba de integración.",
       "prioridad":"Media","origen":"chatbot"}'

# 2) API-02 — consultar por id (usar el ticketId devuelto arriba)
curl -sS "$BASE/api/incidencias/INC-2026-0001?correo=qa@unac.edu.pe" \
  -H "X-Api-Key: $KEY"

# 2b) API-02 — con correo ajeno debe devolver 403 (RN-03)
curl -sS "$BASE/api/incidencias/INC-2026-0001?correo=otro@unac.edu.pe" \
  -H "X-Api-Key: $KEY"

# 3) API-02 — listar por correo (máx. 10, más recientes primero)
curl -sS "$BASE/api/incidencias?correo=qa@unac.edu.pe" -H "X-Api-Key: $KEY"

# 4) API-03 — escalar (200 desde Registrado/Asignado/En Proceso; 409 en otro caso)
curl -sS -X PUT "$BASE/api/incidencias/escalar" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"ticketId":"INC-2026-0001","motivo":"Prueba de escalamiento.","correo":"qa@unac.edu.pe"}'

# 5) API-06 — encuesta (201; una segunda para la misma atención → 409)
curl -sS -X POST "$BASE/api/encuesta" \
  -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"ticketId":"INC-2026-0001","calificacion":5,"comentario":"Todo bien."}'

# 6) API-01b — subir adjunto (201 con adjuntoId)
curl -sS -X POST "$BASE/api/incidencias/adjuntos" \
  -H "X-Api-Key: $KEY" -F "file=@/ruta/a/evidencia.png"

# 7) Métricas de tickets (200)
curl -sS "$BASE/api/metricas/tickets?desde=2026-06-01&hasta=2026-06-30" \
  -H "X-Api-Key: $KEY"

# 8) Autenticación — sin/ con clave inválida debe devolver 401
curl -sS -X POST "$BASE/api/incidencias" -H "Content-Type: application/json" -d '{}'
```

Puntos a validar en cada respuesta:

- [ ] Estructura del **envelope** correcta (`success`, `code`, `message`, `data`/`errors`).
- [ ] **Códigos HTTP** correctos (201 al crear, 403 por correo ajeno, 409 en
      conflicto de estado o encuesta duplicada, 401 sin clave).
- [ ] El **código de ticket** tiene el formato `INC-AAAA-NNNN` y es único.
- [ ] La **regla RN-03** se cumple (un correo solo ve/opera sus propios tickets).
- [ ] Las **transiciones de estado** válidas se respetan al escalar.
- [ ] La **encuesta** acepta solo 1–5 y rechaza duplicados.

Cuando todos los puntos pasen, actualizar el `.env` del chatbot y ejecutar
`docker compose up -d chatbot-api`. La integración queda completa.

---

## 5. Referencias

- `prd/04-api.md` §2–§3 — contratos completos y envelope estándar (fuente de verdad).
- `prd/03-modelo-de-datos.md` — modelo de datos (usuarios, tickets, historial, encuestas).
- `prd/07-despliegue.md` §7 — ruta de integración con el sistema real.
- `services/ticket-service/` — implementación de referencia del contrato.
</content>
