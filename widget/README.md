# Widget Web — Asistente Virtual del CTIC (FIIS UNAC)

Widget de chat **embebible, sin dependencias** (JS/CSS vanilla, ES2020) para el
chatbot de gestión de incidencias del CTIC. Corresponde a la tarea 3.7 del plan
de implementación (`prd/08`) y a la vista de contenedores de `prd/02` §2.

## Cómo embeber

Agregar una sola línea antes de cerrar `</body>` del sitio institucional:

```html
<script src="https://<host>/widget/widget.js" data-api="https://<host>/api" defer></script>
```

- `data-api`: URL base de la API del chatbot (por defecto `/api` si se omite).
- `widget.js` inyecta automáticamente `widget.css` como `<link>`, derivando la
  URL de la de su propio `src` (deben servirse desde el mismo directorio).
- No usa frameworks ni variables globales; todo vive dentro de una IIFE y del
  contenedor `.cbctic-raiz`. Todas las clases CSS llevan el prefijo `cbctic-`.

Para probar localmente: servir `widget/public/` como estáticos (nginx ya lo hace
en `/widget/`) y abrir `demo.html`.

## Estructura

| Archivo | Rol |
|---|---|
| `public/widget.js` | Lógica completa del widget (IIFE con secciones: config, estado, api, ui, render, conversación, arranque). |
| `public/widget.css` | Estilos autocontenidos con prefijo `cbctic-`. Paleta institucional: azul `#1e3a5f`, blanco, acento ámbar `#e8a020`. |
| `public/demo.html` | Página de prueba en español que simula el sitio institucional FIIS-UNAC. |

## Contrato consumido (`prd/04-api.md` §4)

Envelope estándar en todas las respuestas: `{success, code, message, data}`
(éxito) / `{success:false, code, message, errors:[{field,description}]}` (error).

| Endpoint | Uso en el widget |
|---|---|
| `POST {api}/chat/sesiones` con `{canal:"web_widget"}` | Al abrir la ventana por primera vez (o al iniciar nueva conversación). Respuesta 201: `{sessionId, sessionToken, mensajeBienvenida, menu:[{id,texto}]}`. |
| `POST {api}/chat/mensajes` (header `X-Session-Token`) | Envío de texto libre (`{sessionId, texto}`), clic en botón (`{sessionId, opcionId}`) o adjunto subido (`{sessionId, opcionId:"__adjunto__", adjuntoId}`). Respuesta: `{mensajes:[MensajeBot], estadoBot:"ACTIVE"|"PAUSED"}`. |
| `POST {api}/chat/adjuntos` (header `X-Session-Token`, multipart campo `file`) | Subida de evidencia antes de enviarla al flujo. Respuesta: `{adjuntoId, nombreOriginal}`. |
| `GET {api}/chat/stream?sessionId=…&token=…` (`text/event-stream`) | Canal en tiempo real para el handoff (F-07). Solo lectura. El token va en query param porque `EventSource` no envía cabeceras. Ver «Tiempo real (SSE)». |

Tipos de `MensajeBot` renderizados:

- **`texto`** — burbuja del bot; respeta saltos de línea y agrupa líneas `1.` /
  `1)` consecutivas como lista numerada (`<ol>`). Si trae `opciones`, también
  pinta los botones (el contrato lo permite en cualquier tipo).
- **`opciones`** — botones tipo píldora; al hacer clic se envía el `opcionId`,
  la elección se muestra como burbuja del usuario y todos los controles
  interactivos anteriores quedan deshabilitados.
- **`adjunto`** — tarjeta con «📎 Adjuntar archivo» (input `accept=".jpg,.jpeg,.png,.pdf"`,
  validación en cliente de extensión y tamaño ≤ 5 MB según RF-13) y botón
  «Omitir». Al subir con éxito envía `{opcionId:"__adjunto__", adjuntoId}`.
