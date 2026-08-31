"""F-05 · Diagnóstico básico guiado (QA-04, prd/05).

Árboles de decisión ESTÁTICOS y data-driven (sin LLM), uno por categoría:
Internet/WiFi (el del PRD, literal), Aula Virtual, Correo institucional y
Software institucional. Cada árbol es un grafo de nodos:

- `Pregunta`: pregunta con botones; la respuesta elegida decide la rama y se
  registra en la ruta del diagnóstico (QA-04: las respuestas cambian según lo
  respondido).
- `Pasos`: instrucciones numeradas + «¿Se resolvió el problema?» (Sí/No).

Nodo final:
- Sí → cierre feliz, se marca la atención (habilita la encuesta F-08 al
  despedirse) y se muestra el menú.
- No → se encadena el registro de incidencia F-02 PRE-LLENANDO categoría y
  descripción (compuesta con la ruta del árbol y los pasos ya intentados),
  para no repreguntar lo cubierto por el diagnóstico.
"""

from dataclasses import dataclass
from typing import Any

from app.dialogo import validaciones
from app.dialogo.engine import Deps, Resultado
from app.dialogo.flujos.menu import menu_principal
from app.dialogo.tipos import Entrada, MensajeBot, con_opciones, texto_plano
from app.models import Conversacion

# --- Modelo de datos de los árboles --------------------------------------------


@dataclass(frozen=True)
class Rama:
    """Opción de una pregunta: botón + destino + cómo se resume la respuesta."""

    id: str
    etiqueta: str
    destino: str
    resumen: str


@dataclass(frozen=True)
class Pregunta:
    """Nodo de decisión: pregunta con botones."""

    texto: str
    ramas: tuple[Rama, ...]


@dataclass(frozen=True)
class Pasos:
    """Nodo de instrucciones: pasos numerados + «¿Se resolvió?»."""

    intro: str
    pasos: tuple[str, ...]
    resumen: str  # cómo se describen estos pasos en la incidencia pre-llenada


@dataclass(frozen=True)
class Arbol:
    """Árbol de diagnóstico de una categoría."""

    clave: str
    categoria: str  # categoría de F-02 (validaciones.CATEGORIAS)
    titulo: str  # para la descripción compuesta
    inicio: str
    nodos: dict[str, Pregunta | Pasos]


# --- Árbol Internet/WiFi (diagrama F-05 del PRD, literal) ----------------------

_ARBOL_INTERNET = Arbol(
    clave="internet",
    categoria="Internet/WiFi",
    titulo="conexión a internet",
    inicio="conexion",
    nodos={
        "conexion": Pregunta(
            "Vamos a revisar tu conexión paso a paso. "
            "¿Estás conectado mediante WiFi o cable de red?",
            (
                Rama("wifi", "WiFi", "ve_red", "conexión por WiFi"),
                Rama("cable", "Cable de red", "pasos_cable", "conexión por cable de red"),
            ),
        ),
        "ve_red": Pregunta(
            "¿Ves la red «UNAC» en la lista de redes disponibles de tu equipo?",
            (
                Rama("red_si", "Sí, la veo", "autentica", "sí ve la red UNAC"),
                Rama("red_no", "No la veo", "pasos_no_ve_red", "no ve la red UNAC"),
            ),
        ),
        "autentica": Pregunta(
            "¿Tu equipo se conecta a la red pero no puedes navegar?",
            (
                Rama(
                    "navega_no",
                    "Sí, se conecta pero no navego",
                    "pasos_portal",
                    "autentica pero no navega",
                ),
                Rama(
                    "conecta_no",
                    "No, no logra conectarse",
                    "pasos_credenciales",
                    "no logra autenticarse en la red",
                ),
            ),
        ),
        "pasos_no_ve_red": Pasos(
            "Prueba estos pasos para que tu equipo detecte la red:",
            (
                "Desactiva y vuelve a activar el WiFi de tu equipo.",
                "Acércate al punto de acceso más cercano (la cobertura varía por pabellón).",
                "Olvida la red «UNAC» en tu equipo y vuelve a conectarte.",
            ),
            "activar y desactivar el WiFi, acercarse al punto de acceso, "
            "olvidar y reconectar la red",
        ),
        "pasos_portal": Pasos(
            "Prueba estos pasos para recuperar la navegación:",
            (
                "Verifica que el portal cautivo se haya abierto e inicia sesión en él.",
                "Renueva la dirección IP: desconéctate de la red y vuelve a conectarte.",
                "Prueba a navegar con otro navegador.",
            ),
            "revisar el portal cautivo, renovar la IP y probar otro navegador",
        ),
        "pasos_credenciales": Pasos(
            "Prueba estos pasos con tus credenciales institucionales:",
            (
                "Verifica que estás usando tu usuario y contraseña institucionales vigentes.",
                "Si olvidaste tu contraseña, sigue el procedimiento de recuperación "
                "publicado en la base de conocimiento del CTIC.",
                "Intenta conectarte nuevamente a la red «UNAC».",
            ),
            "verificar las credenciales institucionales",
        ),
        "pasos_cable": Pasos(
            "Prueba estos pasos con tu conexión por cable:",
            (
                "Verifica que el cable esté firmemente conectado al equipo y al punto de red.",
                "Prueba el mismo cable en otro punto de red, o el punto con otro equipo.",
                "Reinicia el equipo con el cable conectado.",
            ),
            "verificar el cable y el punto de red, probar con otro equipo",
        ),
    },
)

