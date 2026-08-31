# PRD 05 — Flujos Conversacionales y Lógica de Navegación

El diálogo se modela como una **máquina de estados por conversación**: la columna `conversaciones.flujo_activo` indica el flujo en curso y `flujo_contexto` (JSON) guarda los datos parciales. Si no hay flujo activo, el mensaje pasa al **router de intenciones** (`prd/06` §2).

Convención de IDs: F-01 … F-09. Cada flujo lista sus estados, transiciones y mensajes.

---

## F-01 · Enrutamiento general (qué pasa con cada mensaje)

```mermaid
flowchart TD
    A["Mensaje entrante<br/>(texto u opcionId)"] --> B{"¿estado_bot?"}
    B -- PAUSED --> C["Reenviar al agente<br/>(handoff activo)"]
    B -- ACTIVE --> D{"¿flujo_activo?"}
    D -- "sí" --> E["Dialog Manager:<br/>procesar paso del flujo"]
    E --> E1{"¿entrada válida<br/>para el paso?"}
    E1 -- sí --> E2["avanzar al siguiente paso /<br/>ejecutar acción final"]
    E1 -- no --> E3["re-solicitar el dato<br/>(máx. 3 intentos → fallback F-09)"]
    D -- "no" --> F{"¿opcionId de menú?"}
    F -- sí --> G["Iniciar flujo correspondiente"]
    F -- no --> H["Router de intenciones<br/>(reglas → LLM)"]
    H --> I{"intent"}
    I -- "flujo (1,2,9,10,11)" --> G
    I -- "RAG (3,4,8)" --> J["Motor RAG → respuesta anclada<br/>+ reset contador fallback"]
    I -- "diagnóstico (5,6,7)" --> K["Flujo de diagnóstico F-05"]
    I -- "social (12,13,14)" --> L["Respuesta fija"]
    I -- "fuera_de_alcance" --> M["Mensaje LF-01 + menú"]
    I -- "no_comprendida" --> N["Fallback F-09"]
```

## F-02 · Registrar incidencia (happy path del DRS)

Pasos del DRS 1–12 formalizados. Estados del flujo: `identificacion → categoria → descripcion → prioridad → adjunto → confirmacion → creado`.

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant B as Bot (chatbot-api)
    participant T as ticket-service

    U->>B: "Registrar incidencia" (botón o intent)
    B->>U: Solicita nombre y correo institucional (si la sesión no está identificada)
    U->>B: nombre + correo
    B->>B: valida dominio @unac.edu.pe (QA-06)
    B->>U: Solicita escuela (botones: Industrial/Sistemas)
    U->>B: escuela
    B->>U: Solicita categoría (botones desde tabla categorias)
    U->>B: categoría
    B->>U: "Describe brevemente el problema"
    U->>B: descripción (10–2000 chars, si no → re-solicita)
    B->>U: Prioridad sugerida (botones Baja/Media/Alta, default Media)
    U->>B: prioridad
    B->>U: "¿Deseas adjuntar evidencia?" (opcional, JPG/PNG/PDF ≤5MB)
    U->>B: adjunto o "omitir"
    B->>U: Resumen de datos + botones Confirmar / Corregir / Cancelar
    U->>B: Confirmar
    B->>T: POST /api/incidencias (API-01, con Idempotency-Key)
    T-->>B: { ticketId: "INC-2026-0001" }
    B->>U: "Su incidencia ha sido registrada correctamente. El número de ticket asignado es #INC-2026-0001..."
    B->>U: Menú principal (o encuesta si el usuario se despide)
```

Reglas: en `Corregir`, el bot pregunta qué campo cambiar y vuelve a `confirmacion`. En `Cancelar`, descarta `flujo_contexto` y vuelve al menú. Si `ticket-service` falla: mensaje de disculpa + botón "Reintentar" (los datos capturados no se pierden — REN-05, REN-02).

## F-03 · Consultar estado de incidencia

```mermaid
flowchart TD
    A["Intent consultar_estado"] --> B{"¿Sesión identificada<br/>con correo?"}
    B -- no --> C["Solicitar correo institucional"] --> D
    B -- sí --> D{"¿Cómo desea consultar?"}
    D -- "por nº de ticket" --> E["Solicitar código INC-AAAA-NNNN"]
    E --> F["GET /api/incidencias/{id}?correo=..."]
    F -- 200 --> G["Mostrar: estado, categoría, fecha,<br/>técnico asignado, última actualización"]
    F -- 403 --> H["'El ticket no pertenece a este correo'<br/>(RN-03, sin revelar datos)"]
    F -- 404 --> I["'No encontré ese ticket'<br/>+ reintentar / menú"]
    D -- "por mi correo" --> J["GET /api/incidencias?correo=..."]
    J --> K["Listar hasta 10 tickets<br/>como botones → detalle"]
    G --> L["¿Algo más? → menú / finalizar"]
```

## F-04 · Preguntas frecuentes (RAG)

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant B as Bot
    participant V as ChromaDB
    participant L as API Claude

    U->>B: consulta en lenguaje natural
    B->>V: embedding de la consulta → top-k artículos (k=4)
    V-->>B: artículos + scores
    alt score máx ≥ umbral (0.45 coseno, calibrable)
        B->>L: prompt: responde SOLO con estos artículos (RN-08)
        L-->>B: respuesta (streaming SSE)
        B->>U: respuesta completa del artículo (texto íntegro)
    else sin evidencia suficiente
        B->>U: "No tengo información sobre eso en mi base de conocimiento.<br/>¿Deseas registrar una incidencia para que un técnico te ayude?" (QA-03)
    end
```

## F-05 · Diagnóstico básico guiado (QA-04)

