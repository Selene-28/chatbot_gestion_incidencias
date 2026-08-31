"""Schema de request de la encuesta de satisfacción (API-06, RN-04)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.schemas import comunes


class EncuestaCreate(BaseModel):
    """Cuerpo de POST /api/encuesta: ticketId o conversacionCodigo, al menos uno."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    ticket_id: str | None = Field(default=None, alias="ticketId")
    conversacion_codigo: str | None = Field(default=None, alias="conversacionCodigo")
    calificacion: int
    comentario: str | None = None

    @field_validator("ticket_id")
    @classmethod
    def _validar_ticket(cls, valor: str | None) -> str | None:
        if valor is not None and not comunes.es_codigo_ticket(valor):
            raise PydanticCustomError("ticket_invalido", comunes.MSG_TICKET_FORMATO)
        return valor

    @field_validator("calificacion")
    @classmethod
    def _validar_calificacion(cls, valor: int) -> int:
        if not (comunes.CALIFICACION_MIN <= valor <= comunes.CALIFICACION_MAX):
            raise PydanticCustomError("calificacion_invalida", comunes.MSG_CALIFICACION)
        return valor

    @field_validator("comentario")
    @classmethod
    def _validar_comentario(cls, valor: str | None) -> str | None:
        if valor is not None and len(valor) > comunes.COMENTARIO_MAX:
            raise PydanticCustomError(
                "comentario_largo",
                f"El comentario no debe superar los {comunes.COMENTARIO_MAX} caracteres.",
            )
        return valor or None

    @model_validator(mode="after")
    def _validar_referencia(self) -> "EncuestaCreate":
        if not self.ticket_id and not self.conversacion_codigo:
            raise PydanticCustomError(
                "referencia_faltante",
                "Debe indicar el ticket o la conversación que desea calificar.",
            )
        return self
