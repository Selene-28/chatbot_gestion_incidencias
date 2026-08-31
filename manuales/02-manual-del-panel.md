# Manual del Panel — Personal del CTIC

Chatbot para la Gestión de Incidencias — **CTIC-FIIS UNAC**

Este manual está dirigido al **personal del CTIC** que usa el panel: los
**técnicos** (que atienden incidencias y chats en vivo) y los **administradores**
(que además gestionan la base de conocimiento y ven las métricas). Está escrito en
lenguaje sencillo, sin tecnicismos.

---

## 1. Cómo ingresar al panel

1. Abrir el navegador y entrar a la dirección del panel:
   **`https://<dirección-del-chatbot>/panel`**
   (por ejemplo `https://chatbot.fiis.unac.edu.pe/panel`).
2. Escribir su **usuario (correo)** y **contraseña**, y pulsar *Ingresar*.
3. Si los datos son correctos, verá la lista de incidencias.

La sesión dura **8 horas**; después deberá volver a ingresar. Para salir, use la
opción **Cerrar sesión**.

> **La primera vez:** el administrador y los técnicos se crean con una contraseña
> inicial definida por TI al instalar. **Cámbiela** apenas ingrese y no la
> comparta.

### Roles: técnico vs. administrador

| Puede hacer… | Técnico | Administrador |
|---|:---:|:---:|
| Ver y filtrar incidencias | ✅ | ✅ |
| Cambiar el estado de una incidencia | ✅ | ✅ |
| Asignar técnico y comentar | ✅ | ✅ |
| Atender chats en vivo (handoffs) | ✅ | ✅ |
| Gestionar la base de conocimiento | ❌ | ✅ |
| Ver el panel de métricas | ❌ | ✅ |

Si un técnico intenta entrar a una sección solo para administradores, verá un
aviso de acceso restringido.

---

## 2. Gestión de incidencias (tickets)

La pantalla principal (**Tickets**) lista las incidencias registradas, de la más
reciente a la más antigua.

### Ver y filtrar

Puede filtrar la lista por:

- **Estado** (Registrado, Asignado, En Proceso, Escalado, Resuelto, Cerrado).
- **Categoría** (por ejemplo, Correo Institucional, Aula Virtual, etc.).
- **Técnico** asignado.

Al hacer clic en una incidencia se abre su **detalle**: datos del solicitante,
descripción, adjuntos (si los hay) y el **historial completo** de cambios de
estado con sus comentarios y fechas.

### Los estados y sus transiciones válidas (regla RN-02)

Cada incidencia avanza por estados. **No todos los cambios están permitidos**: el
sistema solo deja pasar de un estado a otro si la transición es válida (esto evita
saltos incoherentes). El flujo es:

| Estado actual | Puede pasar a… |
|---|---|
| **Registrado** | Asignado, Escalado |
| **Asignado** | En Proceso, Escalado |
| **En Proceso** | Escalado, Resuelto |
| **Escalado** | En Proceso |
| **Resuelto** | Cerrado, En Proceso (reapertura) |
| **Cerrado** | (estado final, no admite cambios) |

Significado práctico:

- **Registrado:** recién creada (por el chatbot o por la web), aún sin técnico.
- **Asignado:** ya tiene un técnico responsable.
- **En Proceso:** el técnico está trabajando en ella.
- **Escalado:** se derivó a otra instancia porque no pudo resolverse en el primer
  nivel.
- **Resuelto:** el técnico dio solución (queda pendiente el cierre / la
  conformidad).
- **Cerrado:** atención finalizada. Es definitivo.

Si intenta un cambio no permitido, el sistema lo rechaza con un mensaje y **no**
modifica la incidencia.

### Cambiar el estado

En el detalle de la incidencia, elija el nuevo estado (solo aparecerán los estados
a los que sí puede pasar) y, opcionalmente, escriba un **comentario** explicando el
cambio. El comentario y el cambio quedan guardados en el historial.

### Asignar técnico

Desde el detalle puede asignar (o reasignar) un **técnico** responsable. Si la
incidencia estaba en *Registrado*, al asignar un técnico pasa automáticamente a
*Asignado*. No se puede asignar técnico a una incidencia **Cerrada**.

### Comentar

Cada cambio de estado admite un comentario. Escriba observaciones claras y útiles
(qué se hizo, qué falta), porque forman el historial que verá cualquier colega que
retome el caso.

---

## 3. Atención de handoffs (chat en vivo con el usuario)

### ¿Qué es un handoff?

Un **handoff** es cuando el chatbot **transfiere la conversación a una persona**.
Ocurre cuando el usuario pide hablar con soporte, o cuando el bot no puede
resolver la consulta. En ese momento el bot se **pausa** y la conversación entra en
la **cola de handoffs** esperando que un agente la atienda.

### La cola

En la sección **Handoffs** verá los chats que esperan atención (**pendientes**) y
los que ya están **en atención**. Para cada uno se muestra un resumen y los
**últimos mensajes** de la conversación, para que entienda el contexto antes de
responder.

### Atender un chat en vivo

1. Elija un handoff **pendiente** y pulse **Atender**. Queda asignado a usted.
2. Se abre la ventana de conversación. Escriba sus respuestas: **llegan al usuario
   en tiempo real** en su widget de chat (aparecen como mensajes del *Personal
   CTIC*).
3. El usuario también le puede escribir en vivo; verá sus mensajes al instante.