# --- Árbol Aula Virtual ---------------------------------------------------------

_ARBOL_AULA = Arbol(
    clave="aula_virtual",
    categoria="Aula Virtual",
    titulo="Aula Virtual",
    inicio="sintoma",
    nodos={
        "sintoma": Pregunta(
            "Entiendo, revisemos el Aula Virtual. "
            "¿Cuál de estas situaciones describe mejor tu problema?",
            (
                Rama(
                    "aula_credenciales",
                    "No puedo iniciar sesión",
                    "pasos_credenciales",
                    "no puede iniciar sesión",
                ),
                Rama("aula_cursos", "No veo mis cursos", "pasos_cursos", "no ve sus cursos"),
                Rama(
                    "aula_carga",
                    "La plataforma no carga o da error",
                    "pasos_carga",
                    "la plataforma no carga o muestra errores",
                ),
            ),
        ),
        "pasos_credenciales": Pasos(
            "Prueba estos pasos con tus credenciales:",
            (
                "Verifica que tu usuario y contraseña sean los mismos que usas en el SGA.",
                "Si olvidaste tu contraseña, restablécela desde el SGA y vuelve a intentar.",
                "Escribe las credenciales manualmente, sin usar el autocompletado.",
            ),
            "verificar las credenciales del SGA y restablecer la contraseña",
        ),
        "pasos_cursos": Pasos(
            "Prueba estos pasos para ver tus cursos:",
            (
                "Verifica en el SGA que tu matrícula del ciclo esté registrada.",
                "Considera que los cursos pueden tardar hasta 48 horas en "
                "sincronizarse después de la matrícula.",
                "Cierra sesión en el Aula Virtual y vuelve a ingresar.",
            ),
            "verificar la matrícula en el SGA y esperar la sincronización de cursos",
        ),
        "pasos_carga": Pasos(
            "Prueba estos pasos para que la plataforma cargue:",
            (
                "Borra la caché y las cookies de tu navegador.",
                "Prueba con otro navegador o en una ventana de incógnito.",
                "Verifica tu conexión a internet abriendo otra página.",
            ),
            "borrar caché y cookies, probar otro navegador y revisar la conexión",
        ),
    },
)

# --- Árbol Correo institucional -------------------------------------------------

