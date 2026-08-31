"""Dobles de prueba: cliente de tickets en memoria (misma interfaz que TicketsClient)."""

from typing import Any

from app.core.errors import ConflictError, ForbiddenError, NotFoundError


class FakeTicketsClient:
    """Simula el ticket-service; registra las llamadas para las aserciones."""

    def __init__(self) -> None:
        self.registros: list[tuple[dict[str, Any], str]] = []
        self.escalados: list[tuple[str, str, str]] = []
        self.encuestas: list[dict[str, Any]] = []
        self.adjuntos: list[str] = []
        # tickets conocidos: codigo -> {"correo": ..., "detalle": {...}, "escalable": bool}
        self.tickets: dict[str, dict[str, Any]] = {}
        self.listados: dict[str, list[dict[str, Any]]] = {}
        self.proximo_ticket_id = "INC-2026-0001"
        self.fallo_siguiente: Exception | None = None
        self.encuesta_conflicto = False

    def _tal_vez_fallar(self) -> None:
        if self.fallo_siguiente is not None:
            exc, self.fallo_siguiente = self.fallo_siguiente, None
            raise exc

    async def registrar_incidencia(
        self, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        self._tal_vez_fallar()
        self.registros.append((payload, idempotency_key))
        return {"ticketId": self.proximo_ticket_id, "estado": "Registrado"}

    async def consultar_ticket(self, codigo: str, correo: str) -> dict[str, Any]:
        self._tal_vez_fallar()
        ticket = self.tickets.get(codigo)
        if ticket is None:
            raise NotFoundError("La incidencia no fue encontrada.")
        if ticket["correo"] != correo:
            raise ForbiddenError("No tiene permiso para consultar esta incidencia.")
        return ticket["detalle"]

    async def listar_por_correo(self, correo: str) -> list[dict[str, Any]]:
        self._tal_vez_fallar()
        return self.listados.get(correo, [])

    async def escalar(self, codigo: str, motivo: str, correo: str) -> dict[str, Any]:
        self._tal_vez_fallar()
        ticket = self.tickets.get(codigo)
        if ticket is None:
            raise NotFoundError("La incidencia no fue encontrada.")
        if ticket["correo"] != correo:
            raise ForbiddenError("No tiene permiso para escalar esta incidencia.")
        if not ticket.get("escalable", True):
            raise ConflictError("La incidencia no puede escalarse en su estado actual.")
        self.escalados.append((codigo, motivo, correo))
        return {"estado": "Escalado"}

    async def registrar_encuesta(
        self,
        calificacion: int,
        comentario: str | None = None,
        ticket_id: str | None = None,
        conversacion_codigo: str | None = None,
    ) -> dict[str, Any]:
        self._tal_vez_fallar()
        if self.encuesta_conflicto:
            raise ConflictError("La atención ya fue calificada.")
        self.encuestas.append(
            {
                "calificacion": calificacion,
                "comentario": comentario,
                "ticketId": ticket_id,
                "conversacionCodigo": conversacion_codigo,
            }
        )
        return {}

    async def subir_adjunto(self, filename: str, content: bytes, mime: str) -> dict[str, Any]:
        self._tal_vez_fallar()
        adjunto_id = f"adj_{len(self.adjuntos):08d}"
        self.adjuntos.append(adjunto_id)
        return {"adjuntoId": adjunto_id}


def detalle_ticket(codigo: str, estado: str = "En Proceso") -> dict[str, Any]:
    """Payload de detalle como lo devuelve API-02."""
    return {
        "ticketId": codigo,
        "estado": estado,
        "categoria": "Correo Institucional",
        "fechaRegistro": "2026-06-18T09:15:00",
        "tecnico": "Paul Barzola",
        "ultimaActualizacion": "2026-06-18T10:30:00",
        "observaciones": "Incidencia asignada al área de soporte.",
        "respuesta": None,
    }


class FakeEmbedder:
    """Embedder determinista para tests del stack RAG (sin modelo real).

    Vector = conteo (normalizado por Chroma vía coseno) de palabras de un
    vocabulario fijo: textos que comparten vocabulario quedan cercanos y los
    ajenos quedan ortogonales (similitud ~0, bajo el umbral).
    """

    VOCABULARIO = (
        "wifi",
        "red",
        "internet",
        "correo",
        "contraseña",
        "password",
        "matlab",
        "licencia",
        "aula",
        "virtual",
        "campus",
    )

    def encode(self, textos: list[str]) -> list[list[float]]:
        vectores = []
        for texto in textos:
            palabras = texto.lower().split()
            vector = [float(palabras.count(v)) for v in self.VOCABULARIO]
            vector.append(1e-9)  # evita el vector cero (coseno indefinido)
            vectores.append(vector)
        return vectores
