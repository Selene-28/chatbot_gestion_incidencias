"""F-02 · Registrar incidencia (happy path del DRS, prd/05).

Pasos: identificación (nombre → código institucional → correo, se salta si
la sesión ya está identificada) → escuela → categoría → descripción →
prioridad → adjunto → confirmación → creado.

- La Idempotency-Key (UUID) se genera al entrar a `confirmacion` y se mantiene
  durante los reintentos, evitando tickets duplicados (REN-02/REN-05).
- Si el ticket-service falla: disculpa + botón Reintentar SIN perder el
  contexto capturado.
- `Corregir` pregunta qué campo cambiar y vuelve a `confirmacion`;
  `Cancelar` descarta los datos y vuelve al menú.
"""

from typing import Any
from uuid import uuid4

from app.core.errors import AppError
from app.dialogo import textos, validaciones
from app.dialogo.engine import Deps, Resultado
from app.dialogo.flujos.menu import menu_principal
from app.dialogo.tipos import (
    OPCION_ADJUNTO,
    Entrada,
    MensajeBot,
    Opcion,
    con_opciones,
    texto_plano,
)
from app.models import Conversacion

# --- Opciones de botones -------------------------------------------------------

_OPCIONES_ESCUELA = [(f"escuela_{validaciones.normalizar(e)}", e) for e in validaciones.ESCUELAS]
_OPCIONES_CATEGORIA = [(f"cat_{i}", c) for i, c in enumerate(validaciones.CATEGORIAS)]
_OPCIONES_PRIORIDAD = [
    (f"prio_{validaciones.normalizar(p)}", p if p != "Media" else "Media (sugerida)")
    for p in validaciones.PRIORIDADES
]
_OPCIONES_CONFIRMACION = [
    ("confirmar", "✅ Confirmar"),
    ("corregir", "✏️ Corregir"),
    ("cancelar", "❌ Cancelar"),
]
_OPCIONES_REINTENTO = [("reintentar", "🔄 Reintentar"), ("cancelar", "❌ Cancelar")]

# Orden natural de captura y dato que cubre cada paso. Un paso se salta si su
# dato ya está en el contexto (p. ej. pre-llenado por el diagnóstico F-05).
_ORDEN_PASOS: tuple[tuple[str, str], ...] = (
    ("nombre", "nombre"),
    ("codigo", "codigo"),
    ("correo", "correo"),
    ("area", "area"),
    ("categoria", "categoria"),
    ("descripcion", "descripcion"),
    ("prioridad", "prioridad"),
    ("adjunto", "adjunto_id"),
)

_CAMPOS_CORREGIBLES: list[tuple[str, str]] = [
    ("campo_nombre", "Nombre"),
    ("campo_codigo", "Código Institucional"),
    ("campo_correo", "Correo"),
    ("campo_area", "Escuela"),
    ("campo_categoria", "Categoría"),
    ("campo_descripcion", "Descripción"),
    ("campo_prioridad", "Prioridad"),
    ("campo_adjunto", "Adjunto"),
]

# --- Prompts por paso -----------------------------------------------------------


def _prompt(paso: str) -> MensajeBot:
    """Mensaje de solicitud de dato para cada paso de captura."""
    prompts: dict[str, MensajeBot] = {
        "nombre": texto_plano(
            "Con gusto te ayudo a registrar tu incidencia. "
            "Para comenzar, indícame tu nombre completo."
        ),
        "codigo": texto_plano(
            "Indícame tu código institucional "
            f"(recuerda que debe tener exactamente {validaciones.CODIGO_INSTITUCIONAL_DIGITOS} "
            "dígitos)."
        ),
        "correo": texto_plano("Ahora indícame tu correo institucional (@unac.edu.pe)."),
        "area": con_opciones("¿A qué escuela perteneces?", _OPCIONES_ESCUELA),
        "categoria": con_opciones(
            "Selecciona la categoría que mejor describe tu incidencia:",
            _OPCIONES_CATEGORIA,
        ),
        "descripcion": texto_plano(
            "Describe brevemente el problema (entre 10 y 2000 caracteres)."
        ),
        "prioridad": con_opciones(
            "¿Qué prioridad consideras que tiene? La prioridad final la confirma el técnico.",
            _OPCIONES_PRIORIDAD,
        ),
        "adjunto": MensajeBot(
            tipo="adjunto",
            texto=(
                "¿Deseas adjuntar evidencia? Puedes subir una imagen JPG/PNG "
                "o un PDF de hasta 5 MB."
            ),
            opciones=[Opcion(id="omitir", texto="Omitir")],
        ),
    }
    return prompts[paso]


