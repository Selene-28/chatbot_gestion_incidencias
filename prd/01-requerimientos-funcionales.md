# PRD 01 — Requerimientos Funcionales

Fuente: DRS (`docs/`). Este documento normaliza los requerimientos con IDs trazables. Cada RF referencia el flujo (`prd/05`), el contrato de API (`prd/04`) y las tablas (`prd/03`) que lo implementan.

---

## 1. Requerimientos funcionales

| ID | Nombre | Descripción | Prioridad | Refs |
|---|---|---|---|---|
| RF-01 | Registrar incidencia | El chatbot guía al usuario para registrar una incidencia: captura nombre, correo institucional, área, categoría, subcategoría, descripción, prioridad y evidencia opcional; valida campos obligatorios (LF-04, QA-06); genera ticket con código único y lo confirma al usuario. | Alta | Flujo F-02, API-01 |
| RF-02 | Consultar estado de incidencia | Consulta por número de ticket o por correo institucional. Muestra estado, categoría, fecha de registro, técnico asignado (si existe) y última actualización. Solo el propietario puede ver sus tickets (SEG-02). | Alta | Flujo F-03, API-02 |
| RF-03 | Preguntas frecuentes (FAQ) | Ante una consulta en lenguaje natural, el bot detecta la intención, busca en la base de conocimiento (RAG) y responde con pasos claros. Si no hay respuesta con confianza suficiente, informa la limitación y ofrece registrar incidencia (QA-03). | Alta | Flujo F-04, API-04 |
| RF-04 | Diagnóstico básico guiado | Para categorías conocidas (WiFi/Internet, Aula Virtual, software institucional, correo institucional) el bot hace preguntas guiadas y adapta las sugerencias a las respuestas. Si el problema persiste, ofrece registrar/escalar (QA-04). | Media | Flujo F-05 |
| RF-05 | Escalar incidencia | El usuario (o el bot, tras diagnóstico fallido) escala un ticket existente indicando el motivo; el ticket pasa a estado `Escalado` y es visible para el personal técnico (QA-05). | Alta | Flujo F-06, API-03 |
| RF-06 | Handoff a agente humano | Tras 3 errores consecutivos de comprensión, o a pedido del usuario ("contactar con soporte"), el bot transfiere la conversación: pasa a estado `PAUSED`, notifica al panel de agentes con los últimos 20 mensajes, y vuelve a `ACTIVE` cuando el agente cierra la atención. | Alta | Flujo F-07 |
| RF-07 | Información del CTIC | Responde horario de atención, ubicación y canales de contacto desde la base de conocimiento. | Baja | Flujo F-04 |
| RF-08 | Encuesta de satisfacción | Al finalizar una atención (resolución de FAQ, registro de ticket o cierre de handoff), solicita calificación **1–5** y comentario opcional; la almacena para estadísticas (QA-10). | Media | Flujo F-08, API-06 |
| RF-09 | Registro de conversaciones | Toda interacción (mensaje de usuario, respuesta del bot, intención detectada, confianza, fecha/hora) se almacena para auditoría y mejora continua (LF-12, QA-07). | Alta | API-05, tabla `mensajes` |
| RF-10 | Gestión de fallback | 1er error: mensaje de fallo 1. 2do error consecutivo: mensaje de fallo 2 + menú con botones fijos. 3er error: handoff automático (RF-06). El contador se reinicia con cada mensaje comprendido. | Alta | Flujo F-09 |
| RF-11 | Panel de agentes | Personal CTIC autenticado puede: ver cola de handoffs y chatear con el usuario; listar/filtrar tickets; cambiar estado, asignar técnico y comentar; cerrar handoffs (lo que reactiva el bot). | Alta | `ticket-service` |
| RF-12 | Gestión de base de conocimiento | El administrador puede crear/editar/desactivar artículos FAQ; los cambios se reindexan en el motor de búsqueda semántica sin reiniciar el servicio (REN-06). | Media | `prd/06` §4 |
| RF-13 | Adjuntos | Solo JPG, JPEG, PNG y PDF (LF-08); tamaño máximo 5 MB por archivo; se almacenan fuera del árbol web y se sirven solo a usuarios autorizados. | Media | API-01 |
| RF-14 | Métricas | Endpoint y vistas SQL con: volumen de conversaciones, intents más frecuentes, tasa de autoservicio, tiempos de respuesta, calificación promedio, tickets por estado/categoría. | Media | `prd/04` §8 |
| RF-15 | Identificación del usuario | Antes de registrar o consultar incidencias, el bot solicita y valida el correo institucional (`*@unac.edu.pe`, formato RFC 5322). La sesión de chat queda asociada a ese correo (SEG-01). | Alta | Flujo F-02/F-03 |