_ARBOL_CORREO = Arbol(
    clave="correo",
    categoria="Correo Institucional",
    titulo="correo institucional",
    inicio="sintoma",
    nodos={
        "sintoma": Pregunta(
            "Revisemos tu correo institucional. "
            "¿Cuál de estas situaciones describe mejor tu problema?",
            (
                Rama(
                    "correo_olvido",
                    "Olvidé mi contraseña",
                    "pasos_recuperacion",
                    "olvidó su contraseña",
                ),
                Rama(
                    "correo_bloqueo",
                    "Mi cuenta está bloqueada",
                    "pasos_bloqueo",
                    "su cuenta está bloqueada",
                ),
                Rama(
                    "correo_recepcion",
                    "No recibo mensajes",
                    "pasos_recepcion",
                    "no recibe mensajes",
                ),
            ),
        ),
        "pasos_recuperacion": Pasos(
            "Sigue estos pasos para recuperar tu contraseña:",
            (
                "Ingresa a la página de inicio de sesión del correo y usa la opción "
                "«¿Olvidaste tu contraseña?».",
                "Completa la verificación con tu correo personal alterno registrado.",
                "Define una contraseña nueva que cumpla los requisitos de seguridad.",
            ),
            "recuperar la contraseña con la opción «¿Olvidaste tu contraseña?»",
        ),
        "pasos_bloqueo": Pasos(
            "Sigue estos pasos para desbloquear tu cuenta:",
            (
                "Espera 15 minutos: los bloqueos por intentos fallidos se liberan "
                "automáticamente.",
                "Restablece tu contraseña con la opción «¿Olvidaste tu contraseña?».",
                "Cierra las sesiones guardadas en otros dispositivos, ya que pueden "
                "reintentar la contraseña anterior y bloquear la cuenta de nuevo.",
            ),
            "esperar el desbloqueo automático y restablecer la contraseña",
        ),
        "pasos_recepcion": Pasos(
            "Sigue estos pasos para revisar la recepción de mensajes:",
            (
                "Revisa la carpeta de correo no deseado (spam).",
                "Verifica el espacio disponible de tu buzón y elimina mensajes "
                "antiguos si está lleno.",
                "Confirma con el remitente que tu dirección esté bien escrita "
                "(@unac.edu.pe).",
            ),
            "revisar spam, espacio del buzón y la dirección de destino",
        ),
    },
)

# --- Árbol Software institucional ------------------------------------------------

_ARBOL_SOFTWARE = Arbol(
    clave="software",
    categoria="Software Institucional",
    titulo="software institucional",
    inicio="sistema",
    nodos={
        "sistema": Pregunta(
            "Entiendo, revisemos el software institucional. "
            "¿Con qué sistema tienes problemas?",
            (
                Rama("soft_sga", "SGA", "pasos_sga", "problema con el SGA"),
                Rama("soft_office", "Office 365", "pasos_office", "problema con Office 365"),
                Rama(
                    "soft_turnitin", "Turnitin", "pasos_turnitin", "problema con Turnitin"
                ),
                Rama("soft_otro", "Otro sistema", "pasos_otro", "problema con otro sistema"),
            ),
        ),
        "pasos_sga": Pasos(
            "Prueba estos pasos con el SGA:",
            (
                "Cierra sesión en el SGA y vuelve a ingresar.",
                "Borra la caché del navegador o usa una ventana de incógnito.",
                "Verifica si el problema también ocurre desde otro dispositivo.",
            ),
            "reingresar al SGA, borrar caché y probar desde otro dispositivo",
        ),
        "pasos_office": Pasos(
            "Prueba estos pasos con Office 365:",
            (
                "Verifica que inicias sesión con tu correo institucional (@unac.edu.pe).",
                "Cierra sesión en office.com y vuelve a ingresar.",
                "Si falla la aplicación de escritorio, repara la instalación desde el "
                "panel de control.",
            ),
            "verificar la cuenta institucional y reparar la instalación de Office",
        ),
        "pasos_turnitin": Pasos(
            "Prueba estos pasos con Turnitin:",
            (
                "Verifica que tu docente te haya inscrito en el curso correspondiente.",
                "Confirma que el archivo cumpla el formato y el tamaño permitidos.",
                "Intenta la entrega desde otro navegador.",
            ),
            "verificar la inscripción al curso, el formato del archivo y otro navegador",
        ),
        "pasos_otro": Pasos(
            "Prueba estos pasos generales:",
            (
                "Cierra la aplicación por completo y ábrela nuevamente.",
                "Reinicia el equipo y verifica tu conexión a internet.",
                "Anota el mensaje de error exacto: servirá para la incidencia.",
            ),
            "reiniciar la aplicación y el equipo, y anotar el mensaje de error",
        ),
    },
)

ARBOLES: dict[str, Arbol] = {
    a.clave: a for a in (_ARBOL_INTERNET, _ARBOL_AULA, _ARBOL_CORREO, _ARBOL_SOFTWARE)
}

# Intent del router → árbol de diagnóstico (tabla prd/01 §2, intents 5-7)
ARBOL_POR_INTENT: dict[str, str] = {
    "problema_internet": "internet",
    "problema_aula_virtual": "aula_virtual",
    "problema_software": "software",
}

# --- Textos y opciones ------------------------------------------------------------

_PASO_SELECCION = "seleccion"