def _resumen(conv: Conversacion, datos: dict[str, Any]) -> MensajeBot:
    """Resumen de los datos capturados + Confirmar / Corregir / Cancelar."""
    adjunto = "Sí (1 archivo)" if datos.get("adjunto_id") else "Sin adjunto"
    texto = (
        "Por favor, confirma los datos de tu incidencia:\n\n"
        f"• Nombre: {datos.get('nombre')}\n"
        f"• Código Institucional: {datos.get('codigo')}\n"
        f"• Correo: {datos.get('correo')}\n"
        f"• Escuela: {datos.get('area')}\n"
        f"• Categoría: {datos.get('categoria')}\n"
        f"• Descripción: {datos.get('descripcion')}\n"
        f"• Prioridad: {datos.get('prioridad')}\n"
        f"• Evidencia: {adjunto}"
    )
    return con_opciones(texto, _OPCIONES_CONFIRMACION)


class FlujoRegistrar:
    """Máquina de estados de F-02."""

    nombre = "registrar_incidencia"

    async def iniciar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        """Arranca en el primer paso cuyo dato falte.

        Salta la identificación si la sesión ya se identificó y cualquier paso
        cubierto por datos pre-llenados (p. ej. por el diagnóstico F-05).
        """
        datos = ctx["datos"]
        if conv.usuario_nombre and conv.usuario_correo:
            datos.setdefault("nombre", conv.usuario_nombre)
            datos.setdefault("correo", conv.usuario_correo)
        primero = self._siguiente_pendiente(datos, "nombre")
        if primero == "confirmacion":
            return self._a_confirmacion(conv, ctx)
        return Resultado(mensajes=[_prompt(primero)], paso=primero)

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        """Despacha la entrada al manejador del paso actual."""
        manejadores = {
            "nombre": self._paso_nombre,
            "codigo": self._paso_codigo,
            "correo": self._paso_correo,
            "area": self._paso_area,
            "categoria": self._paso_categoria,
            "descripcion": self._paso_descripcion,
            "prioridad": self._paso_prioridad,
            "adjunto": self._paso_adjunto,
            "confirmacion": None,  # async con deps, se maneja aparte
            "corregir": None,
        }
        if paso == "confirmacion":
            return await self._paso_confirmacion(conv, entrada, ctx, deps)
        if paso == "corregir":
            return self._paso_corregir(entrada, ctx)
        manejador = manejadores.get(paso)
        if manejador is None:
            return Resultado(mensajes=[_prompt("nombre")], paso="nombre")
        return manejador(conv, entrada, ctx)

    # ------------------------------------------------------------- pasos captura

    def _avanzar(self, ctx: dict[str, Any], conv: Conversacion, siguiente: str) -> Resultado:
        """Va al siguiente paso pendiente (salta los datos ya cubiertos), o de
        vuelta a confirmación si corregía un campo."""
        if ctx["datos"].pop("_corrigiendo", None):
            return self._a_confirmacion(conv, ctx)
        siguiente = self._siguiente_pendiente(ctx["datos"], siguiente)
        if siguiente == "confirmacion":
            return self._a_confirmacion(conv, ctx)
        return Resultado(mensajes=[_prompt(siguiente)], paso=siguiente)

    @staticmethod
    def _siguiente_pendiente(datos: dict[str, Any], desde: str) -> str:
        """Primer paso desde `desde` cuyo dato aún no está capturado.

        El adjunto es opcional pero se ofrece siempre que no venga pre-cargado;
        si todo está cubierto, se pasa directo a la confirmación.
        """
        nombres = [paso for paso, _campo in _ORDEN_PASOS]
        for paso, campo in _ORDEN_PASOS[nombres.index(desde) :]:
            if not datos.get(campo):
                return paso
        return "confirmacion"

    def _invalida(self, mensaje: str, prompt: MensajeBot | None = None) -> Resultado:
        """Re-solicita el dato con un mensaje de ayuda (cuenta intento inválido)."""
        mensajes = [texto_plano(mensaje)]
        if prompt is not None:
            mensajes.append(prompt)
        return Resultado(mensajes=mensajes, invalida=True)

    def _paso_nombre(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        nombre = validaciones.validar_nombre(entrada.texto or "")
        if not nombre:
            return self._invalida(
                "El nombre debe tener entre 3 y 120 caracteres, sin símbolos < ni >. "
                "Por favor, escríbelo nuevamente."
            )
        ctx["datos"]["nombre"] = nombre
        conv.usuario_nombre = nombre
        return self._avanzar(ctx, conv, "codigo")

    def _paso_codigo(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        codigo = validaciones.validar_codigo_institucional(entrada.texto or "")
        if not codigo:
            return self._invalida(
                "El código institucional debe tener exactamente "
                f"{validaciones.CODIGO_INSTITUCIONAL_DIGITOS} dígitos numéricos. "
                "Por favor, escríbelo nuevamente."
            )
        ctx["datos"]["codigo"] = codigo
        return self._avanzar(ctx, conv, "correo")

    def _paso_correo(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        correo = validaciones.validar_correo(entrada.texto or "")
        if not correo:
            return self._invalida(
                "El correo debe ser válido y pertenecer al dominio institucional "
                "@unac.edu.pe (ej. jperez@unac.edu.pe). Inténtalo nuevamente."
            )
        ctx["datos"]["correo"] = correo
        conv.usuario_correo = correo  # RF-15: la sesión queda identificada
        return self._avanzar(ctx, conv, "area")

    def _paso_area(self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]) -> Resultado:
        area = self._elegir(entrada, _OPCIONES_ESCUELA, validaciones.ESCUELAS)
        if not area:
            return self._invalida(
                "Por favor, selecciona una de las escuelas disponibles.", _prompt("area")
            )
        ctx["datos"]["area"] = area
        return self._avanzar(ctx, conv, "categoria")

    def _paso_categoria(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        categoria = self._elegir(entrada, _OPCIONES_CATEGORIA, validaciones.CATEGORIAS)
        if not categoria:
            return self._invalida(
                "Por favor, selecciona una de las categorías disponibles.",
                _prompt("categoria"),
            )
        ctx["datos"]["categoria"] = categoria
        return self._avanzar(ctx, conv, "descripcion")

    def _paso_descripcion(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        descripcion = validaciones.validar_descripcion(entrada.texto or "")
        if not descripcion:
            return self._invalida(
                "La descripción debe tener entre 10 y 2000 caracteres. "
                "Cuéntame el problema con un poco más de detalle."
            )
        ctx["datos"]["descripcion"] = descripcion
        return self._avanzar(ctx, conv, "prioridad")

    def _paso_prioridad(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        prioridad = self._elegir(entrada, _OPCIONES_PRIORIDAD, validaciones.PRIORIDADES)
        if not prioridad:
            return self._invalida(
                "Por favor, selecciona una prioridad: Baja, Media o Alta.",
                _prompt("prioridad"),
            )
        ctx["datos"]["prioridad"] = prioridad
        return self._avanzar(ctx, conv, "adjunto")

    def _paso_adjunto(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        if entrada.opcion_id == OPCION_ADJUNTO and entrada.adjunto_id:
            ctx["datos"]["adjunto_id"] = entrada.adjunto_id
            ctx["datos"].pop("_corrigiendo", None)
            return self._a_confirmacion(conv, ctx)
        # "__omitir__": id que envía el botón Omitir propio del widget (ver widget/README.md)
        if entrada.opcion_id in ("omitir", "__omitir__") or validaciones.normalizar(
            entrada.texto or ""
        ) in (
            "omitir",
            "no",
            "no gracias",
        ):
            ctx["datos"].pop("adjunto_id", None)
            ctx["datos"].pop("_corrigiendo", None)
            return self._a_confirmacion(conv, ctx)
        return self._invalida(
            'Sube un archivo JPG/PNG/PDF de hasta 5 MB o pulsa "Omitir".',
            _prompt("adjunto"),
        )

    # -------------------------------------------------------- confirmación/creación

    def _a_confirmacion(self, conv: Conversacion, ctx: dict[str, Any]) -> Resultado:
        """Entra a confirmación generando la Idempotency-Key del intento (REN-02)."""
        ctx["datos"]["idempotency_key"] = str(uuid4())
        return Resultado(mensajes=[_resumen(conv, ctx["datos"])], paso="confirmacion")

    async def _paso_confirmacion(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        opcion = entrada.opcion_id or validaciones.normalizar(entrada.texto or "")
        if opcion in ("confirmar", "reintentar", "si"):
            return await self._crear_ticket(conv, ctx, deps)
        if opcion == "corregir":
            return Resultado(
                mensajes=[con_opciones("¿Qué campo deseas corregir?", _CAMPOS_CORREGIBLES)],
                paso="corregir",
            )
        if opcion == "cancelar":
            return Resultado(
                mensajes=[
                    texto_plano("He cancelado el registro de la incidencia."),
                    menu_principal(),
                ],
                terminar=True,
            )
        return self._invalida(
            "Por favor, elige Confirmar, Corregir o Cancelar.",
            _resumen(conv, ctx["datos"]),
        )

    async def _crear_ticket(
        self, conv: Conversacion, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        datos = ctx["datos"]
        prefijo_codigo = f"Código institucional: {datos['codigo']}\n\n"
        # Recorte de seguridad: el ticket-service valida descripción <= 2000
        # caracteres (misma cota que aquí); el prefijo no debe hacerla exceder.
        espacio_disponible = 2000 - len(prefijo_codigo)
        descripcion_con_codigo = prefijo_codigo + datos["descripcion"][:espacio_disponible]
        payload = {
            "nombre": datos["nombre"],
            "correo": datos["correo"],
            "area": datos["area"],
            "categoria": datos["categoria"],
            "descripcion": descripcion_con_codigo,
            "prioridad": datos.get("prioridad") or validaciones.PRIORIDAD_DEFAULT,
            "origen": "chatbot",
            "conversacionCodigo": conv.codigo,
            "adjuntoId": datos.get("adjunto_id"),
        }
        try:
            data = await deps.tickets.registrar_incidencia(payload, datos["idempotency_key"])
        except AppError as exc:
            # REN-05: disculpa + Reintentar sin perder el contexto capturado
            return Resultado(
                mensajes=[con_opciones(exc.message, _OPCIONES_REINTENTO)],
                paso="confirmacion",
            )
        ticket_id = str(data.get("ticketId"))
        ctx["sesion"]["ultimo_ticket"] = ticket_id
        ctx["sesion"]["atencion"] = True
        return Resultado(
            mensajes=[
                texto_plano(
                    textos.ticket_registrado(ticket_id),
                    meta={"intent": self.nombre, "ticketId": ticket_id},
                ),
                menu_principal("¿Puedo ayudarte en algo más?"),
            ],
            terminar=True,
        )

    def _paso_corregir(self, entrada: Entrada, ctx: dict[str, Any]) -> Resultado:
        opcion = entrada.opcion_id or ""
        if not opcion and entrada.texto:
            texto_norm = validaciones.normalizar(entrada.texto)
            for campo_id, etiqueta in _CAMPOS_CORREGIBLES:
                if validaciones.normalizar(etiqueta) == texto_norm:
                    opcion = campo_id
                    break
        if opcion.startswith("campo_"):
            paso = opcion.removeprefix("campo_")
            ctx["datos"]["_corrigiendo"] = True
            return Resultado(mensajes=[_prompt(paso)], paso=paso)
        return self._invalida(
            "Por favor, indica qué campo deseas corregir.",
            con_opciones("¿Qué campo deseas corregir?", _CAMPOS_CORREGIBLES),
        )

    # ----------------------------------------------------------------- utilidades

    @staticmethod
    def _elegir(
        entrada: Entrada, opciones_botones: list[tuple[str, str]], lista: tuple[str, ...]
    ) -> str | None:
        """Resuelve una elección por opcionId de botón o por texto libre."""
        if entrada.opcion_id:
            for indice, (opcion_id, _texto) in enumerate(opciones_botones):
                if entrada.opcion_id == opcion_id:
                    return lista[indice]
            return None
        if entrada.texto:
            return validaciones.elegir_de_lista(entrada.texto, lista)
        return None
