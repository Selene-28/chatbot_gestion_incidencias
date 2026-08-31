"""F-06 · Escalar incidencia (prd/05).

1. Solicita el nº de ticket (o lo toma del contexto de sesión si ya se consultó).
2. Solicita el motivo (texto libre, 10–500 caracteres).
3. PUT /api/incidencias/escalar (API-03) validando propiedad por correo.
4. Confirmación con el texto oficial del DRS.
5. Errores: 404 → reintento del código; 409 (Resuelto/Cerrado) → explica y
   ofrece registrar una nueva incidencia.
"""

from typing import Any

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.dialogo import textos, validaciones
from app.dialogo.engine import Deps, Resultado
from app.dialogo.tipos import Entrada, MensajeBot, con_opciones, texto_plano
from app.models import Conversacion

_OPCIONES_CIERRE = [("menu", "Volver al menú"), ("finalizar", "Finalizar")]
_OPCIONES_NO_ESCALABLE = [
    ("registrar_incidencia", "📝 Registrar nueva incidencia"),
    ("menu", "Volver al menú"),
]
_OPCIONES_REINTENTO = [("reintentar", "🔄 Reintentar"), ("menu", "Volver al menú")]

_PROMPT_CORREO = texto_plano(
    "Para escalar una incidencia necesito tu correo institucional (@unac.edu.pe)."
)
_PROMPT_CODIGO = texto_plano(
    "Indícame el número del ticket que deseas escalar (formato INC-AAAA-NNNN)."
)


def _prompt_motivo(codigo: str) -> MensajeBot:
    return texto_plano(
        f"Cuéntame el motivo por el que deseas escalar el ticket {codigo} "
        "(entre 10 y 500 caracteres)."
    )


class FlujoEscalar:
    """Máquina de estados de F-06."""

    nombre = "escalar_incidencia"

    async def iniciar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        """Pide correo si hace falta; toma el ticket del contexto si existe."""
        if not conv.usuario_correo:
            return Resultado(mensajes=[_PROMPT_CORREO], paso="correo")
        return self._tras_identificacion(ctx)

    def _tras_identificacion(self, ctx: dict[str, Any]) -> Resultado:
        codigo = ctx["datos"].get("codigo") or ctx["sesion"].get("ultimo_ticket")
        if codigo:
            ctx["datos"]["codigo"] = codigo
            return Resultado(mensajes=[_prompt_motivo(codigo)], paso="motivo")
        return Resultado(mensajes=[_PROMPT_CODIGO], paso="codigo")

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        """Despacha la entrada al manejador del paso actual."""
        if paso == "correo":
            return self._paso_correo(conv, entrada, ctx)
        if paso == "codigo":
            return self._paso_codigo(entrada, ctx)
        if paso == "motivo":
            return await self._paso_motivo(conv, entrada, ctx, deps)
        return Resultado(mensajes=[_PROMPT_CODIGO], paso="codigo")

    # ----------------------------------------------------------------- pasos

    def _paso_correo(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any]
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
        conv.usuario_correo = correo
        return self._tras_identificacion(ctx)

    def _paso_codigo(self, entrada: Entrada, ctx: dict[str, Any]) -> Resultado:
        codigo = validaciones.extraer_ticket(entrada.texto or "")
        if not codigo:
            return Resultado(
                mensajes=[
                    texto_plano(
                        "El número de ticket no tiene el formato INC-AAAA-NNNN. "
                        "Inténtalo nuevamente."
                    )
                ],
                invalida=True,
            )
        ctx["datos"]["codigo"] = codigo
        return Resultado(mensajes=[_prompt_motivo(codigo)], paso="motivo")

    async def _paso_motivo(
        self, conv: Conversacion, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        if entrada.opcion_id == "reintentar" and ctx["datos"].get("motivo"):
            return await self._escalar(conv, ctx, deps)
        motivo = validaciones.validar_motivo(entrada.texto or "")
        if not motivo:
            return Resultado(
                mensajes=[
                    texto_plano(
                        "El motivo debe tener entre 10 y 500 caracteres. "
                        "Descríbelo nuevamente, por favor."
                    )
                ],
                invalida=True,
            )
        ctx["datos"]["motivo"] = motivo
        return await self._escalar(conv, ctx, deps)

    async def _escalar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        codigo = ctx["datos"]["codigo"]
        try:
            await deps.tickets.escalar(
                codigo, ctx["datos"]["motivo"], conv.usuario_correo or ""
            )
        except NotFoundError:
            ctx["datos"].pop("codigo", None)
            ctx["sesion"].pop("ultimo_ticket", None)
            return Resultado(
                mensajes=[
                    texto_plano(
                        f"No encontré el ticket {codigo}. Verifica el número, por favor."
                    ),
                    _PROMPT_CODIGO,
                ],
                paso="codigo",
            )
        except ForbiddenError:
            ctx["datos"].pop("codigo", None)
            return Resultado(
                mensajes=[
                    texto_plano(
                        f"El ticket {codigo} no pertenece a tu correo institucional, "
                        "por lo que no puedo escalarlo. Puedes indicarme otro número."
                    ),
                    _PROMPT_CODIGO,
                ],
                paso="codigo",
            )
        except ConflictError:
            # Estado no escalable (Resuelto/Cerrado): explicar y ofrecer nueva incidencia
            return Resultado(
                mensajes=[
                    con_opciones(
                        f"El ticket {codigo} se encuentra en un estado que ya no permite "
                        "escalarlo (por ejemplo, Resuelto o Cerrado). Si el problema "
                        "persiste, puedo ayudarte a registrar una nueva incidencia.",
                        _OPCIONES_NO_ESCALABLE,
                    )
                ],
                terminar=True,
            )
        except AppError as exc:
            return Resultado(
                mensajes=[con_opciones(exc.message, _OPCIONES_REINTENTO)],
                paso="motivo",
            )
        ctx["sesion"]["ultimo_ticket"] = codigo
        ctx["sesion"]["atencion"] = True
        return Resultado(
            mensajes=[
                texto_plano(textos.ESCALADO_CONFIRMACION, meta={"intent": self.nombre}),
                con_opciones("¿Necesitas algo más?", _OPCIONES_CIERRE),
            ],
            terminar=True,
        )
