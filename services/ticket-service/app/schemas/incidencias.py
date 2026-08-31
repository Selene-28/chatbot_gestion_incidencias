"""Schemas de request de incidencias (API-01, API-03) con validaciones de prd/01 §4."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.models import AREAS, ORIGENES, PRIORIDADES
from app.schemas import comunes


def _error(codigo: str, mensaje: str) -> PydanticCustomError:
    """Error de validación con mensaje en español (sin prefijo 'Value error')."""
    return PydanticCustomError(codigo, mensaje)


class IncidenciaCreate(BaseModel):
    """Cuerpo de POST /api/incidencias (API-01)."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    nombre: str
    correo: str
    area: str
    categoria: str
    subcategoria: str | None = None
    descripcion: str
    prioridad: str = "Media"
    origen: str = "chatbot"
    conversacion_codigo: str | None = Field(default=None, alias="conversacionCodigo")
    adjunto_id: str | None = Field(default=None, alias="adjuntoId")

    @field_validator("nombre")
    @classmethod
    def _validar_nombre(cls, valor: str) -> str:
        if not (comunes.NOMBRE_MIN <= len(valor) <= comunes.NOMBRE_MAX) or comunes.contiene_html(
            valor
        ):
            raise _error("nombre_invalido", comunes.MSG_NOMBRE)
        return valor

    @field_validator("correo")
    @classmethod
    def _validar_correo(cls, valor: str) -> str:
        valor = comunes.normalizar_correo(valor)
        if not comunes.tiene_formato_correo(valor):
            raise _error("correo_invalido", comunes.MSG_CORREO_FORMATO)
        if not comunes.es_correo_institucional(valor):
            raise _error("correo_no_institucional", comunes.MSG_CORREO_DOMINIO)
        return valor

    @field_validator("area")
    @classmethod
    def _validar_area(cls, valor: str) -> str:
        if valor not in AREAS:
            raise _error(
                "area_invalida",
                f"El área debe ser una de: {', '.join(AREAS)}.",
            )
        return valor

    @field_validator("categoria")
    @classmethod
    def _validar_categoria(cls, valor: str) -> str:
        if not valor:
            raise _error("categoria_vacia", "La categoría es obligatoria.")
        return valor

    @field_validator("descripcion")
    @classmethod
    def _validar_descripcion(cls, valor: str) -> str:
        if not (comunes.DESCRIPCION_MIN <= len(valor) <= comunes.DESCRIPCION_MAX):
            raise _error("descripcion_invalida", comunes.MSG_DESCRIPCION)
        return valor

    @field_validator("prioridad")
    @classmethod
    def _validar_prioridad(cls, valor: str) -> str:
        if valor not in PRIORIDADES:
            raise _error(
                "prioridad_invalida",
                f"La prioridad debe ser una de: {', '.join(PRIORIDADES)}.",
            )
        return valor

    @field_validator("origen")
    @classmethod
    def _validar_origen(cls, valor: str) -> str:
        if valor not in ORIGENES:
            raise _error(
                "origen_invalido",
                f"El origen debe ser uno de: {', '.join(ORIGENES)}.",
            )
        return valor


class EscalarRequest(BaseModel):
    """Cuerpo de PUT /api/incidencias/escalar (API-03)."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    ticket_id: str = Field(alias="ticketId")
    motivo: str
    correo: str

    @field_validator("ticket_id")
    @classmethod
    def _validar_ticket(cls, valor: str) -> str:
        if not comunes.es_codigo_ticket(valor):
            raise _error("ticket_invalido", comunes.MSG_TICKET_FORMATO)
        return valor.strip()

    @field_validator("motivo")
    @classmethod
    def _validar_motivo(cls, valor: str) -> str:
        if not (3 <= len(valor) <= 1000):
            raise _error(
                "motivo_invalido", "El motivo debe tener entre 3 y 1000 caracteres."
            )
        return valor

    @field_validator("correo")
    @classmethod
    def _validar_correo(cls, valor: str) -> str:
        valor = comunes.normalizar_correo(valor)
        if not comunes.es_correo_institucional(valor):
            raise _error("correo_invalido", comunes.MSG_CORREO_DOMINIO)
        return valor