- **`encuesta`** — 5 estrellas ★ clicables (RF-08); la estrella *n* envía
  `opcionId:"calif_n"` y se muestra la elección como `★★★☆☆ (3/5)`.
- **`handoff`** — banner distintivo ámbar con ícono 🧑‍💻 (RF-06). Mientras
  `estadoBot === "PAUSED"` el subtítulo del header cambia a «Atendido por
  personal del CTIC»; el usuario puede seguir escribiendo (RN-05: sus mensajes
  van al agente).
- Tipos desconocidos (p. ej. futuros `formulario`, `stream_pendiente`) se
  degradan a burbuja de texto para no romper la conversación.

Además, los mensajes escritos por un **agente humano** durante el handoff no
llegan por el `POST` sino por SSE y se pintan como una burbuja propia (rol
`agente`): alineada a la izquierda como el bot pero con el acento ámbar del
handoff y la etiqueta **«Personal CTIC»**, para distinguirla de bot y usuario.

## Tiempo real (SSE) — handoff con agente humano (F-07)

Cuando existe una sesión (recién creada o restaurada desde `sessionStorage`), el
widget abre un `EventSource` hacia
`GET {api}/chat/stream?sessionId=…&token=…`. Es un canal **de solo lectura**: el
usuario nunca escribe por SSE; sus mensajes siempre viajan por
`POST /chat/mensajes` (el backend los enruta al agente). Es una **mejora
progresiva**: si el navegador no soporta `EventSource` o el canal no conecta, el
chat sigue funcionando por `POST` sin degradar la experiencia base.

Eventos consumidos (el resto, incluidos los comentarios `: heartbeat` cada ~20 s,
se ignoran):

| Evento | `data` | Efecto en el widget |
|---|---|---|
| `agente` | `{texto, fecha}` | Mensaje del personal del CTIC → burbuja de agente añadida al historial (persistente), autoscroll y, si la ventana está cerrada, suma al contador de no-leídos. |
| `estado` | `{estadoBot}` | Transición `ACTIVE`↔`PAUSED`: actualiza `estado.estadoBot`, lo persiste y cambia el subtítulo del header («Atendido por personal del CTIC» en `PAUSED`). |
| `encuesta` | un `MensajeBot` de tipo `encuesta` | Tras cerrar el handoff, ofrece la encuesta con el mismo render de estrellas (el usuario califica con `POST /chat/mensajes`, `opcionId:"calif_n"`). |

- **En `PAUSED`** el usuario **sigue pudiendo escribir**: sus mensajes van por el
  `POST` normal y el backend los enruta al agente (no se espera respuesta del bot).
- **Reconexión:** `EventSource` reconecta solo ante cortes transitorios
  (`readyState === CONNECTING`). Si el navegador da el canal por cerrado
  (`CLOSED`), el widget reintenta con **backoff suave** (2 s × nº de intentos,
  tope 30 s); el contador se reinicia al reconectar (`open`).
- **Deduplicación:** el contrato no garantiza *replay*, pero por robustez los
  mensajes de agente se deduplican por `texto + fecha` (el evento no trae id) y
  la encuesta no se ofrece dos veces si ya hay una pendiente. Las claves de
  dedup se reconstruyen al restaurar el historial tras recargar.
- **Ciclo de vida:** el canal se cierra al iniciar «nueva conversación» o ante un
  `401` (sesión descartada) y se reabre con la nueva sesión.

### Degradación (limitación conocida)

El contrato principal para recibir mensajes del agente es **SSE** y el widget del
usuario **no dispone de un endpoint de polling propio** (el `POST /chat/mensajes`
solo responde a lo que el usuario envía). Por tanto, si el SSE no está soportado
o falla de forma persistente, el fallback aceptable es: el usuario **puede seguir
escribiendo y viendo sus propios mensajes** por el `POST`, y **los mensajes del
agente se mostrarán cuando el SSE vuelva a conectar**. No se inventan endpoints
de polling fuera del contrato.

### Manejo de errores

