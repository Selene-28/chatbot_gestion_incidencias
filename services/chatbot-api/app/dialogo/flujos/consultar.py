"""F-03 · Consultar estado de incidencia (prd/05).

- Solicita el correo institucional si la sesión no está identificada.
- Consulta por número de ticket o por correo (lista de hasta 10 botones).
- 403 → mensaje sin revelar datos del ticket ajeno (RN-03); 404 → reintentar
  o volver al menú.
"""

from typing import Any

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.dialogo import validaciones
from app.dialogo.engine import Deps, Resultado
from app.dialogo.tipos import Entrada, MensajeBot, Opcion, con_opciones, texto_plano
from app.models import Conversacion

_OPCIONES_MODO = [
    ("modo_codigo", "Por número de ticket"),
    ("modo_correo", "Por mi correo"),
]
_OPCIONES_TRAS_ERROR = [("menu", "Volver al menú")]
_OPCIONES_CIERRE = [("menu", "Volver al menú"), ("finalizar", "Finalizar")]
_OPCIONES_SIN_TICKETS = [
    ("registrar_incidencia", "📝 Registrar incidencia"),
    ("menu", "Volver al menú"),
]

_PROMPT_CORREO = texto_plano(
    "Para consultar tus incidencias necesito tu correo institucional (@unac.edu.pe)."
)
_PROMPT_MODO = con_opciones("¿Cómo deseas consultar tu incidencia?", _OPCIONES_MODO)
_PROMPT_CODIGO = texto_plano("Indícame el número de ticket (formato INC-AAAA-NNNN).")


def _detalle_ticket(data: dict[str, Any]) -> str:
    """Formatea el detalle de API-02 (estado, categoría, fechas, técnico)."""
    tecnico = data.get("tecnico") or "Aún no asignado"
    return (
        f"Estado de la incidencia {data.get('ticketId')}:\n\n"
        f"• Estado: {data.get('estado')}\n"
        f"• Categoría: {data.get('categoria')}\n"
        f"• Fecha de registro: {data.get('fechaRegistro')}\n"
        f"• Técnico asignado: {tecnico}\n"
        f"• Última actualización: {data.get('ultimaActualizacion')}\n"
        f"• Observaciones: {data.get('observaciones')}"
    )


