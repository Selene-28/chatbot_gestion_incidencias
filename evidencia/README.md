# Evidencia para la tesis — Semana 6 (tareas 6.2 y 6.6)

Instrumentos de **prueba de carga** (tarea 6.2) y de **evaluación de calidad**
(tarea 6.6) del *Chatbot para la gestión de incidencias de la CTIC-FIIS UNAC*.
Todos los scripts se ejecutan contra el stack real levantado con Docker
(nginx en `http://localhost`, chatbot-api en `http://localhost:8000`).

Este directorio produce la evidencia empírica del **capítulo de resultados** del
diseño pre-experimental (pre-test / post-test): precisión del router de
intenciones, fidelidad (recall) del RAG, KPIs operativas y comportamiento del
sistema bajo concurrencia (REN-04, 50 sesiones simultáneas).

> Las cifras de este README son **resultados reales** de corridas ejecutadas el
> 2026-07-05 contra el stack de desarrollo. Se reportan tal cual, incluidos los
> números que no alcanzan el objetivo — son evidencia científica, no marketing.

---

## 1. Requisitos y puesta en marcha

- Python 3.12 (ver `.python-version`), gestor de paquetes [uv](https://docs.astral.sh/uv/).
- Stack del chatbot corriendo: `docker compose up -d` en la raíz del repositorio.

```bash
cd evidencia
uv sync                 # crea el entorno e instala locust, httpx, pandas, ruff
uv run ruff check .     # el código está libre de findings de ruff
```

Credenciales usadas por los scripts (valores por defecto, parametrizables por
CLI): staff admin `admin@ctic.local` / `cambiar`.

### Estructura

```
evidencia/
  pyproject.toml            # deps (locust, httpx, pandas) + ruff
  carga/locustfile.py       # 6.2 · prueba de carga
  evaluacion/
    precision_router.py     # 6.6 · precisión del router de intenciones
    fidelidad_rag.py        # 6.6 · recall del RAG
    exportar_metricas.py    # 6.6 · KPIs pre/post-test a CSV
  datos/
    frases_intents.json     # >=10 frases reales por intent
    preguntas_rag.json      # 32 preguntas con el artículo KB esperado
  salidas/                  # CSV/HTML generados (gitignored)
```

---

## 2. Nota metodológica importante (sin ANTHROPIC_API_KEY real)

El entorno de la corrida NO tiene una `ANTHROPIC_API_KEY` válida (vale `cambiar`),
de modo que **el LLM de Claude no está operativo**. Esto afecta a dos capas y se
documenta explícitamente en cada resultado:

- **Router de intenciones:** solo actúa la **Capa 1 (reglas regex/keywords**,
  `app/dialogo/router.py`). La Capa 2 (clasificador LLM) *se intenta* pero la API
  de Anthropic responde `401`, el *circuit breaker* se abre y el diálogo degrada
  a la Capa 1 (comportamiento previsto, prd/06 §6). El número reportado es, por
  tanto, la **precisión de la Capa 1 sola**.
- **RAG:** no hay **redacción** generada por el LLM, pero **sí funciona la
  recuperación** por *embeddings* locales (`meta.via = "semantico"`; si fallara,
  degradaría a FULLTEXT de MySQL). Se evalúa entonces el **recall del retrieval**,
  no la calidad de la redacción.

En producción, con la clave válida, la Capa 2 atendería justamente los casos que
hoy caen en `no_comprendida`, por lo que la precisión de extremo a extremo sería
mayor que la aquí reportada.

---

## 3. Tarea 6.2 · Prueba de carga (locust)

`carga/locustfile.py` simula usuarios concurrentes del widget ejecutando flujos
**mixtos y realistas**: cada `WidgetUser` crea **su propia sesión** (`POST
/api/chat/sesiones`) y usa su `X-Session-Token`. Los flujos son: saludar,
consultar una FAQ (mini-flujo de preguntas frecuentes → RAG), **registrar una
incidencia completa recorriendo F-02**, consultar estado (F-03) e info del CTIC.
Los IDs de botón **no se hardcodean**: cada tarea inspecciona la respuesta del
bot y descubre las opciones (`area_*`, `cat_*`, `prio_*`, `confirmar`, …).

### Comando reproducible (headless)

```bash
# A) A través de nginx (borde de producción, incluye rate-limit):
uv run locust -f carga/locustfile.py --headless -u 50 -r 5 -t 60s \
    --host http://localhost \
    --csv salidas/carga --html salidas/carga_reporte.html

# B) Directo al chatbot-api (mide la capacidad REAL de la app, REN-04):
uv run locust -f carga/locustfile.py --headless -u 50 -r 5 -t 60s \
    --host http://localhost:8000 \
    --csv salidas/carga_directo --html salidas/carga_directo_reporte.html
```

`-u 50` = 50 usuarios concurrentes (objetivo REN-04) · `-r 5` = rampa 5 usuarios/s
· `-t 60s` = 60 segundos.

### Resultados obtenidos (50 usuarios, 60 s)

**B) Directo al chatbot-api** — capacidad real de la aplicación (REN-04):