Árboles de decisión **estáticos y versionados en código/BD** (no LLM), uno por categoría. Ejemplo WiFi:

```mermaid
flowchart TD
    A["problema_internet"] --> B["¿Está conectado mediante<br/>WiFi o cable de red?"]
    B -- WiFi --> C["¿Ve la red 'UNAC' disponible?"]
    C -- no --> C1["Pasos: activar WiFi, acercarse al AP,<br/>olvidar y reconectar la red"]
    C -- sí --> C2["¿Autentica pero no navega?"]
    C2 -- sí --> C3["Pasos: portal cautivo, renovar IP,<br/>probar otro navegador"]
    C2 -- no --> C4["Verificar credenciales institucionales<br/>(enlace a artículo KB)"]
    B -- Cable --> D["Pasos: verificar cable/punto de red,<br/>probar otro equipo"]
    C1 & C3 & C4 & D --> E{"¿Se resolvió?"}
    E -- sí --> F["Cierre feliz + encuesta"]
    E -- no --> G["Ofrecer: registrar incidencia (F-02)<br/>con datos ya capturados<br/>(ubicación, tipo de conexión, síntoma)"]
```

Los otros árboles (Aula Virtual, software institucional, correo) siguen el mismo patrón; sus pasos provienen de artículos KB marcados como `categoria='diagnostico'`. El contexto capturado durante el diagnóstico **pre-llena** el flujo F-02 si se decide registrar (evita repreguntar).

## F-06 · Escalar incidencia

1. Bot solicita nº de ticket (o lo toma del contexto si la conversación ya lo consultó).
2. Bot solicita motivo (texto libre, 10–500 chars).
3. `PUT /api/incidencias/escalar` (API-03) validando propiedad por correo.
4. Confirmación: «Su incidencia requiere atención especializada. El caso ha sido escalado al personal técnico del CTIC. Recibirá una notificación cuando exista una actualización.»
5. Errores: ticket inexistente → reintento; ticket en estado no escalable (`Resuelto`/`Cerrado`) → explica y ofrece registrar una nueva incidencia.

## F-07 · Handoff a agente humano (protocolo del DRS)

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant B as Bot
    participant P as Panel de agentes
    actor A as Agente CTIC

    Note over B: disparadores: 3 fallbacks (F-09),<br/>botón "Contactar con soporte",<br/>diagnóstico fallido con usuario frustrado
    B->>U: "Te voy a transferir con el personal de CTIC. Un momento, por favor..."
    B->>B: estado_bot = PAUSED (RN-05)
    B->>P: crea handoff(pendiente) + últimos 20 mensajes de contexto
    P-->>A: notificación (badge/refresh en panel)
    A->>P: "Atender" → handoff(atendido)
    loop conversación humana
        A->>P: mensaje del agente
        P->>U: entrega vía SSE (emisor='agente')
        U->>B: mensajes del usuario → enrutados al panel (F-01)
    end
    A->>P: "Cerrar atención" (con o sin ticket asociado)
    P->>B: handoff(cerrado)
    B->>B: estado_bot = ACTIVE (RN-06)
    B->>U: "He vuelto 🙂 ¿Puedo ayudarte en algo más?" + encuesta (F-08)
```

Si ningún agente atiende en **10 minutos** (configurable): el bot se disculpa, ofrece registrar una incidencia (F-02) para atención asíncrona y marca el handoff `expirado`.

## F-08 · Encuesta de satisfacción

- Disparadores: cierre de handoff, ticket registrado + despedida, FAQ resuelta + despedida, intent `finalizar`.
- Mensaje: «Antes de finalizar, ¿podría calificar la atención recibida del 1 al 5?» — botones ⭐1–⭐5, luego comentario opcional (o botón "Omitir").
- `POST /api/encuesta` (API-06) con `ticketId` si la atención generó/consultó un ticket, si no `conversacionCodigo`.
- Solo se ofrece una vez por atención (RN-04); si el usuario la ignora, la conversación cierra igual.

## F-09 · Gestión de errores / Fallback (RF-10, DRS §Fallback)

```mermaid
stateDiagram-v2
    [*] --> ok : mensaje comprendido
    ok --> f1 : no comprendido (1º)
    f1 --> ok : mensaje comprendido<br/>(contador = 0)
    f1 --> f2 : no comprendido (2º)
    f2 --> ok : mensaje comprendido<br/>(contador = 0)
    f2 --> handoff : no comprendido (3º)
    handoff --> [*] : protocolo F-07

    note right of f1
        Mensaje de Fallo 1:
        "Lo siento, no logré entender tu mensaje.
        Por favor, selecciona una opción válida del
        menú o escribe tu duda en pocas palabras."
    end note
    note right of f2
        Mensaje de Fallo 2 + menú
        con botones fijos (reajuste del flujo)
    end note
```

"No comprendido" = intent `no_comprendida`, o confianza del router < 0.55, o 3 entradas inválidas seguidas dentro de un paso de flujo. El contador `fallback_consecutivos` vive en `conversaciones` y se reinicia con cualquier mensaje procesado con éxito.

---

## Mapa de cobertura DRS → flujos

| Elemento del DRS | Flujo |
|---|---|
| Happy Path pasos 1–12 | F-02 (+ F-08 paso 12) |
| Fallback 1º/2º/3º error | F-09 |
| Protocolo de handoff (PAUSED/ACTIVE, 20 mensajes) | F-07 |
| Intents 1–11 de la matriz | F-02…F-08 según tabla en `prd/01` §2 |
| Intenciones adicionales PLN (saludo, gracias, despedida, no comprendida, fuera de alcance) | F-01 (respuestas fijas) |