class FlujoConsultar:
    """Máquina de estados de F-03."""

    nombre = "consultar_estado"

    async def iniciar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        """Pide correo si hace falta; si llegó un código en el mensaje, consulta directo."""
        if not conv.usuario_correo:
            return Resultado(mensajes=[_PROMPT_CORREO], paso="correo")
        if ctx["datos"].get("codigo"):
            return await self._consultar_codigo(conv, ctx["datos"]["codigo"], ctx, deps)
        return Resultado(mensajes=[_PROMPT_MODO], paso="modo")

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        """Despacha la entrada al manejador del paso actual."""
        if paso == "correo":
            return await self._paso_correo(conv, entrada, ctx, deps)
        if paso == "modo":
            return await self._paso_modo(conv, entrada, ctx, deps)
        if paso == "codigo":
            return await self._paso_codigo(conv, entrada, ctx, deps)
        if paso == "elegir":
            return await self._paso_elegir(conv, entrada, ctx, deps)
        return Resultado(mensajes=[_PROMPT_MODO], paso="modo")

    # ----------------------------------------------------------------- pasos

    async def _paso_correo(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        correo = validaciones.validar_correo(entrada.texto or "")
        if not correo:
            return Resultado(
                mensajes=[
                    texto_plano(
                        "El correo debe pertenecer al dominio institucional @unac.edu.pe. "
                        "Inténtalo nuevamente."
                    )
                ],
                invalida=True,
            )
        conv.usuario_correo = correo  # RF-15
        if ctx["datos"].get("codigo"):
            return await self._consultar_codigo(conv, ctx["datos"]["codigo"], ctx, deps)
        return Resultado(mensajes=[_PROMPT_MODO], paso="modo")

    async def _paso_modo(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        opcion = entrada.opcion_id or validaciones.normalizar(entrada.texto or "")
        if opcion in ("modo_codigo", "por numero de ticket"):
            return Resultado(mensajes=[_PROMPT_CODIGO], paso="codigo")
        if opcion in ("modo_correo", "por mi correo"):
            return await self._listar_por_correo(conv, ctx, deps)
        codigo = validaciones.extraer_ticket(entrada.texto or "")
        if codigo:
            return await self._consultar_codigo(conv, codigo, ctx, deps)
        return Resultado(
            mensajes=[
                texto_plano("Por favor, elige una de las dos opciones."),
                _PROMPT_MODO,
            ],
            invalida=True,
        )

    async def _paso_codigo(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        if entrada.opcion_id == "reintentar":
            return Resultado(mensajes=[_PROMPT_CODIGO], paso="codigo")
        codigo = validaciones.extraer_ticket(entrada.texto or "")
        if not codigo:
            return Resultado(
                mensajes=[
                    texto_plano(
                        "El número de ticket no tiene el formato INC-AAAA-NNNN "
                        "(ej. INC-2026-0001). Inténtalo nuevamente."
                    )
                ],
                invalida=True,
            )
        return await self._consultar_codigo(conv, codigo, ctx, deps)

    async def _paso_elegir(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        codigo = entrada.opcion_id or validaciones.extraer_ticket(entrada.texto or "")
        disponibles = ctx["datos"].get("tickets") or []
        if not codigo or codigo not in disponibles:
            return Resultado(
                mensajes=[texto_plano("Por favor, selecciona uno de tus tickets de la lista.")],
                invalida=True,
            )
        return await self._consultar_codigo(conv, codigo, ctx, deps)

    # ------------------------------------------------------------- consultas

    async def _consultar_codigo(
        self, conv: Conversacion, codigo: str, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        try:
            data = await deps.tickets.consultar_ticket(codigo, conv.usuario_correo or "")
        except ForbiddenError:
            # RN-03: no revelar información del ticket ajeno
            return Resultado(
                mensajes=[
                    con_opciones(
                        f"El ticket {codigo} no pertenece a tu correo institucional, "
                        "por lo que no puedo mostrarte su información. "
                        "Puedes escribir otro número de ticket.",
                        _OPCIONES_TRAS_ERROR,
                    )
                ],
                paso="codigo",
            )
        except NotFoundError:
            return Resultado(
                mensajes=[
                    con_opciones(
                        f"No encontré el ticket {codigo}. Verifica el número e "
                        "inténtalo nuevamente escribiendo otro código.",
                        _OPCIONES_TRAS_ERROR,
                    )
                ],
                paso="codigo",
            )
        except AppError as exc:
            return Resultado(
                mensajes=[con_opciones(exc.message, _OPCIONES_TRAS_ERROR)],
                paso="codigo",
            )
        ctx["sesion"]["ultimo_ticket"] = str(data.get("ticketId"))
        ctx["sesion"]["atencion"] = True
        return Resultado(
            mensajes=[
                texto_plano(_detalle_ticket(data), meta={"intent": self.nombre}),
                con_opciones("¿Necesitas algo más?", _OPCIONES_CIERRE),
            ],
            terminar=True,
        )

    async def _listar_por_correo(
        self, conv: Conversacion, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        try:
            items = await deps.tickets.listar_por_correo(conv.usuario_correo or "")
        except AppError as exc:
            return Resultado(
                mensajes=[con_opciones(exc.message, _OPCIONES_TRAS_ERROR)],
                paso="modo",
            )
        if not items:
            return Resultado(
                mensajes=[
                    con_opciones(
                        "No encontré incidencias registradas con tu correo. "
                        "¿Deseas registrar una nueva?",
                        _OPCIONES_SIN_TICKETS,
                    )
                ],
                terminar=True,
            )
        # máx. 10 botones (el ticket-service ya limita a 10)
        botones = [
            (str(t["ticketId"]), f"{t['ticketId']} — {t['estado']}") for t in items[:10]
        ]
        ctx["datos"]["tickets"] = [b[0] for b in botones]
        return Resultado(
            mensajes=[
                MensajeBot(
                    tipo="opciones",
                    texto="Estas son tus incidencias más recientes. Selecciona una para ver "
                    "su detalle:",
                    opciones=[Opcion(id=i, texto=t) for i, t in botones],
                )
            ],
            paso="elegir",
        )