| Métrica | Valor |
|---|---|
| Peticiones totales | 7 325 |
| Errores 5xx | **0 (0.00 %)** |
| Latencia p50 (agregada) | 10 ms |
| Latencia **p95 (agregada)** | **65 ms** |
| Latencia p99 (agregada) | 120 ms |
| Latencia máx. | 307 ms |
| Throughput | 123.8 req/s |
| Flujo más pesado (`faq:consulta`, RAG) | p95 = **160 ms**, p99 = 260 ms |

> **Veredicto QA-09 / QA-11:** p95 = 65 ms (peor flujo, el RAG, 160 ms) ≪ 3 s y
> **0 errores 5xx** → **CUMPLE** el criterio con amplio margen. La aplicación
> sostiene 50 sesiones concurrentes sin degradación.

**A) A través de nginx** — comportamiento del borde de producción:

| Métrica | Valor |
|---|---|
| Peticiones cursadas | 2 098 |
| Respuestas `503` | **1 514 (≈72 %)** |
| Latencia p95 (de las que pasaron) | 23 ms |

Los `503` **no son un fallo de la aplicación**: provienen del **rate-limiter de
nginx** (`limit_req_zone $binary_remote_addr … rate=10r/s` con `burst=20`, ver
`deploy/nginx/conf.d/`). Es un control **anti-abuso por IP** (prd/02 §7, SEG).
Como el generador de carga comparte **una sola IP de origen**, los 50 usuarios
sumados superan 10 r/s y nginx los estrangula. En producción los 50 usuarios
provienen de IPs distintas, por lo que el límite por IP no se dispara. El
chatbot-api sirvió con `200` todas las peticiones que nginx sí le reenvió.

**Conclusión de carga:** el objetivo de 50 sesiones concurrentes (REN-04) se
cumple a nivel de aplicación (p95 ≈ 65 ms, 0 5xx). El único `503` observable es
el *rate-limit* de seguridad de nginx cuando el tráfico proviene de una sola IP,
un hallazgo esperado y deseable del control anti-abuso.

---

## 4. Tarea 6.6 · Precisión del router de intenciones

```bash
uv run python evaluacion/precision_router.py --host http://localhost
# -> salidas/precision_router.csv  y  salidas/precision_router_matriz.csv
```

Envía cada frase de `datos/frases_intents.json` (12 intents × 12 frases = **144
frases**) a una **sesión nueva** y compara `meta.intent` (intent detectado por el
router) con el esperado. `datos/frases_intents.json` contiene frases reales en
español con mayúsculas, tildes y coloquialismos.

### Resultado obtenido

| | |
|---|---|
| **Precisión global (Capa 1, reglas)** | **88.2 % (127/144)** |
| Objetivo prd/06 §7 (≥ 90 %) | **No alcanzado por 1.8 pp** |
| Vía de clasificación | 100 % `regla` (la Capa 2 LLM no operó, ver §2) |

Precisión por intent: `recuperar_correo` 100 %, `escalar_incidencia` 100 %,
`despedida` 100 %, `consultar_estado` 91.7 %, `contactar_soporte` 91.7 %,
`problema_aula_virtual` 91.7 %, `registrar_incidencia` 91.7 %, `saludo` 83.3 %,
`faq_general` 83.3 %, `info_ctic` 83.3 %, `problema_software` 75.0 %,
`problema_internet` 66.7 %.

**Análisis honesto de los 17 errores** (todos caen a `faq_general` o
`no_comprendida`, nunca a un intent accionable equivocado):

- Saludos compuestos: *"Hola buenas"*, *"Hola, ¿qué tal?"* → el patrón social
  está **anclado** (`^…$`) y no admite palabras extra.