## 2. Matriz de intenciones (del DRS, normalizada)

Estas son las intenciones que el router debe reconocer. Las de tipo **flujo** disparan una máquina de estados; las de tipo **RAG** se responden con la base de conocimiento; las **sociales** tienen respuesta fija.

| # | Intent (código) | Tipo | Datos a capturar | Acción | Integración |
|---|---|---|---|---|---|
| 1 | `registrar_incidencia` | Flujo | nombre, correo, área, categoría, subcategoría, descripción, evidencia (opc.), prioridad | Crear ticket y devolver código | API-01 |
| 2 | `consultar_estado` | Flujo | nº de ticket o correo | Consultar y mostrar estado | API-02 |
| 3 | `faq_general` | RAG | texto de la consulta | Buscar respuesta en base de conocimiento | API-04 |
| 4 | `recuperar_correo` | RAG→Flujo | correo institucional | Mostrar procedimiento; si persiste, ofrecer registrar incidencia | API-04 / API-01 |
| 5 | `problema_internet` | Diagnóstico | ubicación, tipo de conexión, descripción | Diagnóstico guiado + sugerencias | KB |
| 6 | `problema_aula_virtual` | Diagnóstico | usuario, descripción | Procedimiento guiado; si persiste, registrar incidencia | KB / API-01 |
| 7 | `problema_software` | Diagnóstico | sistema afectado, descripción | Mostrar solución o registrar ticket automáticamente | KB / API-01 |
| 8 | `info_ctic` | RAG (fija) | — | Horario, contacto, ubicación | KB |
| 9 | `escalar_incidencia` | Flujo | nº de ticket, motivo | Derivar al personal técnico | API-03 |
| 10 | `contactar_soporte` | Flujo | — | Handoff a agente humano | Panel interno |
| 11 | `finalizar` | Flujo | calificación (opc.) | Encuesta 1–5 y cierre | API-06 |
| 12 | `saludo` | Social | — | Mensaje de bienvenida + menú principal | — |
| 13 | `agradecimiento` | Social | — | Respuesta cortés, ofrece más ayuda | — |
| 14 | `despedida` | Social | — | Despedida (dispara `finalizar` si hubo atención) | — |
| 15 | `no_comprendida` | Fallback | — | Lógica de fallback RF-10 | — |
| 16 | `fuera_de_alcance` | Fallback | — | Informa que solo atiende servicios del CTIC (LF-01) | — |

### Respuestas fijas (textos oficiales del DRS)

- **Bienvenida (`saludo`):** «¡Hola! Soy el Asistente Virtual del CTIC. Estoy aquí para ayudarte con consultas e incidencias relacionadas con los servicios tecnológicos. ¿En qué puedo ayudarte?»
- **Agradecimiento:** «Con gusto. Si necesita ayuda con otra consulta o incidencia, estaré disponible para asistirlo.»
- **Despedida:** «Gracias por utilizar el Asistente Virtual del CTIC. Que tenga un excelente día.»
- **No comprendida (fallo 1):** «Lo siento, no logré entender tu mensaje. Por favor, selecciona una opción válida del menú o escribe tu duda en pocas palabras.»
- **Fuera de alcance:** «Actualmente solo puedo atender consultas relacionadas con los servicios tecnológicos del CTIC. Si su consulta corresponde a otra área de la universidad, le recomiendo comunicarse con la dependencia correspondiente.»
- **Transición a handoff:** «Te voy a transferir con el personal de CTIC. Un momento, por favor...»

## 3. Menú principal (botones)

El menú se muestra tras el saludo y tras cada atención completada:

1. 📝 Registrar incidencia
2. 🔍 Consultar estado de mi incidencia
3. ❓ Preguntas frecuentes
4. 🧑‍💻 Contactar con soporte
5. ℹ️ Información del CTIC

El usuario siempre puede escribir libremente; el router de intenciones decide (ver `prd/06` §2).

## 4. Reglas de validación (LF-03, LF-04, QA-06)