_PREGUNTA_SELECCION = con_opciones(
    "Con gusto te ayudo con un diagnóstico guiado. ¿Con qué servicio tienes problemas?",
    [
        ("arbol_internet", "🌐 Internet/WiFi"),
        ("arbol_aula_virtual", "🎓 Aula Virtual"),
        ("arbol_correo", "📧 Correo institucional"),
        ("arbol_software", "💻 Software institucional"),
    ],
)

_OPCIONES_RESUELTO: list[tuple[str, str]] = [
    ("resuelto_si", "Sí, se resolvió"),
    ("resuelto_no", "No, el problema continúa"),
]

_PREGUNTA_RESUELTO = "¿Se resolvió el problema con estos pasos?"

_CIERRE_FELIZ = (
    "¡Excelente! Me alegra que el problema se haya resuelto. "
    "Si vuelve a presentarse, no dudes en escribirme."
)

_TRANSICION_REGISTRO = (
    "Lamento que el problema persista. Registremos una incidencia para que un "
    "técnico del CTIC te atienda: ya tomé nota de la categoría y de lo que "
    "revisamos en el diagnóstico, así no tendrás que repetirlo."
)


class FlujoDiagnostico:
    """Máquina de estados de F-05 (los árboles son datos, no código)."""

    nombre = "diagnostico"

    async def iniciar(self, conv: Conversacion, ctx: dict[str, Any], deps: Deps) -> Resultado:
        """Arranca en el árbol indicado, o pregunta el servicio si no se conoce."""
        datos = ctx["datos"]
        datos.setdefault("respuestas", [])
        datos.setdefault("pasos_probados", [])
        arbol = ARBOLES.get(datos.get("arbol") or "")
        if arbol is None:
            return Resultado(mensajes=[_PREGUNTA_SELECCION], paso=_PASO_SELECCION)
        return self._mostrar_nodo(arbol, arbol.inicio, datos)

    async def procesar(
        self, conv: Conversacion, paso: str, entrada: Entrada, ctx: dict[str, Any], deps: Deps
    ) -> Resultado:
        """Avanza por el árbol según la respuesta del usuario."""
        datos = ctx["datos"]
        if paso == _PASO_SELECCION:
            return self._paso_seleccion(entrada, datos)

        arbol = ARBOLES.get(datos.get("arbol") or "")
        nodo = arbol.nodos.get(paso) if arbol else None
        if arbol is None or nodo is None:
            # estado inconsistente (p. ej. datos corruptos): reiniciar el flujo
            return Resultado(mensajes=[_PREGUNTA_SELECCION], paso=_PASO_SELECCION)

        if isinstance(nodo, Pregunta):
            return self._paso_pregunta(arbol, nodo, entrada, datos)
        return self._paso_resolucion(arbol, nodo, entrada, ctx)

    # -------------------------------------------------------------------- pasos

    def _paso_seleccion(self, entrada: Entrada, datos: dict[str, Any]) -> Resultado:
        """Elección del árbol cuando el diagnóstico se inició sin categoría."""
        eleccion = entrada.opcion_id or ""
        if eleccion.startswith("arbol_"):
            eleccion = eleccion.removeprefix("arbol_")
        elif entrada.texto:
            texto = validaciones.normalizar(entrada.texto)
            for clave, candidato in ARBOLES.items():
                if validaciones.normalizar(candidato.categoria) == texto or clave == texto:
                    eleccion = clave
                    break
        arbol = ARBOLES.get(eleccion)
        if arbol is None:
            return Resultado(
                mensajes=[
                    texto_plano("Por favor, selecciona uno de los servicios disponibles."),
                    _PREGUNTA_SELECCION,
                ],
                invalida=True,
            )
        datos["arbol"] = arbol.clave
        return self._mostrar_nodo(arbol, arbol.inicio, datos)

    def _paso_pregunta(
        self, arbol: Arbol, nodo: Pregunta, entrada: Entrada, datos: dict[str, Any]
    ) -> Resultado:
        """Registra la rama elegida y muestra el nodo destino (QA-04)."""
        rama = self._elegir_rama(nodo, entrada)
        if rama is None:
            return Resultado(
                mensajes=[
                    texto_plano("Por favor, selecciona una de las opciones disponibles."),
                    self._mensaje_pregunta(nodo),
                ],
                invalida=True,
            )
        datos["respuestas"].append(rama.resumen)
        return self._mostrar_nodo(arbol, rama.destino, datos)

    def _paso_resolucion(
        self, arbol: Arbol, nodo: Pasos, entrada: Entrada, ctx: dict[str, Any]
    ) -> Resultado:
        """Nodo final «¿Se resolvió?»: cierre feliz o registro pre-llenado."""
        respuesta = self._si_o_no(entrada)
        if respuesta is None:
            return Resultado(
                mensajes=[
                    texto_plano("Por favor, indícame si el problema se resolvió (Sí o No)."),
                    con_opciones(_PREGUNTA_RESUELTO, _OPCIONES_RESUELTO),
                ],
                invalida=True,
            )
        if respuesta:
            # cierre feliz: cuenta como atención (habilita la encuesta F-08)
            ctx["sesion"]["atencion"] = True
            return Resultado(
                mensajes=[
                    texto_plano(_CIERRE_FELIZ),
                    menu_principal("¿Puedo ayudarte en algo más?"),
                ],
                terminar=True,
            )
        # no se resolvió → F-02 pre-llenado (categoría + descripción compuesta)
        return Resultado(
            mensajes=[texto_plano(_TRANSICION_REGISTRO)],
            terminar=True,
            siguiente_flujo="registrar_incidencia",
            siguiente_datos={
                "categoria": arbol.categoria,
                "descripcion": self._descripcion(arbol, ctx["datos"]),
            },
        )

    # -------------------------------------------------------------- utilidades

    def _mostrar_nodo(
        self, arbol: Arbol, nodo_id: str, datos: dict[str, Any]
    ) -> Resultado:
        """Renderiza un nodo (pregunta o pasos + «¿Se resolvió?»)."""
        nodo = arbol.nodos[nodo_id]
        datos["nodo"] = nodo_id
        if isinstance(nodo, Pregunta):
            return Resultado(mensajes=[self._mensaje_pregunta(nodo)], paso=nodo_id)
        datos["pasos_probados"].append(nodo.resumen)
        listado = "\n".join(f"{i}. {p}" for i, p in enumerate(nodo.pasos, start=1))
        return Resultado(
            mensajes=[
                texto_plano(f"{nodo.intro}\n\n{listado}"),
                con_opciones(_PREGUNTA_RESUELTO, _OPCIONES_RESUELTO),
            ],
            paso=nodo_id,
        )

    @staticmethod
    def _mensaje_pregunta(nodo: Pregunta) -> MensajeBot:
        return con_opciones(nodo.texto, [(r.id, r.etiqueta) for r in nodo.ramas])

    @staticmethod
    def _elegir_rama(nodo: Pregunta, entrada: Entrada) -> Rama | None:
        """Resuelve la rama por opcionId o por texto igual a la etiqueta."""
        if entrada.opcion_id:
            for rama in nodo.ramas:
                if rama.id == entrada.opcion_id:
                    return rama
            return None
        if entrada.texto:
            texto = validaciones.normalizar(entrada.texto)
            for rama in nodo.ramas:
                if validaciones.normalizar(rama.etiqueta) == texto:
                    return rama
        return None

    @staticmethod
    def _si_o_no(entrada: Entrada) -> bool | None:
        """Interpreta la respuesta a «¿Se resolvió?» (botón o texto)."""
        if entrada.opcion_id == "resuelto_si":
            return True
        if entrada.opcion_id == "resuelto_no":
            return False
        texto = validaciones.normalizar(entrada.texto or "")
        if texto in ("si", "si, se resolvio", "ya se resolvio", "resuelto"):
            return True
        if texto in ("no", "no, el problema continua", "sigue igual", "no se resolvio"):
            return False
        return None

    @staticmethod
    def _descripcion(arbol: Arbol, datos: dict[str, Any]) -> str:
        """Descripción compuesta para F-02 con la ruta del árbol y respuestas."""
        partes = [f"Diagnóstico guiado de {arbol.titulo} sin solución."]
        sintoma = (datos.get("sintoma") or "").strip()
        if sintoma:
            partes.append(f"Mensaje original del usuario: «{sintoma}».")
        respuestas = [str(r) for r in datos.get("respuestas") or []]
        if respuestas:
            partes.append(f"Respuestas del diagnóstico: {'; '.join(respuestas)}.")
        pasos = [str(p) for p in datos.get("pasos_probados") or []]
        if pasos:
            partes.append(f"Pasos sugeridos sin resultado: {'; '.join(pasos)}.")
        descripcion = " ".join(partes)
        return descripcion[: validaciones.DESCRIPCION_MAX]
