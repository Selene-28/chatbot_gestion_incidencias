"""F-08 · Encuesta de satisfacción (prd/05, RN-04).

- Mensaje oficial + botones calif_1..calif_5, luego comentario opcional u
  "Omitir".
- API-06 con ticketId si la atención generó/consultó un ticket; si no, con
  conversacionCodigo.
- Se ofrece UNA sola vez por atención (RN-04). Al terminar: cierre cortés y
  la conversación se marca cerrada (motivo `usuario`).
"""

from typing import Any

from app.core.errors import AppError, ConflictError
from app.dialogo import textos, validaciones
from app.dialogo.engine import Deps, Resultado
from app.dialogo.tipos import Entrada, MensajeBot, Opcion, texto_plano
from app.models import Conversacion

_OPCIONES_CALIFICACION = [Opcion(id=f"calif_{n}", texto=f"⭐ {n}") for n in range(1, 6)]
_OPCION_OMITIR = Opcion(id="omitir", texto="Omitir")


def _mensaje_encuesta() -> MensajeBot:
    """Solicitud oficial de calificación (tipo 'encuesta', ids calif_1..calif_5)."""
    return MensajeBot(
        tipo="encuesta",
        texto=textos.ENCUESTA_SOLICITUD,
        opciones=list(_OPCIONES_CALIFICACION),
    )


class FlujoEncuesta:
    """Máquina de estados de F-08."""

    nombre = "encuesta"

    async def iniciar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        """Ofrece la encuesta (si ya se ofreció en esta atención, cierra cortésmente)."""
        if ctx["sesion"].get("encuesta_ofrecida"):
            return self._cierre(conv)
        ctx["sesion"]["encuesta_ofrecida"] = True  # RN-04: una vez por atención
        return Resultado(mensajes=[_mensaje_encuesta()], paso="calificacion")

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        """Despacha la entrada al manejador del paso actual."""
        if paso == "calificacion":
            return self._paso_calificacion(entrada, ctx)
        if paso == "comentario":
            return await self._paso_comentario(conv, entrada, ctx, deps)
        return self._cierre(conv)

    # ----------------------------------------------------------------- pasos

    def _paso_calificacion(self, entrada: Entrada, ctx: dict[str, Any]) -> Resultado:
        calificacion: int | None = None
        if entrada.opcion_id and entrada.opcion_id.startswith("calif_"):
            sufijo = entrada.opcion_id.removeprefix("calif_")
            calificacion = int(sufijo) if sufijo in {"1", "2", "3", "4", "5"} else None
        elif entrada.texto:
            calificacion = validaciones.validar_calificacion(entrada.texto)
        if calificacion is None:
            return Resultado(
                mensajes=[
                    texto_plano("Por favor, selecciona una calificación del 1 al 5."),
                    _mensaje_encuesta(),
                ],
                invalida=True,
            )
        ctx["datos"]["calificacion"] = calificacion
        return Resultado(
            mensajes=[
                MensajeBot(
                    tipo="opciones",
                    texto="¿Deseas agregar un comentario? (opcional)",
                    opciones=[_OPCION_OMITIR],
                )
            ],
            paso="comentario",
        )

    async def _paso_comentario(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        comentario: str | None = None
        if entrada.opcion_id != "omitir":
            comentario = (entrada.texto or "").strip() or None
            if comentario and len(comentario) > validaciones.COMENTARIO_MAX:
                return Resultado(
                    mensajes=[
                        texto_plano(
                            "El comentario no debe superar los 500 caracteres. "
                            'Resúmelo, por favor, o pulsa "Omitir".'
                        )
                    ],
                    invalida=True,
                )
        mensajes: list[MensajeBot] = []
        try:
            await deps.tickets.registrar_encuesta(
                calificacion=int(ctx["datos"]["calificacion"]),
                comentario=comentario,
                ticket_id=ctx["sesion"].get("ultimo_ticket"),
                conversacion_codigo=(
                    None if ctx["sesion"].get("ultimo_ticket") else conv.codigo
                ),
            )
            ctx["sesion"]["encuesta_registrada"] = True
            mensajes.append(texto_plano("¡Gracias por tu calificación!"))
        except ConflictError:
            # RN-04: ya existía una encuesta para esta atención
            mensajes.append(
                texto_plano("Ya registramos una calificación para esta atención. ¡Gracias!")
            )
        except AppError:
            mensajes.append(
                texto_plano(
                    "No pude registrar tu calificación en este momento, "
                    "pero agradezco mucho tu opinión."
                )
            )
        resultado = self._cierre(conv)
        return Resultado(mensajes=mensajes + resultado.mensajes, terminar=True)

    def _cierre(self, conv: Conversacion) -> Resultado:
        """Cierre cortés: despedida oficial + conversación cerrada (motivo usuario)."""
        from app.services import sesiones

        sesiones.marcar_cierre(conv, motivo="usuario")
        return Resultado(mensajes=[texto_plano(textos.DESPEDIDA)], terminar=True)