Mientras usted atiende, **el bot permanece pausado**: no interfiere en la
conversación.

### Cerrar la atención

Cuando termine, pulse **Cerrar** la atención. Al cerrar:

- El **bot se reactiva** (RN-06) y vuelve a estar disponible para el usuario.
- Se le ofrece al usuario una **breve encuesta de satisfacción** (calificación de
  1 a 5 estrellas) sobre la atención recibida.

### Expiración automática (10 minutos)

Si un handoff queda **pendiente y nadie lo atiende en 10 minutos**, el sistema lo
marca como **expirado**: el bot se disculpa con el usuario y le ofrece registrar
una incidencia para que su caso se atienda de forma diferida. Por eso conviene
**revisar la cola con frecuencia** y atender rápido los pendientes.

---

## 4. Administración de la base de conocimiento (solo administrador)

La **base de conocimiento (KB)** es el conjunto de artículos con los que la IA del
chatbot responde las preguntas frecuentes. Cuanto mejor redactados estén, mejor
responderá el bot.

En la sección **Base de conocimiento** el administrador puede:

- **Crear** un artículo nuevo (título, contenido, categoría y etiquetas).
- **Editar** un artículo existente.
- **Desactivar** un artículo (deja de usarse sin borrarlo; se puede reactivar).

Cada vez que se crea, edita o desactiva un artículo, el sistema **actualiza el
índice de búsqueda automáticamente** (no hay que reiniciar nada). Si alguna vez
fuese necesario reconstruir todo el índice, existe la opción de **Reindexar**.

### Buenas prácticas de redacción (para que el RAG responda bien)

El buscador de la IA funciona por significado, no por palabras exactas. Para que
encuentre y use bien un artículo:

1. **Título claro y específico.** Que describa exactamente el problema o la
   pregunta. Ejemplo: *"Recuperación de contraseña del correo institucional"* (no
   *"Problemas de correo"*).
2. **Un tema por artículo.** No mezcle varios problemas distintos en el mismo
   artículo; es preferible dividirlos.
3. **Pasos numerados.** Cuando la solución sea un procedimiento, escríbalo como
   lista `1.`, `2.`, `3.` El bot los presenta ordenados al usuario.
4. **Lenguaje natural del usuario.** Use las palabras que usaría un docente o
   estudiante ("no puedo entrar a mi correo"), no solo la jerga técnica.
5. **Etiquetas útiles.** Agregue etiquetas con sinónimos y términos relacionados
   (por ejemplo: *contraseña, clave, correo, acceso*) para ampliar las formas en
   que la pregunta puede llegar.
6. **Contenido conciso y correcto.** Respuestas breves, directas y verificadas.
   Un artículo desactualizado hace que el bot dé información equivocada.

> Los artículos que trae el sistema de fábrica son **provisionales** y deben
> validarse con el CTIC antes de considerarlos oficiales.

---

## 5. Dashboard de métricas (solo administrador)

La sección **Métricas** resume cómo está funcionando el chatbot en un período
(seleccione las fechas *desde* / *hasta*). Principales indicadores (KPI):

| Indicador | Qué significa | Cómo usarlo |
|---|---|---|
| **Conversaciones** | Cuántas conversaciones hubo en el período. | Mide el volumen de uso del chatbot. |
| **Mensajes** | Total de mensajes intercambiados. | Complementa el volumen; conversaciones muy largas pueden indicar dificultad. |
| **Tasa de autoservicio** | Porcentaje de conversaciones que se resolvieron **sin** generar un ticket. | Cuanto más alta, más problemas resuelve el bot solo. Es el KPI clave del proyecto. |
| **Latencia promedio** | Tiempo medio de respuesta del bot (milisegundos). | Si sube mucho, revisar el servicio o la IA. |
| **Calificación promedio** | Promedio de las encuestas de satisfacción (1 a 5). | Mide la calidad percibida de la atención. |
| **Encuestas** | Cuántas encuestas se respondieron. | Da contexto a la calificación (pocas encuestas = promedio menos representativo). |
| **Tickets por estado** | Cuántas incidencias hay en cada estado (Registrado, En Proceso, Escalado, Resuelto, Cerrado…). | Muestra la carga de trabajo y cuellos de botella (ej. muchos "Escalado"). |
| **Intenciones más frecuentes** | Los temas que más consultan los usuarios. | Orienta qué artículos de la KB reforzar o crear. |
| **Tokens del LLM** | Consumo acumulado de la IA. | Sirve para vigilar el costo/presupuesto de la API de Claude. |

Sugerencia de uso: revise las métricas semanalmente. Si la **tasa de autoservicio**
baja o crecen ciertas **intenciones**, suele indicar que faltan o están
desactualizados artículos en la base de conocimiento (sección 4).

---

## 6. Preguntas frecuentes del personal

- **¿Puedo borrar un artículo de la KB?** No se borra: se **desactiva** (deja de
  usarse pero queda registrado). Así se evita perder información por error.
- **Cerré un handoff por error, ¿el bot ya volvió?** Sí, al cerrar la atención el
  bot se reactiva automáticamente. El usuario puede seguir conversando con él.
- **No veo la sección de KB ni de Métricas.** Esas secciones son solo para
  **administradores**. Si necesita acceso, solicítelo a su administrador.
- **Un chat quedó "expirado".** Nadie lo atendió dentro de los 10 minutos. El
  usuario fue invitado a registrar una incidencia; búsquela en la lista de
  Tickets para darle seguimiento.
</content>
