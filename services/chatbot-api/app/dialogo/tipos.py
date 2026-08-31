"""Tipos compartidos del protocolo de chat (contrato con el widget, prd/04 §4)."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

TipoMensaje = Literal["texto", "opciones", "adjunto", "encuesta", "handoff"]

# opcionId reservado: el widget lo envía junto con adjuntoId tras subir un archivo
OPCION_ADJUNTO = "__adjunto__"


class Opcion(BaseModel):
    """Botón que el widget renderiza bajo un mensaje del bot."""

    id: str
    texto: str


class MensajeBot(BaseModel):
    """Mensaje del bot hacia el widget (protocolo compartido — EXACTO)."""

    tipo: TipoMensaje
    texto: str
    opciones: list[Opcion] | None = None
    meta: dict[str, Any] | None = None

    def a_dict(self) -> dict[str, Any]:
        """Serializa omitiendo claves None (payload limpio para el widget)."""
        return self.model_dump(exclude_none=True)


@dataclass(frozen=True)
class Entrada:
    """Entrada del usuario en un turno: texto libre o botón (con adjunto opcional)."""

    texto: str | None = None
    opcion_id: str | None = None
    adjunto_id: str | None = None


def texto_plano(texto: str, meta: dict[str, Any] | None = None) -> MensajeBot:
    """Mensaje simple de texto."""
    return MensajeBot(tipo="texto", texto=texto, meta=meta)


def con_opciones(
    texto: str, opciones: list[tuple[str, str]], meta: dict[str, Any] | None = None
) -> MensajeBot:
    """Mensaje con botones [(id, texto), ...]."""
    return MensajeBot(
        tipo="opciones",
        texto=texto,
        opciones=[Opcion(id=i, texto=t) for i, t in opciones],
        meta=meta,
    )
