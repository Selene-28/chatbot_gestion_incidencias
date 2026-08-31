/**
 * Widget Web v1 — Asistente Virtual del CTIC (FIIS UNAC).
 *
 * Chat embebible sin dependencias (vanilla ES2020). Se integra con:
 *   <script src="https://.../widget/widget.js" data-api="/api" defer></script>
 *
 * Contrato consumido (prd/04-api.md §4):
 *   POST {api}/chat/sesiones   → crea sesión ({sessionId, sessionToken, mensajeBienvenida, menu})
 *   POST {api}/chat/mensajes   → envía texto/opción (header X-Session-Token)
 *   POST {api}/chat/adjuntos   → sube evidencia (multipart, campo "file")
 *   GET  {api}/chat/stream     → SSE en tiempo real durante el handoff (F-07):
 *                                eventos "agente", "estado" y "encuesta".
 *                                El token va como query param porque EventSource
 *                                no permite enviar cabeceras.
 *
 * Ver widget/README.md para decisiones de diseño y supuestos.
 */
(function () {
  "use strict";

  /* ============================================================
   * 1. CONFIG
   * ============================================================ */

  const script = document.currentScript;
  const API_BASE = ((script && script.getAttribute("data-api")) || "/api").replace(/\/+$/, "");
  const CSS_URL = script && script.src ? new URL("widget.css", script.src).href : "widget.css";

  const STORAGE_KEY = "cbctic_sesion_v1";
  const MAX_ADJUNTO_BYTES = 5 * 1024 * 1024; // 5 MB (RF-13)
  const EXTENSIONES_PERMITIDAS = [".jpg", ".jpeg", ".png", ".pdf"];
  const ACCEPT_ADJUNTO = ".jpg,.jpeg,.png,.pdf";

  // Todos los textos de la interfaz, en español.
  const TXT = {
    titulo: "Asistente Virtual CTIC — UNAC",
    subtituloActivo: "En línea",
    subtituloPausado: "Atendido por personal del CTIC",
    etiquetaAgente: "Personal CTIC",
    abrirChat: "Abrir el chat del Asistente Virtual del CTIC",
    cerrarChat: "Cerrar la ventana de chat",
    nuevaConv: "Iniciar una nueva conversación",
    confirmarNueva: "¿Deseas iniciar una nueva conversación? Se perderá el historial actual.",
    ventanaChat: "Ventana de chat del Asistente Virtual del CTIC",
    areaMensajes: "Historial de la conversación",
    placeholder: "Escribe tu mensaje…",
    entradaTexto: "Escribe tu mensaje para el asistente",
    enviar: "Enviar mensaje",
    escribiendo: "escribiendo…",
    eligeOpcion: "Selecciona una opción o escribe tu consulta:",
    offline: "No se pudo conectar con el asistente. Verifica tu conexión e inténtalo nuevamente.",
    reintentar: "Reintentar",
    errorEnvio: "Lo sentimos, ocurrió un problema al procesar tu mensaje. Por favor, inténtalo nuevamente.",
    errorLimite: "Estamos recibiendo muchas solicitudes en este momento. Por favor, espera unos segundos e inténtalo de nuevo.",
    sesionCerrada: "Esta conversación fue cerrada.",
    sesionExpirada: "Tu sesión expiró. Hemos iniciado una nueva conversación.",
    nuevaConversacionBtn: "Iniciar nueva conversación",
    adjuntoSeleccionar: "Adjuntar archivo",
    adjuntoOmitir: "Omitir",
    adjuntoAyuda: "Formatos: JPG, JPEG, PNG o PDF · máximo 5 MB",
    adjuntoInvalidoTipo: "Formato no permitido. Solo se aceptan archivos JPG, JPEG, PNG o PDF.",
    adjuntoInvalidoTam: "El archivo supera el tamaño máximo de 5 MB.",
    adjuntoSubiendo: "Subiendo archivo…",
    adjuntoError: "No se pudo subir el archivo. Por favor, inténtalo nuevamente.",
    adjuntoInput: "Seleccionar archivo de evidencia (JPG, PNG o PDF, máximo 5 MB)",
    encuestaAyuda: "Toca una estrella para calificar (1 a 5).",
    calificarCon: function (n) {
      return "Calificar con " + n + (n === 1 ? " estrella" : " estrellas") + " de 5";
    },
    noLeidos: function (n) {
      return n + (n === 1 ? " mensaje sin leer" : " mensajes sin leer");
    },
  };

  /* ============================================================
   * 2. ESTADO
   * ============================================================ */

  const estado = {
    abierto: false,
    sessionId: null,
    sessionToken: null,
    estadoBot: "ACTIVE", // ACTIVE | PAUSED
    historial: [], // items {rol:'usuario'|'bot'|'sistema'|'agente', tipo?, texto, opciones?, usado?}
    noLeidos: 0,
    enviando: false,
    creandoSesion: false,
    ultimoEnvio: null, // {parcial, eco} para el botón "Reintentar"
    // --- Tiempo real (SSE) ---
    eventSource: null, // instancia EventSource activa (o null)
    sseReintentos: 0, // contador para el backoff de reconexión manual
    sseTimer: null, // timeout de reconexión pendiente
    clavesAgente: new Set(), // dedup de mensajes de agente (texto+fecha)
  };

  function guardarSesion() {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          sessionId: estado.sessionId,
          sessionToken: estado.sessionToken,
          estadoBot: estado.estadoBot,
          historial: estado.historial,
        })
      );
    } catch (e) {
      /* almacenamiento no disponible: el chat sigue funcionando sin persistencia */
    }
  }

  function cargarSesion() {
    try {
      const crudo = sessionStorage.getItem(STORAGE_KEY);
      if (!crudo) return;
      const datos = JSON.parse(crudo);
      if (!datos || !datos.sessionId || !datos.sessionToken) return;
      estado.sessionId = datos.sessionId;
      estado.sessionToken = datos.sessionToken;
      estado.estadoBot = datos.estadoBot === "PAUSED" ? "PAUSED" : "ACTIVE";
      estado.historial = Array.isArray(datos.historial) ? datos.historial : [];
      // Reconstruye las claves de dedup de mensajes de agente ya mostrados,
      // para no duplicarlos si el backend los reenvía tras reconectar.
      estado.clavesAgente = new Set();
      estado.historial.forEach(function (item) {
        if (item.rol === "agente") {
          estado.clavesAgente.add(claveMensajeAgente(item.texto, item.fecha));
        }
      });
    } catch (e) {
      /* datos corruptos: se ignoran y se creará una sesión nueva */
    }
  }

  function limpiarSesion() {
    cerrarSSE(); // el flujo en tiempo real pertenece a la sesión que se descarta
    estado.sessionId = null;
    estado.sessionToken = null;
    estado.estadoBot = "ACTIVE";
    estado.ultimoEnvio = null;
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      /* sin almacenamiento */
    }
  }

  /* ============================================================
   * 3. API (contrato prd/04 §4 — envelope {success, code, message, data})
   * ============================================================ */

  async function apiFetch(ruta, opciones) {
    let res;
    try {
      res = await fetch(API_BASE + ruta, opciones);
    } catch (e) {
      const err = new Error("Sin conexión con el servidor");
      err.esRed = true;
      throw err;
    }
    let cuerpo = null;
    try {
      cuerpo = await res.json();
    } catch (e) {
      /* respuesta sin JSON (p. ej. 502 del proxy) */
    }
    if (!res.ok || !cuerpo || cuerpo.success !== true) {
      const err = new Error((cuerpo && cuerpo.message) || "HTTP " + res.status);
      err.status = res.status;
      err.envelope = cuerpo;
      throw err;
    }
    return cuerpo.data || {};
  }

  function apiCrearSesion() {
    return apiFetch("/chat/sesiones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ canal: "web_widget" }),
    });
  }

  function apiEnviarMensaje(cuerpo) {
    return apiFetch("/chat/mensajes", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Session-Token": estado.sessionToken || "",
      },
      body: JSON.stringify(cuerpo),
    });
  }

  function apiSubirAdjunto(archivo) {
    const formulario = new FormData();
    formulario.append("file", archivo, archivo.name);
    return apiFetch("/chat/adjuntos", {
      method: "POST",
      headers: { "X-Session-Token": estado.sessionToken || "" },
      body: formulario,
    });
  }

  /* ============================================================
   * 4. UI — construcción del DOM (siempre textContent, nunca innerHTML
   *    con datos del servidor)
   * ============================================================ */

  const ui = {
    raiz: null,
    burbuja: null,
    badge: null,
    ventana: null,
    subtitulo: null,
    mensajes: null,
    escribiendo: null,
    entrada: null,
    botonEnviar: null,
  };

  function el(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    if (texto !== undefined && texto !== null) nodo.textContent = texto;
    return nodo;
  }

  function boton(clase, texto, onClick, ariaLabel) {
    const b = el("button", clase, texto);
    b.type = "button";
    if (ariaLabel) b.setAttribute("aria-label", ariaLabel);
    b.addEventListener("click", onClick);
    return b;
  }

  function inyectarEstilos() {
    if (document.querySelector("link[data-cbctic]")) return;
    const enlace = document.createElement("link");
    enlace.rel = "stylesheet";
    enlace.href = CSS_URL;
    enlace.setAttribute("data-cbctic", "1");
    document.head.appendChild(enlace);
  }

  function construirUI() {
    ui.raiz = el("div", "cbctic-raiz");

    // --- Burbuja flotante -------------------------------------------------
    ui.burbuja = boton("cbctic-burbuja", "", alternarVentana, TXT.abrirChat);
    ui.burbuja.setAttribute("aria-expanded", "false");
    ui.burbuja.appendChild(el("span", "cbctic-burbuja-icono", "💬"));
    ui.badge = el("span", "cbctic-badge", "");
    ui.badge.hidden = true;
    ui.burbuja.appendChild(ui.badge);

    // --- Ventana de chat ---------------------------------------------------
    ui.ventana = el("div", "cbctic-ventana");
    ui.ventana.setAttribute("role", "dialog");
    ui.ventana.setAttribute("aria-label", TXT.ventanaChat);
    ui.ventana.hidden = true;

    // Cabecera
    const cabecera = el("div", "cbctic-cabecera");
    cabecera.appendChild(el("span", "cbctic-avatar", "🤖"));
    const tituloCaja = el("div", "cbctic-titulos");
    tituloCaja.appendChild(el("div", "cbctic-titulo", TXT.titulo));
    ui.subtitulo = el("div", "cbctic-subtitulo", TXT.subtituloActivo);
    tituloCaja.appendChild(ui.subtitulo);
    cabecera.appendChild(tituloCaja);
    const acciones = el("div", "cbctic-acciones");
    acciones.appendChild(boton("cbctic-accion", "⟳", confirmarNuevaConversacion, TXT.nuevaConv));
    acciones.appendChild(boton("cbctic-accion", "✕", cerrarVentana, TXT.cerrarChat));
    cabecera.appendChild(acciones);
    ui.ventana.appendChild(cabecera);

    // Área de mensajes
    ui.mensajes = el("div", "cbctic-mensajes");
    ui.mensajes.setAttribute("role", "log");
    ui.mensajes.setAttribute("aria-live", "polite");
    ui.mensajes.setAttribute("aria-label", TXT.areaMensajes);
    ui.ventana.appendChild(ui.mensajes);

    // Indicador "escribiendo…"
    ui.escribiendo = el("div", "cbctic-escribiendo");
    ui.escribiendo.hidden = true;
    const puntos = el("span", "cbctic-puntos");
    for (let i = 0; i < 3; i++) puntos.appendChild(el("span", "cbctic-punto"));
    ui.escribiendo.appendChild(puntos);
    ui.escribiendo.appendChild(el("span", "cbctic-escribiendo-texto", TXT.escribiendo));
    ui.ventana.appendChild(ui.escribiendo);

    // Pie: entrada de texto + enviar
    const pie = el("form", "cbctic-pie");
    pie.addEventListener("submit", function (ev) {
      ev.preventDefault();
      enviarTextoLibre();
    });
    ui.entrada = el("input", "cbctic-entrada");
    ui.entrada.type = "text";
    ui.entrada.placeholder = TXT.placeholder;
    ui.entrada.autocomplete = "off";
    ui.entrada.maxLength = 2000;
    ui.entrada.setAttribute("aria-label", TXT.entradaTexto);
    pie.appendChild(ui.entrada);
    ui.botonEnviar = el("button", "cbctic-enviar", "➤");
    ui.botonEnviar.type = "submit";
    ui.botonEnviar.setAttribute("aria-label", TXT.enviar);
    pie.appendChild(ui.botonEnviar);
    ui.ventana.appendChild(pie);

    ui.raiz.appendChild(ui.ventana);
    ui.raiz.appendChild(ui.burbuja);
    document.body.appendChild(ui.raiz);

    // Historial restaurado desde sessionStorage (tras recarga de página).
    estado.historial.forEach(function (item) {
      ui.mensajes.appendChild(renderItem(item));
    });
    actualizarSubtitulo();
  }

  /* ============================================================
   * 5. RENDER de mensajes
   * ============================================================ */

  /** Renderiza texto plano con saltos de línea y listas numeradas (1. / 1)). */
  function renderTextoEnriquecido(contenedor, texto) {
    const lineas = String(texto === undefined || texto === null ? "" : texto).split("\n");
    let listaActual = null;
    lineas.forEach(function (linea) {
      const item = linea.match(/^\s*(\d+)[.)]\s+(.*)$/);
      if (item) {
        if (!listaActual) {
          listaActual = el("ol", "cbctic-lista");
          listaActual.start = parseInt(item[1], 10) || 1;
          contenedor.appendChild(listaActual);
        }
        listaActual.appendChild(el("li", null, item[2]));
      } else {
        listaActual = null;
        if (linea.trim() === "") {
          contenedor.appendChild(el("div", "cbctic-linea-vacia"));
        } else {
          contenedor.appendChild(el("div", "cbctic-linea", linea));
        }
      }
    });
  }

  /** Crea el nodo DOM de un item del historial. */
  function renderItem(item) {
    if (item.rol === "usuario") {
      const fila = el("div", "cbctic-fila cbctic-fila-usuario");
      const burbujaMsg = el("div", "cbctic-msg cbctic-msg-usuario");
      renderTextoEnriquecido(burbujaMsg, item.texto);
      fila.appendChild(burbujaMsg);
      return fila;
    }

    if (item.rol === "sistema") {
      const fila = el("div", "cbctic-fila cbctic-fila-sistema");
      fila.appendChild(el("div", "cbctic-msg-sistema", item.texto));
      return fila;
    }

    // rol === 'agente' → mensaje escrito por personal humano del CTIC (handoff).
    if (item.rol === "agente") return renderAgente(item);

    // rol === 'bot'
    if (item.tipo === "handoff") return renderHandoff(item);

    const fila = el("div", "cbctic-fila cbctic-fila-bot");
    const burbujaMsg = el("div", "cbctic-msg cbctic-msg-bot");
    if (item.texto) renderTextoEnriquecido(burbujaMsg, item.texto);

    if (item.tipo === "encuesta") {
      burbujaMsg.appendChild(renderEncuesta(item));
    } else if (item.tipo === "adjunto") {
      burbujaMsg.appendChild(renderAdjunto(item));
    }
    // Cualquier tipo puede traer botones de opciones (el contrato lo permite
    // incluso en tipo "texto").
    if (Array.isArray(item.opciones) && item.opciones.length) {
      burbujaMsg.appendChild(renderOpciones(item));
    }
    fila.appendChild(burbujaMsg);
    return fila;
  }

  function renderOpciones(item) {
    const caja = el("div", "cbctic-opciones cbctic-interactivo");
    item.opciones.forEach(function (op) {
      const b = boton("cbctic-opcion", op.texto, function () {
        enviarMensaje({ opcionId: op.id }, op.texto);
      });
      if (item.usado) b.disabled = true;
      caja.appendChild(b);
    });
    return caja;
  }

  function renderEncuesta(item) {
    const caja = el("div", "cbctic-encuesta cbctic-interactivo");
    const estrellas = el("div", "cbctic-estrellas");
    estrellas.setAttribute("role", "group");
    estrellas.setAttribute("aria-label", TXT.encuestaAyuda);
    for (let n = 1; n <= 5; n++) {
      (function (valor) {
        const estrella = boton("cbctic-estrella", "★", function () {
          const marcadas = "★".repeat(valor) + "☆".repeat(5 - valor);
          Array.prototype.forEach.call(estrellas.children, function (hija, i) {
            if (i < valor) hija.classList.add("cbctic-elegida");
          });
          enviarMensaje({ opcionId: "calif_" + valor }, marcadas + " (" + valor + "/5)");
        }, TXT.calificarCon(valor));
        if (item.usado) estrella.disabled = true;
        estrellas.appendChild(estrella);
      })(n);
    }
    caja.appendChild(estrellas);
    return caja;
  }

  function renderAdjunto(item) {
    const caja = el("div", "cbctic-adjunto cbctic-interactivo");

    const entradaArchivo = document.createElement("input");
    entradaArchivo.type = "file";
    entradaArchivo.accept = ACCEPT_ADJUNTO;
    entradaArchivo.className = "cbctic-adjunto-input";
    entradaArchivo.setAttribute("aria-label", TXT.adjuntoInput);

    const fila = el("div", "cbctic-adjunto-botones");
    const bSeleccionar = boton("cbctic-opcion cbctic-adjunto-boton", "📎 " + TXT.adjuntoSeleccionar, function () {
      entradaArchivo.click();
    });
    const bOmitir = boton("cbctic-opcion cbctic-opcion-secundaria", TXT.adjuntoOmitir, function () {
      enviarMensaje({ opcionId: "__omitir__" }, TXT.adjuntoOmitir);
    });
    fila.appendChild(bSeleccionar);
    fila.appendChild(bOmitir);

    const ayuda = el("div", "cbctic-adjunto-ayuda", TXT.adjuntoAyuda);
    const aviso = el("div", "cbctic-adjunto-aviso", "");
    aviso.hidden = true;

    entradaArchivo.addEventListener("change", async function () {
      const archivo = entradaArchivo.files && entradaArchivo.files[0];
      if (!archivo) return;
      aviso.hidden = true;
      aviso.classList.remove("cbctic-adjunto-error");

      const nombre = archivo.name.toLowerCase();
      const extensionValida = EXTENSIONES_PERMITIDAS.some(function (ext) {
        return nombre.endsWith(ext);
      });
      if (!extensionValida) {
        aviso.textContent = TXT.adjuntoInvalidoTipo;
        aviso.classList.add("cbctic-adjunto-error");
        aviso.hidden = false;
        entradaArchivo.value = "";
        return;
      }
      if (archivo.size > MAX_ADJUNTO_BYTES) {
        aviso.textContent = TXT.adjuntoInvalidoTam;
        aviso.classList.add("cbctic-adjunto-error");
        aviso.hidden = false;
        entradaArchivo.value = "";
        return;
      }

      bSeleccionar.disabled = true;
      bOmitir.disabled = true;
      aviso.textContent = TXT.adjuntoSubiendo;
      aviso.hidden = false;
      try {
        const data = await apiSubirAdjunto(archivo);
        aviso.hidden = true;
        enviarMensaje(
          { opcionId: "__adjunto__", adjuntoId: data.adjuntoId },
          "📎 " + (data.nombreOriginal || archivo.name)
        );
      } catch (err) {
        console.error("[cbctic] Error al subir adjunto:", err);
        aviso.textContent =
          (err.envelope && err.envelope.message) || TXT.adjuntoError;
        aviso.classList.add("cbctic-adjunto-error");
        aviso.hidden = false;
        bSeleccionar.disabled = false;
        bOmitir.disabled = false;
        entradaArchivo.value = "";
      }
    });

    caja.appendChild(fila);
    caja.appendChild(ayuda);
    caja.appendChild(aviso);
    caja.appendChild(entradaArchivo);
    if (item.usado) {
      bSeleccionar.disabled = true;
      bOmitir.disabled = true;
    }
    return caja;
  }

  /** Burbuja de un mensaje del agente humano; se distingue de bot y usuario
   *  con la etiqueta "Personal CTIC" y el acento ámbar del handoff. */
  function renderAgente(item) {
    const fila = el("div", "cbctic-fila cbctic-fila-agente");
    const burbujaMsg = el("div", "cbctic-msg cbctic-msg-agente");
    const etiqueta = el("div", "cbctic-agente-etiqueta");
    etiqueta.appendChild(el("span", "cbctic-agente-icono", "🧑‍💻"));
    etiqueta.appendChild(el("span", null, TXT.etiquetaAgente));
    burbujaMsg.appendChild(etiqueta);
    renderTextoEnriquecido(burbujaMsg, item.texto);
    fila.appendChild(burbujaMsg);
    return fila;
  }

  function renderHandoff(item) {
    const fila = el("div", "cbctic-fila cbctic-fila-sistema");
    const banner = el("div", "cbctic-handoff");
    banner.appendChild(el("span", "cbctic-handoff-icono", "🧑‍💻"));
    const cuerpo = el("div", "cbctic-handoff-texto");
    renderTextoEnriquecido(cuerpo, item.texto);
    banner.appendChild(cuerpo);
    fila.appendChild(banner);
    return fila;
  }

  /** Agrega un item al historial, lo pinta, persiste y hace autoscroll. */
  function agregarItem(item) {
    estado.historial.push(item);
    const nodo = renderItem(item);
    ui.mensajes.appendChild(nodo);
    guardarSesion();
    // Textos largos (p. ej. Información de la FIIS): lleva la vista al inicio
    // de la respuesta para que no quede tapada abajo.
    const textoLargo =
      item.rol === "bot" && item.texto && String(item.texto).length > 600;
    if (textoLargo) {
      nodo.scrollIntoView({ block: "start", behavior: "smooth" });
    } else {
      autoscroll();
    }
    if (!estado.abierto && item.rol !== "usuario") {
      estado.noLeidos++;
      actualizarBadge();
    }
  }

  /** Aviso de sistema transitorio (con botones de acción); no se persiste. */
  function agregarAvisoTransitorio(texto, textoBoton, accion) {
    const fila = el("div", "cbctic-fila cbctic-fila-sistema cbctic-transitorio");
    if (texto) fila.appendChild(el("div", "cbctic-msg-sistema", texto));
    if (textoBoton && accion) {
      fila.appendChild(
        boton("cbctic-opcion cbctic-reintentar", textoBoton, function () {
          fila.remove();
          accion();
        })
      );
    }
    ui.mensajes.appendChild(fila);
    autoscroll();
    if (!estado.abierto) {
      estado.noLeidos++;
      actualizarBadge();
    }
  }

  function quitarAvisosTransitorios() {
    ui.mensajes.querySelectorAll(".cbctic-transitorio").forEach(function (n) {
      n.remove();
    });
  }

  /** Quita botones/entradas de mensajes anteriores para no tapar la respuesta. */
  function deshabilitarInteractivos() {
    estado.historial.forEach(function (item) {
      if (item.rol === "bot") {
        item.usado = true;
        // Conserva el texto; oculta las opciones ya elegidas del historial.
        if (Array.isArray(item.opciones)) item.opciones = [];
      }
    });
    ui.mensajes.querySelectorAll(".cbctic-interactivo").forEach(function (nodo) {
      nodo.remove();
    });
    guardarSesion();
  }

  function mostrarEscribiendo() {
    ui.escribiendo.hidden = false;
    autoscroll();
  }

  function ocultarEscribiendo() {
    ui.escribiendo.hidden = true;
  }

  function autoscroll() {
    ui.mensajes.scrollTop = ui.mensajes.scrollHeight;
  }

  function actualizarBadge() {
    if (estado.noLeidos > 0) {
      ui.badge.textContent = estado.noLeidos > 9 ? "9+" : String(estado.noLeidos);
      ui.badge.hidden = false;
      ui.badge.setAttribute("aria-label", TXT.noLeidos(estado.noLeidos));
    } else {
      ui.badge.hidden = true;
    }
  }

  function actualizarSubtitulo() {
    const pausado = estado.estadoBot === "PAUSED";
    ui.subtitulo.textContent = pausado ? TXT.subtituloPausado : TXT.subtituloActivo;
    ui.subtitulo.classList.toggle("cbctic-subtitulo-pausado", pausado);
  }

  function actualizarControlesEnvio() {
    ui.botonEnviar.disabled = estado.enviando;
  }

  /* ============================================================
   * 6. LÓGICA DE CONVERSACIÓN
   * ============================================================ */

  function alternarVentana() {
    if (estado.abierto) cerrarVentana();
    else abrirVentana();
  }

  function abrirVentana() {
    estado.abierto = true;
    ui.ventana.hidden = false;
    ui.burbuja.setAttribute("aria-expanded", "true");
    ui.burbuja.classList.add("cbctic-burbuja-abierta");
    estado.noLeidos = 0;
    actualizarBadge();
    autoscroll();
    if (!estado.sessionId && !estado.creandoSesion) {
      iniciarSesion();
    } else {
      ui.entrada.focus();
    }
  }

  function cerrarVentana() {
    estado.abierto = false;
    ui.ventana.hidden = true;
    ui.burbuja.setAttribute("aria-expanded", "false");
    ui.burbuja.classList.remove("cbctic-burbuja-abierta");
  }

  /** Crea la sesión de chat y pinta bienvenida + menú. */
  async function iniciarSesion() {
    if (estado.creandoSesion) return;
    estado.creandoSesion = true;
    quitarAvisosTransitorios();
    mostrarEscribiendo();
    try {
      const data = await apiCrearSesion();
      ocultarEscribiendo();
      estado.sessionId = data.sessionId;
      estado.sessionToken = data.sessionToken;
      estado.estadoBot = "ACTIVE";
      if (data.mensajeBienvenida) {
        agregarItem({ rol: "bot", tipo: "texto", texto: data.mensajeBienvenida });
      }
      if (Array.isArray(data.menu) && data.menu.length) {
        agregarItem({
          rol: "bot",
          tipo: "opciones",
          texto: TXT.eligeOpcion,
          opciones: data.menu,
          usado: false,
        });
      }
      guardarSesion();
      actualizarSubtitulo();
      conectarSSE(); // abre el canal en tiempo real para el handoff
      if (estado.abierto) ui.entrada.focus();
    } catch (err) {
      ocultarEscribiendo();
      console.error("[cbctic] Error al crear la sesión de chat:", err);
      agregarAvisoTransitorio(TXT.offline, TXT.reintentar, iniciarSesion);
    } finally {
      estado.creandoSesion = false;
    }
  }

  /** Procesa la lista de MensajeBot devuelta por el backend. */
  function procesarMensajesBot(mensajes) {
    mensajes.forEach(function (m) {
      agregarItem({
        rol: "bot",
        tipo: m.tipo || "texto",
        texto: m.texto,
        opciones: Array.isArray(m.opciones) ? m.opciones : undefined,
        usado: false,
      });
    });
  }

  /**
   * Envía un mensaje al backend.
   * @param {object} parcial  {texto} | {opcionId} | {opcionId, adjuntoId}
   * @param {string} eco      texto a mostrar como burbuja del usuario
   * @param {boolean} esReintento  no repite el eco ni re-deshabilita botones
   */
  async function enviarMensaje(parcial, eco, esReintento) {
    if (estado.enviando || !estado.sessionId) return;
    estado.enviando = true;
    actualizarControlesEnvio();
    quitarAvisosTransitorios();

    if (!esReintento) {
      deshabilitarInteractivos();
      if (eco) agregarItem({ rol: "usuario", texto: eco });
    }
    estado.ultimoEnvio = { parcial: parcial, eco: eco };
    mostrarEscribiendo();

    try {
      const cuerpo = Object.assign({ sessionId: estado.sessionId }, parcial);
      const data = await apiEnviarMensaje(cuerpo);
      ocultarEscribiendo();
      if (data.estadoBot) estado.estadoBot = data.estadoBot;
      procesarMensajesBot(Array.isArray(data.mensajes) ? data.mensajes : []);
      estado.ultimoEnvio = null;
      guardarSesion();
    } catch (err) {
      ocultarEscribiendo();
      manejarErrorEnvio(err);
    } finally {
      estado.enviando = false;
      actualizarControlesEnvio();
      actualizarSubtitulo();
    }
  }

  function manejarErrorEnvio(err) {
    console.error("[cbctic] Error al enviar mensaje:", err);

    // 401: token inválido/expirado → reiniciar sesión automáticamente.
    if (err.status === 401) {
      limpiarSesion();
      agregarItem({ rol: "sistema", texto: TXT.sesionExpirada });
      iniciarSesion();
      return;
    }

    // 409: la sesión fue cerrada (p. ej. inactividad RN-09).
    if (err.status === 409) {
      agregarItem({
        rol: "sistema",
        texto: (err.envelope && err.envelope.message) || TXT.sesionCerrada,
      });
      agregarAvisoTransitorio(null, TXT.nuevaConversacionBtn, function () {
        nuevaConversacion();
      });
      return;
    }

    // 429 / 5xx / error de red: disculpa + reintentar el último envío.
    if (err.esRed || err.status === 429 || err.status >= 500 || !err.status) {
      const texto = err.status === 429 ? TXT.errorLimite : TXT.errorEnvio;
      const pendiente = estado.ultimoEnvio;
      agregarAvisoTransitorio(texto, TXT.reintentar, function () {
        if (pendiente) enviarMensaje(pendiente.parcial, pendiente.eco, true);
      });
      return;
    }

    // Otros 4xx (400/403/404/422): se muestra el mensaje del envelope.
    agregarItem({
      rol: "sistema",
      texto: (err.envelope && err.envelope.message) || TXT.errorEnvio,
    });
  }

  function enviarTextoLibre() {
    const texto = ui.entrada.value.trim();
    if (!texto || estado.enviando) return;
    if (!estado.sessionId) {
      // Sesión aún no creada (p. ej. estaba offline): reintenta primero.
      iniciarSesion();
      return;
    }
    ui.entrada.value = "";
    enviarMensaje({ texto: texto }, texto);
    ui.entrada.focus();
  }

  function confirmarNuevaConversacion() {
    if (!window.confirm(TXT.confirmarNueva)) return;
    nuevaConversacion();
  }

  function nuevaConversacion() {
    limpiarSesion();
    estado.historial = [];
    estado.noLeidos = 0;
    actualizarBadge();
    while (ui.mensajes.firstChild) ui.mensajes.removeChild(ui.mensajes.firstChild);
    actualizarSubtitulo();
    iniciarSesion();
  }

  /* ============================================================
   * 7. TIEMPO REAL — SSE (handoff con agente humano, F-07)
   *
   * Canal de solo lectura. El widget del usuario nunca escribe por SSE:
   * sus mensajes siempre viajan por POST /chat/mensajes (el backend los
   * enruta al agente). Aquí solo se *reciben* los mensajes del agente y las
   * transiciones de estado. Es una mejora progresiva: si el navegador no
   * soporta EventSource o el canal falla, el chat sigue funcionando por POST
   * (los mensajes del agente aparecerán cuando el SSE vuelva a conectar).
   * ============================================================ */

  const SSE_BACKOFF_BASE = 2000; // ms; el backoff crece por reintento
  const SSE_BACKOFF_MAX = 30000; // ms; tope del backoff

  /** Clave estable para deduplicar un mensaje de agente (contenido + fecha),
   *  ya que el contrato del evento "agente" no incluye un id. */
  function claveMensajeAgente(texto, fecha) {
    return (fecha || "") + " " + (texto || "");
  }

  /** Abre el EventSource si hay sesión y el navegador lo soporta. Idempotente. */
  function conectarSSE() {
    if (!estado.sessionId || !estado.sessionToken) return;
    if (typeof EventSource === "undefined") return; // degradación: sigue por POST
    if (estado.eventSource) return; // ya hay un canal abierto

    const url =
      API_BASE +
      "/chat/stream?sessionId=" +
      encodeURIComponent(estado.sessionId) +
      "&token=" +
      encodeURIComponent(estado.sessionToken);

    let es;
    try {
      es = new EventSource(url);
    } catch (e) {
      return; // sin canal en tiempo real; el chat sigue por POST
    }
    estado.eventSource = es;

    es.addEventListener("open", function () {
      estado.sseReintentos = 0; // conexión establecida: se reinicia el backoff
    });

    es.addEventListener("agente", manejarEventoAgente);
    es.addEventListener("estado", manejarEventoEstado);
    es.addEventListener("encuesta", manejarEventoEncuesta);
    // Los comentarios ": heartbeat" no disparan eventos, así que se ignoran solos.

    es.addEventListener("error", function () {
      // EventSource reconecta solo mientras readyState === CONNECTING. Si el
      // navegador cerró el canal (CLOSED) hacemos un reintento con backoff suave.
      if (es.readyState === EventSource.CLOSED) {
        programarReconexionSSE();
      }
    });
  }

  /** Cierra el canal y cancela cualquier reconexión pendiente. */
  function cerrarSSE() {
    if (estado.sseTimer) {
      window.clearTimeout(estado.sseTimer);
      estado.sseTimer = null;
    }
    if (estado.eventSource) {
      try {
        estado.eventSource.close();
      } catch (e) {
        /* ignorar */
      }
      estado.eventSource = null;
    }
  }

  /** Reconexión manual con backoff cuando el navegador dio el canal por cerrado. */
  function programarReconexionSSE() {
    cerrarSSE();
    if (!estado.sessionId) return; // no reconectar sesiones descartadas
    estado.sseReintentos += 1;
    const espera = Math.min(SSE_BACKOFF_BASE * estado.sseReintentos, SSE_BACKOFF_MAX);
    estado.sseTimer = window.setTimeout(function () {
      estado.sseTimer = null;
      conectarSSE();
    }, espera);
  }

  function parsearDatosSSE(ev) {
    try {
      return JSON.parse(ev.data);
    } catch (e) {
      return null; // trama malformada: se ignora sin romper la conversación
    }
  }

  /** event: agente — mensaje escrito por un agente humano del CTIC. */
  function manejarEventoAgente(ev) {
    const datos = parsearDatosSSE(ev);
    if (!datos || !datos.texto) return;
    const clave = claveMensajeAgente(datos.texto, datos.fecha);
    if (estado.clavesAgente.has(clave)) return; // dedup ante reenvíos
    estado.clavesAgente.add(clave);
    ocultarEscribiendo();
    agregarItem({ rol: "agente", texto: datos.texto, fecha: datos.fecha });
  }

  /** event: estado — transición ACTIVE ↔ PAUSED del bot. */
  function manejarEventoEstado(ev) {
    const datos = parsearDatosSSE(ev);
    if (!datos || !datos.estadoBot) return;
    estado.estadoBot = datos.estadoBot === "PAUSED" ? "PAUSED" : "ACTIVE";
    guardarSesion();
    actualizarSubtitulo();
  }

  /** event: encuesta — un MensajeBot de tipo "encuesta" tras cerrar el handoff. */
  function manejarEventoEncuesta(ev) {
    const datos = parsearDatosSSE(ev);
    if (!datos) return;
    // Dedup: si ya hay una encuesta pendiente (por reenvío o por el POST), no se repite.
    const yaOfrecida = estado.historial.some(function (item) {
      return item.rol === "bot" && item.tipo === "encuesta" && !item.usado;
    });
    if (yaOfrecida) return;
    ocultarEscribiendo();
    agregarItem({
      rol: "bot",
      tipo: "encuesta",
      texto: datos.texto,
      opciones: Array.isArray(datos.opciones) ? datos.opciones : undefined,
      usado: false,
    });
  }

  /* ============================================================
   * 8. ARRANQUE
   * ============================================================ */

  function iniciar() {
    inyectarEstilos();
    cargarSesion();
    construirUI();
    // Sesión restaurada tras recargar la página: reabre el canal en tiempo real.
    if (estado.sessionId) conectarSSE();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