- Síntomas reflexivos: *"No puedo **conectarme** al WiFi"* → la regla busca
  `\bconectar\b`, que no casa con "conectarme"/"conectarse".
- Síntomas de software sin la forma exacta: *"El Word no me abre"*, *"MATLAB no
  reconoce mi licencia"* → `no_comprendida`.
- Ambigüedades genuinas: *"Cómo genero un ticket"* (¿registrar vs. FAQ?),
  *"Cómo me comunico con el CTIC"* (¿info vs. contacto?).

Es exactamente el tipo de frase que en producción resolvería la **Capa 2 (LLM)**,
inactiva en esta corrida. La Capa 1 sola queda 1.8 pp bajo el objetivo; el diseño
de dos capas está pensado para cerrar esa brecha. La matriz de confusión completa
está en `salidas/precision_router_matriz.csv`.

---

## 5. Tarea 6.6 · Fidelidad / recall del RAG

```bash
uv run python evaluacion/fidelidad_rag.py --host http://localhost
# -> salidas/fidelidad_rag.csv
```

Envía cada pregunta de `datos/preguntas_rag.json` (**32 preguntas** sobre los 16
artículos reales de la base de conocimiento) por el mini-flujo de FAQ, lo que
fuerza el paso por el motor RAG. Verifica si el artículo esperado es la fuente
principal devuelta en `meta.fuentesKb` (recall@1). El emparejamiento es por
título exacto del artículo (el script mapea `id → título` vía `GET
/api/kb/articulos`).

### Resultado obtenido

| | |
|---|---|
| **Recall@1** | **96.9 % (31/32)** |
| Recall@k | 96.9 % (31/32) |
| Vía de recuperación | 100 % `semantico` (embeddings locales) |

Único fallo: *"¿Dónde reseteo la clave de mi correo @unac.edu.pe?"* recuperó
*"Configurar el correo institucional en el celular"* en lugar de *"Recuperación
de contraseña del correo institucional"* — confusión semántica razonable entre
dos artículos de la categoría *Correo Institucional*.

Recall@k coincide con recall@1 porque el motor cita **una** fuente principal por
respuesta. Se mide la **recuperación**, no la redacción (ver §2).

---

## 6. Tarea 6.6 · Exportación de KPIs (instrumento pre/post-test)

```bash
uv run python evaluacion/exportar_metricas.py --host http://localhost \
    --desde 2026-01-01 --hasta 2026-12-31
# -> salidas/metricas_resumen.csv  y  salidas/metricas_intents.csv
```

Consume `GET /api/metricas/resumen` (login admin) y vuelca a CSV las KPIs de la
tesis (prd/00 §3, prd/04 §8). Es el **instrumento del pre/post-test**: se ejecuta
una vez para cada medición con el mismo rango relativo y se comparan los CSV.

KPIs exportadas: conversaciones, mensajes, **tasa de autoservicio**, **latencia
promedio del bot (ms)** (REN-01 < 3 s), **calificación promedio** (1-5), nº de
encuestas, tickets por estado, tokens LLM e **intents más frecuentes**.

Muestra de referencia (rango 2026 completo, datos de desarrollo — se
**reemplazará** con las mediciones reales del pre-test y del post-test):

| KPI | Valor (dev) |
|---|---|
| Conversaciones | 209 |
| Mensajes | 870 |
| Tasa de autoservicio | 1.0 |
| Latencia promedio del bot | 89 ms (REN-01: < 3000) |
| Calificación promedio | 5.0 / 5 |
| Intents top | faq_general (60), faq (41), registrar_incidencia (34), … |

---

## 7. Resumen de resultados para la tesis

| Instrumento | Métrica | Resultado | Objetivo | Veredicto |
|---|---|---|---|---|
| Carga (app directa) | p95 latencia | **65 ms** (RAG: 160 ms) | < 3 s | **CUMPLE** |
| Carga (app directa) | errores 5xx | **0** | 0 | **CUMPLE** |
| Router de intenciones | precisión Capa 1 | **88.2 %** | ≥ 90 % | No alcanzado (−1.8 pp; Capa 2 LLM inactiva) |
| RAG | recall@1 (retrieval) | **96.9 %** | evaluación de fidelidad | **CUMPLE** |

Los CSV de `salidas/` están *gitignored* (son evidencia **generada**,
reproducible ejecutando los scripts). Se versionan los scripts, los datos `.json`
y este README con los resultados redactados.