| Situación | Comportamiento |
|---|---|
| `401` | Se descarta la sesión y se crea otra automáticamente; se avisa «Tu sesión expiró…». |
| `409` | Mensaje «Esta conversación fue cerrada.» + botón «Iniciar nueva conversación». |
| `429` | Disculpa específica de límite de solicitudes + botón «Reintentar» que reenvía el último envío. |
| `5xx` / error de red | Disculpa genérica + botón «Reintentar» el último envío. |
| Otros `4xx` (400/422…) | Se muestra el `message` del envelope como nota de sistema. |
| Fallo de `POST /sesiones` al abrir | Mensaje offline + botón «Reintentar». |

## Comportamiento y decisiones de UX

- **Burbuja flotante** inferior derecha con `aria-label` en español,
  `aria-expanded` y **contador de mensajes no leídos** (se acumula si llegan
  mensajes con la ventana cerrada, se limpia al abrir).
- **Ventana**: header azul «Asistente Virtual CTIC — UNAC» con avatar 🤖,
  botón ⟳ «nueva conversación» (con `confirm()` previo) y ✕ cerrar. Desktop
  380×560 px; **móvil (<480 px) a pantalla completa**.
- **Sesión persistente por pestaña**: `{sessionId, sessionToken, historial,
  estadoBot}` se guardan en `sessionStorage` y el historial visual se restaura
  tras recargar la página. Se eligió `sessionStorage` (no `localStorage`)
  porque la sesión de chat es efímera (RN-09: timeout de 15 min) y así no
  persisten datos personales entre pestañas/sesiones del navegador.
- **Entrada siempre habilitada**: el usuario puede escribir texto libre aunque
  haya botones visibles (el router de intenciones decide, `prd/01` §3).
  Enter envía; el botón de enviar se bloquea mientras hay un POST en curso.
- **Indicador «escribiendo…»** con puntos animados durante cada petición;
  autoscroll al final; animaciones sutiles con soporte de
  `prefers-reduced-motion`.
- **Seguridad**: todo contenido del servidor se pinta con `textContent`
  (nunca `innerHTML`), en línea con SEG-04.
- Área de mensajes con `role="log"` y `aria-live="polite"`.

## Supuestos sobre puntos no especificados del contrato

1. **Botón «Omitir» del adjunto**: el contrato solo define el envío del adjunto
   exitoso (`opcionId:"__adjunto__"`). Se asume `{opcionId:"__omitir__"}` para
   omitir. Si el `MensajeBot` de tipo `adjunto` trae su propio arreglo
   `opciones`, esos botones también se renderizan, de modo que el backend puede
   imponer su propio id de «omitir» sin cambiar el widget.
2. **401 durante una conversación**: se reinicia la sesión automáticamente
   (bienvenida + menú nuevos) sin reenviar el mensaje que falló, porque el
   contexto del flujo se pierde con la sesión anterior.
3. **`meta` de los mensajes** (intent, confianza, fuentesKb): se ignora en la
   UI v1; se conserva en la firma del contrato para versiones futuras.
4. **Encuesta**: los ids `calif_1..calif_5` se envían como `opcionId` normal;
   el comentario opcional de la encuesta llega como texto libre posterior (lo
   maneja el flujo del backend).
5. **Streaming SSE** (`GET /chat/stream`): el widget consume los eventos
   `agente`, `estado` y `encuesta` para el handoff con un agente humano (ver
   «Tiempo real (SSE)»). El token de sesión se pasa como query param porque
   `EventSource` no admite cabeceras; se asume que el backend lo valida igual
   que el header `X-Session-Token`. Las respuestas del bot al `POST` siguen
   llegando completas (no se consumen los eventos `token`/`fin` de streaming de
   tokens RAG); el tipo `stream_pendiente` se degrada a texto.
6. **Validación de adjuntos en cliente**: por extensión y tamaño; la validación
   por MIME real la hace el backend (RF-13).