| Campo | Regla |
|---|---|
| Correo institucional | Regex de email + dominio `unac.edu.pe`. Si no cumple, se solicita de nuevo (máx. 3 intentos → fallback). |
| Nombre | 3–120 caracteres, sin HTML. |
| Escuela | Selección de lista: Industrial, Sistemas. |
| Categoría | Selección de la tabla `categorias` (activas). |
| Descripción | 10–2000 caracteres. Si el mensaje es excesivamente extenso o ambiguo, el bot pide reformular (LF-03). |
| Prioridad | Baja / Media / Alta (default: Media). La prioridad final la confirma el técnico. |
| Adjunto | JPG/JPEG/PNG/PDF, ≤ 5 MB, validación por MIME real (no solo extensión). |
| Nº de ticket | Formato `INC-AAAA-NNNN`. |
| Calificación | Entero 1–5. |
| Toda entrada libre | Sanitización anti-XSS/inyección (SEG-04): se almacena texto plano, se escapa al renderizar, queries siempre parametrizadas. |

## 5. Reglas de negocio

- **RN-01 Código de ticket:** `INC-<año>-<correlativo de 4 dígitos>` (ej. `INC-2026-0001`), correlativo por año, generado transaccionalmente.
- **RN-02 Estados de ticket:** `Registrado → Asignado → En Proceso → (Escalado) → Resuelto → Cerrado`. `Escalado` puede alcanzarse desde `Registrado`, `Asignado` o `En Proceso`. Todo cambio se registra en `ticket_historial` con actor y fecha.
- **RN-03 Privacidad de consulta:** la consulta de estado por correo solo devuelve tickets de ese correo; la consulta por código exige que el correo de la sesión coincida con el del ticket (SEG-02, PRI-03).
- **RN-04 Encuesta:** se ofrece una sola vez por atención; responderla es opcional; se asocia al ticket si existe, si no, a la conversación.
- **RN-05 Bot pausado:** mientras `estado_bot = PAUSED`, los mensajes del usuario se enrutan al agente y el motor de intenciones no responde.
- **RN-06 Reactivación:** cuando el agente marca el handoff como cerrado (o cierra el ticket asociado), el bot vuelve a `ACTIVE` y ofrece la encuesta.
- **RN-07 Consistencia (LF-11):** para una misma consulta FAQ y la misma versión de la base de conocimiento, la respuesta debe ser equivalente (temperatura/aleatoriedad del LLM minimizada por prompt y por respuestas ancladas a artículos).
- **RN-08 Fundamentación (LF-06):** el LLM solo responde con contenido presente en los artículos recuperados; si no hay evidencia suficiente, debe decir que no tiene la información y ofrecer registrar incidencia. Nunca inventa procedimientos.
- **RN-09 Inactividad:** una conversación sin actividad por 15 minutos se cierra automáticamente (estado `cerrada`, motivo `timeout`); si estaba en handoff pendiente, se notifica al panel.

## 6. Criterios de aceptación (QA del DRS — definición de terminado)

El proyecto está completo solo si pasa todas estas pruebas:

| ID | Prueba | Criterios |
|---|---|---|
| QA-01 | Registro de incidencias | Captura todos los datos obligatorios; valida completitud; genera ticket único; persiste en BD; confirma al usuario con el código. |
| QA-02 | Consulta de estado | Por nº de ticket; muestra estado actual, fecha de registro y técnico asignado (si existe); la información coincide con la BD. |
| QA-03 | FAQ | Identifica la intención; consulta la base de conocimiento; la respuesta corresponde a la consulta; si no existe respuesta, informa la limitación y ofrece registrar incidencia. |
| QA-04 | Diagnóstico básico | Hace preguntas relacionadas; las respuestas cambian según lo que responde el usuario; cierra bien si se resuelve; ofrece registrar/escalar si no. |
| QA-05 | Escalamiento | El usuario puede solicitarlo; se registra el motivo; el ticket pasa a `Escalado`; el personal técnico lo visualiza en el panel. |
| QA-06 | Validación de datos | No permite registrar con obligatorios vacíos; verifica formato del correo institucional; re-solicita ante errores. |
| QA-07 | Historial de conversaciones | Cada interacción queda registrada con fecha/hora e intención detectada; consultable por personal autorizado. |
| QA-08 | Seguridad | Solo usuarios autorizados consultan sus incidencias; HTTPS extremo a extremo; datos personales no visibles a terceros. |
| QA-09 | Rendimiento | Respuesta promedio ≤ 3 s; registro sin pérdida de información; disponibilidad según lo definido. |
| QA-10 | Encuesta | Se solicita al finalizar; acepta valoración 1–5; queda almacenada para estadísticas. |
| QA-11 | Flujo completo | El 100 % de los happy paths termina en la acción correcta sin colapsar el backend (se verifica con suite E2E automatizada). |
