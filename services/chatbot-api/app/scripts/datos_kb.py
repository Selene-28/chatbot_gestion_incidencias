"""Base de conocimiento inicial del CTIC FIIS-UNAC (tarea 4.5, prd/03 §5).

CONTENIDO PROVISIONAL — validar con el CTIC antes del post-test.
Los procedimientos, horarios, anexos y URLs son plausibles pero deben ser
revisados y firmados por el personal del CTIC (gate de la tarea 4.5).

Cada artículo: titulo (clave de upsert), contenido (markdown, 150-350 palabras,
pasos numerados), categoria (catálogo de prd/03) y etiquetas (para el re-ranking
léxico del RAG y el matching de la capa 1 del router).
"""

ARTICULOS: list[dict[str, str]] = [
    {
        "titulo": "Recuperación de contraseña del correo institucional",
        "categoria": "Correo Institucional",
        "etiquetas": "correo,contraseña,password,recuperar,restablecer,outlook,acceso,olvide",
        "contenido": (
            "Si olvidó la contraseña de su correo `@unac.edu.pe`, siga estos pasos:\n\n"
            "1. Ingrese al portal institucional: <https://correo.unac.edu.pe>.\n"
            "2. Haga clic en **¿Olvidó su contraseña?**.\n"
            "3. Escriba su correo institucional completo y valide el captcha.\n"
            "4. Recibirá un enlace de restablecimiento en su correo personal alterno "
            "registrado en la Oficina de Registros Académicos.\n"
            "5. Cree una contraseña nueva de al menos 8 caracteres que combine "
            "mayúsculas, minúsculas y números; evite reutilizar contraseñas antiguas.\n"
            "6. Espere unos 5 minutos y pruebe iniciar sesión en el correo web y en el "
            "Aula Virtual (la nueva contraseña se sincroniza en ambos servicios).\n\n"
            "Recomendaciones:\n\n"
            "- El enlace de restablecimiento caduca a las 24 horas; si expiró, repita "
            "el procedimiento.\n"
            "- Revise la carpeta de spam de su correo alterno si el mensaje no llega "
            "en 10 minutos.\n\n"
            "Si no tiene correo alterno registrado o el enlace nunca llega, acérquese "
            "al CTIC con su DNI o carné universitario para validar su identidad, o "
            "registre una incidencia desde este mismo chat indicando su código de "
            "estudiante o de trabajador."
        ),
    },
    {
        "titulo": "Configurar el correo institucional en el celular",
        "categoria": "Correo Institucional",
        "etiquetas": "correo,celular,móvil,android,iphone,ios,outlook,gmail,configurar",
        "contenido": (
            "Puede leer su correo `@unac.edu.pe` desde el celular con la aplicación "
            "**Outlook** (recomendada) o con la app de correo nativa.\n\n"
            "En Android o iPhone con Outlook:\n\n"
            "1. Instale **Microsoft Outlook** desde Play Store o App Store.\n"
            "2. Abra la app y toque **Agregar cuenta**.\n"
            "3. Escriba su correo institucional completo (ej. `jperez@unac.edu.pe`).\n"
            "4. Ingrese la contraseña de su correo institucional.\n"
            "5. Acepte los permisos solicitados; la bandeja se sincroniza en unos "
            "minutos.\n\n"
            "En la app de correo nativa (opción avanzada):\n\n"
            "1. Agregue una cuenta de tipo **Exchange / Office 365**.\n"
            "2. Use como servidor `outlook.office365.com` y como usuario su correo "
            "completo.\n\n"
            "Problemas frecuentes:\n\n"
            "- *Contraseña rechazada:* verifique que puede entrar desde "
            "<https://correo.unac.edu.pe>; si no, primero recupere su contraseña.\n"
            "- *La cuenta ya está configurada pero dejó de sincronizar:* elimine la "
            "cuenta del teléfono y vuelva a agregarla.\n\n"
            "Si tras estos pasos el correo no sincroniza, registre una incidencia "
            "indicando el modelo del teléfono y la app utilizada."
        ),
    },
    {
        "titulo": "Acceso al Sistema de Gestión Académica (SGA)",
        "categoria": "Cuentas y Accesos",
        "etiquetas": "sga,sistema,gestión académica,matrícula,notas,acceso,usuario,intranet",
        "contenido": (
            "El SGA (<https://sga.unac.edu.pe>) es el sistema donde estudiantes y "
            "docentes consultan matrícula, horarios, notas y trámites académicos.\n\n"
            "Para ingresar:\n\n"
            "1. Abra <https://sga.unac.edu.pe> en un navegador actualizado (Chrome, "
            "Edge o Firefox).\n"
            "2. Escriba como usuario su **código de estudiante** (o código de docente).\n"
            "3. Ingrese la contraseña del SGA. Para ingresantes, la contraseña inicial "
            "es su número de DNI; el sistema le pedirá cambiarla en el primer acceso.\n"
            "4. Seleccione el período académico vigente en la parte superior.\n\n"
            "Problemas frecuentes:\n\n"
            "- *Usuario o contraseña incorrectos:* use la opción **Recuperar "
            "contraseña** del propio SGA; el enlace llega a su correo institucional.\n"
            "- *Cuenta bloqueada por intentos fallidos:* espere 30 minutos e intente "
            "nuevamente.\n"
            "- *No aparece el período actual o la matrícula:* la habilitación depende "
            "de la Oficina de Registros Académicos, no del CTIC; consulte primero con "
            "su facultad.\n\n"
            "Si el SGA muestra errores del sistema (pantalla en blanco, error 500) o "
            "no puede recuperar su contraseña, registre una incidencia con captura de "
            "pantalla y su código de estudiante."
        ),
    },
    {
        "titulo": "Aula Virtual: no puedo iniciar sesión (caché y credenciales)",
        "categoria": "Aula Virtual",
        "etiquetas": "aula virtual,moodle,login,sesión,caché,credenciales,acceso,error",
        "contenido": (
            "Si el Aula Virtual (<https://aulavirtual.unac.edu.pe>) rechaza su usuario "
            "o se queda cargando, siga estos pasos en orden:\n\n"
            "1. Verifique sus credenciales: el usuario es su **correo institucional "
            "completo** y la contraseña es la misma del correo. Pruebe primero entrar "
            "al correo web; si tampoco puede, recupere su contraseña de correo.\n"
            "2. Borre la caché y las cookies del navegador (en Chrome: Configuración → "
            "Privacidad y seguridad → Borrar datos de navegación → marque *Cookies* e "
            "*Imágenes y archivos en caché*).\n"
            "3. Cierre el navegador por completo y vuelva a intentar.\n"
            "4. Pruebe en una **ventana de incógnito** o en otro navegador: si así "
            "funciona, el problema era la caché local.\n"
            "5. Si usa la app móvil de Moodle, cierre sesión, borre los datos de la "
            "app y vuelva a configurarla con la URL del aula virtual.\n\n"
            "Errores típicos:\n\n"
            "- *«Sesión caducada»* repetido: casi siempre se resuelve con el paso 2.\n"
            "- *«Usuario o contraseña no válidos»*: la cuenta se sincroniza con el "
            "correo; espere 10 minutos después de cambiar la contraseña.\n\n"
            "Si tras estos pasos no puede ingresar, registre una incidencia indicando "
            "el mensaje de error exacto y el navegador utilizado."
        ),
    },
    {
        "titulo": "Aula Virtual: no aparecen mis cursos",
        "categoria": "Aula Virtual",
        "etiquetas": "aula virtual,moodle,cursos,no aparecen,matrícula,docente,secciones",
        "contenido": (
            "Si ya puede ingresar al Aula Virtual pero uno o más cursos no figuran en "
            "su panel, considere lo siguiente:\n\n"
            "1. Revise la sección **Mis cursos** y el filtro de período: seleccione el "
            "semestre en curso (por defecto puede mostrar un período anterior).\n"
            "2. Verifique su matrícula en el SGA: los cursos se cargan al Aula Virtual "
            "a partir de la matrícula oficial, con una sincronización que puede tardar "
            "hasta **48 horas** después de matricularse o rectificar.\n"
            "3. Si se matriculó hace más de 48 horas y el curso sigue sin aparecer, "
            "confirme con su docente que la sección ya fue **activada**: los docentes "
            "deciden cuándo hacer visible cada curso.\n"
            "4. Para docentes: si le falta un curso asignado, verifique primero su "
            "carga lectiva en el SGA; el CTIC solo replica lo que Registros Académicos "
            "reporta.\n\n"
            "Importante: el CTIC no matricula ni retira estudiantes de los cursos; "
            "eso corresponde a la Oficina de Registros Académicos de su facultad.\n\n"
            "Si su matrícula es correcta, pasaron más de 48 horas y el docente indica "
            "que el curso está visible, registre una incidencia con su código de "
            "estudiante, el nombre del curso y la sección."
        ),
    },
    {
        "titulo": "Conexión a la red WiFi de la UNAC",
        "categoria": "Internet/WiFi",
        "etiquetas": "wifi,internet,red,conexión,inalámbrica,portal cautivo,campus,sede",
        "contenido": (
            "Para conectarse a la red inalámbrica del campus:\n\n"
            "1. Active el WiFi de su dispositivo y seleccione la red **UNAC-CAMPUS** "
            "(en la sede Cañete y en los laboratorios FIIS puede figurar como "
            "**UNAC-FIIS**).\n"
            "2. Ingrese como usuario su **correo institucional** completo "
            "(ej. `jperez@unac.edu.pe`).\n"
            "3. Ingrese la **misma contraseña** de su correo institucional.\n"
            "4. Si el navegador muestra un **portal cautivo**, inicie sesión ahí y "
            "acepte los términos de uso; hágalo desde el navegador, no desde la "
            "ventana emergente, si esta no carga.\n\n"
            "Problemas frecuentes:\n\n"
            "- *Credenciales rechazadas:* verifique que su contraseña de correo esté "
            "vigente; si la olvidó, consulte el artículo de recuperación de "
            "contraseña.\n"
            "- *Conecta pero sin internet:* olvide la red desde la configuración del "
            "dispositivo, reconéctese y vuelva a pasar por el portal cautivo.\n"
            "- *El portal cautivo no aparece:* abra manualmente una página http como "
            "`http://portal.unac.edu.pe` para forzarlo.\n"
            "- *Cobertura débil:* la señal es más estable en pabellones, biblioteca y "
            "cafetería central.\n\n"
            "Si el problema persiste, registre una incidencia indicando la sede, el "
            "pabellón y el tipo de dispositivo."
        ),
    },
    {
        "titulo": "Solicitud de cuenta y correo institucional para ingresantes",
        "categoria": "Cuentas y Accesos",
        "etiquetas": "cuenta,correo,institucional,ingresante,nuevo,solicitud,creación,docente",
        "contenido": (
            "Las cuentas institucionales `@unac.edu.pe` se crean de oficio para "
            "estudiantes ingresantes y personal nuevo; no es necesario pagar ni "
            "presentar solicitudes en físico.\n\n"
            "Para estudiantes ingresantes:\n\n"
            "1. Tras la matrícula, la cuenta se genera automáticamente en un plazo de "
            "hasta **10 días hábiles**.\n"
            "2. Las credenciales iniciales se envían al correo personal que registró "
            "en su postulación (revise también el spam).\n"
            "3. En el primer acceso el sistema le exigirá cambiar la contraseña.\n\n"
            "Para docentes y personal administrativo:\n\n"
            "1. La Oficina de Recursos Humanos comunica el alta al CTIC.\n"
            "2. El CTIC crea la cuenta y notifica las credenciales al correo personal "
            "declarado en RRHH.\n\n"
            "Casos especiales:\n\n"
            "- Si pasaron los 10 días hábiles y no recibió sus credenciales, registre "
            "una incidencia con su código de estudiante y DNI.\n"
            "- Si su nombre figura con errores en el correo, solicite la corrección "
            "por incidencia adjuntando su DNI.\n"
            "- Las cuentas de egresados se mantienen activas 1 año después de "
            "concluir los estudios.\n\n"
            "El CTIC nunca solicita su contraseña por correo o teléfono; ante "
            "mensajes sospechosos, no responda y repórtelos."
        ),
    },
    {
        "titulo": "Office 365 educativo gratuito para la comunidad UNAC",
        "categoria": "Software Institucional",
        "etiquetas": "office,office 365,word,excel,powerpoint,teams,onedrive,licencia,microsoft",
        "contenido": (
            "Por convenio con Microsoft, estudiantes, docentes y administrativos con "
            "cuenta `@unac.edu.pe` activa tienen acceso a **Office 365 educativo** sin "
            "costo, que incluye Word, Excel, PowerPoint, Teams y 1 TB en OneDrive.\n\n"
            "Para usar la versión web:\n\n"
            "1. Ingrese a <https://www.office.com>.\n"
            "2. Inicie sesión con su correo institucional y su contraseña.\n"
            "3. Use las aplicaciones directamente en el navegador; sus archivos se "
            "guardan en OneDrive.\n\n"
            "Para instalar Office en su computadora personal:\n\n"
            "1. En <https://www.office.com>, haga clic en **Instalar aplicaciones**.\n"
            "2. Descargue el instalador y ejecútelo (requiere Windows 10/11 o macOS "
            "reciente).\n"
            "3. Al abrir cualquier aplicación, inicie sesión con su cuenta "
            "institucional para activar la licencia.\n"
            "4. La licencia permite hasta **5 dispositivos** por usuario.\n\n"
            "Problemas frecuentes:\n\n"
            "- *«Cuenta no válida»:* su cuenta institucional puede estar inactiva; "
            "verifique que puede entrar al correo web.\n"
            "- *Office pide comprar licencia:* cierre sesión de cuentas personales de "
            "Microsoft y vuelva a entrar solo con la institucional.\n\n"
            "Para errores de activación persistentes, registre una incidencia con "
            "captura del mensaje."
        ),
    },
    {
        "titulo": "Acceso a Turnitin para docentes y tesistas",
        "categoria": "Software Institucional",
        "etiquetas": "turnitin,similitud,plagio,tesis,docente,tesista,informe,acceso",
        "contenido": (
            "La UNAC cuenta con licencia institucional de **Turnitin** para la "
            "revisión de similitud de tesis y trabajos de investigación.\n\n"
            "Para docentes (instructores):\n\n"
            "1. Solicite su acceso enviando un correo a `ctic.fiis@unac.edu.pe` desde "
            "su cuenta institucional, indicando facultad y unidad de posgrado si "
            "corresponde.\n"
            "2. Recibirá una invitación de Turnitin en su correo institucional; "
            "actívela dentro de los 7 días.\n"
            "3. Ingrese en <https://www.turnitin.com> y cree sus clases y ejercicios.\n\n"
            "Para estudiantes y tesistas:\n\n"
            "1. El acceso lo entrega su **asesor o la unidad de investigación** de la "
            "facultad mediante el ID de clase y la clave de inscripción.\n"
            "2. Regístrese con su correo institucional y suba su documento en el "
            "ejercicio indicado.\n"
            "3. El reporte de similitud queda disponible para su asesor; la emisión "
            "de constancias corresponde a la unidad de investigación, no al CTIC.\n\n"
            "Problemas frecuentes:\n\n"
            "- *La invitación expiró:* solicite el reenvío por incidencia.\n"
            "- *No recuerda su contraseña de Turnitin:* use «¿Olvidaste tu "
            "contraseña?» en el sitio de Turnitin con su correo institucional.\n\n"
            "Para cupos agotados o errores de la plataforma, registre una incidencia."
        ),
    },
    {
        "titulo": "MATLAB con licencia campus de la UNAC",
        "categoria": "Software Institucional",
        "etiquetas": "matlab,simulink,licencia,campus,mathworks,instalación,software",
        "contenido": (
            "La universidad dispone de licencia **Campus-Wide de MATLAB** que permite "
            "a estudiantes y docentes instalar MATLAB y Simulink en equipos "
            "personales.\n\n"
            "Pasos de instalación:\n\n"
            "1. Cree una cuenta de MathWorks en <https://www.mathworks.com> usando su "
            "correo institucional `@unac.edu.pe` (esto vincula la licencia campus).\n"
            "2. Verifique su correo con el enlace que envía MathWorks.\n"
            "3. En su cuenta, elija **Instalar MATLAB**, descargue el instalador para "
            "su sistema operativo y ejecútelo.\n"
            "4. Inicie sesión durante la instalación y seleccione la licencia "
            "**Academic - Total Headcount**.\n"
            "5. Marque los toolboxes que necesite (puede agregar más luego).\n\n"
            "Notas:\n\n"
            "- También puede usar **MATLAB Online** en el navegador, sin instalar "
            "nada, desde la misma cuenta.\n"
            "- La licencia se revalida automáticamente mientras su cuenta "
            "institucional esté activa; conéctese a internet al menos una vez al mes "
            "con MATLAB abierto.\n\n"
            "Problemas frecuentes:\n\n"
            "- *MathWorks no acepta el correo:* su cuenta institucional debe estar "
            "activa; pruebe primero el correo web.\n"
            "- *«Licencia no encontrada»:* cierre sesión en MATLAB y vuelva a "
            "iniciarla.\n\n"
            "Si la licencia campus no aparece asociada a su cuenta, registre una "
            "incidencia con su correo institucional."
        ),
    },
    {
        "titulo": "Laboratorios de cómputo e impresoras de la FIIS",
        "categoria": "Equipos de Cómputo",
        "etiquetas": "laboratorio,cómputo,impresora,imprimir,equipos,reserva,pc,horario",
        "contenido": (
            "La FIIS cuenta con laboratorios de cómputo administrados por el CTIC en "
            "el pabellón de la facultad (LAB-01 a LAB-04, 2.º y 3.er piso).\n\n"
            "Uso de los laboratorios:\n\n"
            "1. El acceso libre para estudiantes es en los horarios sin clase "
            "programada, publicados en la puerta de cada laboratorio y en la vitrina "
            "del CTIC.\n"
            "2. Inicie sesión en los equipos con su **correo institucional** y su "
            "contraseña.\n"
            "3. Guarde sus archivos en OneDrive o en una memoria USB: los equipos se "
            "restauran al reiniciarse y **no conservan archivos locales**.\n"
            "4. Los docentes reservan laboratorios para clases o evaluaciones "
            "enviando un correo a `ctic.fiis@unac.edu.pe` con al menos 48 horas de "
            "anticipación.\n\n"
            "Impresiones:\n\n"
            "1. El servicio de impresión para trabajos académicos está disponible en "
            "el LAB-02.\n"
            "2. Envíe el documento a la cola **IMPRESION-FIIS** desde cualquier PC "
            "del laboratorio y acérquese al encargado con su carné.\n"
            "3. Hay una cuota mensual por estudiante; el encargado puede informarle "
            "su saldo.\n\n"
            "Reporte equipos malogrados, software faltante o problemas de impresión "
            "registrando una incidencia con el número de laboratorio y de equipo "
            "(etiqueta del CPU)."
        ),
    },
    {
        "titulo": "Videoconferencias institucionales (Google Meet y Zoom)",
        "categoria": "Software Institucional",
        "etiquetas": "videoconferencia,meet,zoom,clase virtual,reunión,grabación,enlace",
        "contenido": (
            "Para clases y reuniones virtuales, la comunidad UNAC dispone de **Google "
            "Meet** (con la cuenta institucional) y de licencias **Zoom** "
            "administradas por el CTIC para actividades académicas oficiales.\n\n"
            "Google Meet (recomendado para clases regulares):\n\n"
            "1. Ingrese a <https://meet.google.com> con su correo institucional.\n"
            "2. Cree la reunión o únase con el enlace compartido por el docente.\n"
            "3. Con la cuenta institucional las reuniones no tienen límite de 60 "
            "minutos y permiten hasta 100 participantes.\n\n"
            "Zoom institucional (sustentaciones, eventos, grabaciones):\n\n"
            "1. Solicite la sesión por correo a `ctic.fiis@unac.edu.pe` con al menos "
            "48 horas de anticipación, indicando fecha, hora, duración y si requiere "
            "grabación.\n"
            "2. El CTIC le enviará el enlace de anfitrión y los datos de acceso.\n"
            "3. Las grabaciones se entregan por OneDrive/Drive en un plazo de 24 "
            "horas después del evento.\n\n"
            "Problemas frecuentes:\n\n"
            "- *«No tienes permiso para unirte»:* entre con la cuenta institucional, "
            "no con una cuenta personal de Gmail.\n"
            "- *Sin audio o cámara:* revise los permisos del navegador (candado en la "
            "barra de direcciones).\n\n"
            "Para fallas durante un evento en curso, llame al anexo 2214 o registre "
            "una incidencia."
        ),
    },
    {
        "titulo": "Horario de atención y contacto del CTIC",
        "categoria": "Información CTIC",
        "etiquetas": (
            "fiis,facultad,ingeniería industrial,ingeniería de sistemas,misión,"
            "visión,unac,biblioteca,laboratorios,investigación,egresado,valores"
        ),
        "contenido": (
            "La Facultad de Ingeniería Industrial y de Sistemas de la Universidad "
            "Nacional del Callao (FIIS) es una de las facultades de ingeniería de la "
            "Universidad Nacional del Callao, ubicada en el campus universitario de "
            "Bellavista, Callao.\n\n"
            "Desde su creación ha orientado su labor académica hacia la formación de "
            "profesionales capaces de diseñar, optimizar e innovar procesos "
            "organizacionales y tecnológicos que contribuyan al desarrollo del país. "
            "La facultad busca combinar conocimientos científicos, tecnológicos y "
            "humanísticos con una sólida formación ética y profesional.\n\n"
            "**Finalidad de la facultad**\n\n"
            "La finalidad de la FIIS es formar ingenieros con una preparación "
            "integral que les permita resolver problemas reales de las "
            "organizaciones mediante la aplicación de la ingeniería, la "
            "investigación, la innovación tecnológica y la mejora continua. Además, "
            "promueve la responsabilidad social, el emprendimiento, el pensamiento "
            "crítico y el compromiso con el desarrollo sostenible. Su enfoque no "
            "solo está orientado a la enseñanza, sino también a la generación de "
            "conocimiento y la vinculación con el sector productivo.\n\n"
            "**Misión**\n\n"
            "La misión de la facultad consiste en formar ingenieros industriales e "
            "ingenieros de sistemas con sólidos conocimientos científicos, "
            "tecnológicos y empresariales, fomentando la innovación, la "
            "investigación y el desarrollo profesional bajo principios éticos, "
            "humanísticos y de responsabilidad social, contribuyendo al desarrollo "
            "sostenible del país.\n\n"
            "**Visión**\n\n"
            "La FIIS tiene como visión consolidarse como una facultad líder y "
            "acreditada, reconocida a nivel nacional e internacional por la calidad "
            "de sus programas académicos, la investigación científica, la "
            "innovación tecnológica y la formación de profesionales altamente "
            "competitivos que respondan a los cambios científicos y tecnológicos de "
            "la sociedad.\n\n"
            "**¿Qué ofrece la FIIS a sus estudiantes?**\n\n"
            "La facultad pone a disposición de los alumnos diversos recursos "
            "académicos y de apoyo para fortalecer su formación.\n\n"
            "*Biblioteca especializada:* cuenta con un centro de información que "
            "dispone de tesis, informes de investigación, material bibliográfico y "
            "espacios adecuados para el estudio individual y grupal. Este servicio "
            "facilita el acceso a información científica y técnica necesaria "
            "durante toda la carrera.\n\n"
            "*Laboratorios de computación:* dispone de laboratorios equipados con "
            "computadoras conectadas en red y acceso a software especializado e "
            "Internet, permitiendo el desarrollo de prácticas académicas, "
            "programación, simulación y proyectos de ingeniería.\n\n"
            "*Laboratorio de química:* los estudiantes cuentan con un laboratorio "
            "equipado con instrumentos modernos para la realización de prácticas "
            "experimentales y actividades de investigación relacionadas con las "
            "ciencias básicas de ingeniería.\n\n"
            "*Auditorio y salas audiovisuales:* la facultad posee ambientes "
            "equipados con proyectores multimedia y equipos audiovisuales "
            "utilizados para conferencias, sustentaciones, seminarios, talleres, "
            "congresos y actividades académicas.\n\n"
            "*Instituto de Investigación:* promueve la investigación científica "
            "mediante el desarrollo de proyectos en los que participan docentes y "
            "estudiantes, incentivando la producción científica, la innovación "
            "tecnológica y la solución de problemas del entorno.\n\n"
            "**Formación académica**\n\n"
            "Durante la carrera, el estudiante desarrolla competencias en: gestión "
            "y optimización de procesos, desarrollo e implementación de sistemas de "
            "información, investigación científica, gestión de proyectos, "
            "innovación tecnológica, transformación digital, análisis y solución de "
            "problemas, liderazgo y trabajo en equipo, emprendimiento, y ética "
            "profesional. Estas competencias permiten que el egresado pueda "
            "adaptarse a diversos sectores económicos y tecnológicos.\n\n"
            "**Investigación e innovación**\n\n"
            "La investigación constituye uno de los pilares de la FIIS. Los "
            "estudiantes pueden participar en proyectos de investigación junto con "
            "docentes investigadores, elaborar artículos científicos, desarrollar "
            "soluciones tecnológicas y presentar sus trabajos en eventos "
            "académicos. La facultad incentiva la innovación como parte de la "
            "formación profesional y busca que sus estudiantes contribuyan con "
            "soluciones a problemas reales de la industria y la sociedad.\n\n"
            "**Oportunidades para los estudiantes**\n\n"
            "Durante su formación, un estudiante puede acceder a: prácticas "
            "preprofesionales, actividades de investigación, seminarios y "
            "conferencias, visitas técnicas a empresas, programas de proyección "
            "social, desarrollo de proyectos tecnológicos, participación en "
            "eventos académicos y científicos, y trabajo colaborativo con docentes "
            "e investigadores.\n\n"
            "**Perfil del egresado**\n\n"
            "El egresado de la FIIS está preparado para: diseñar soluciones "
            "tecnológicas y organizacionales, gestionar procesos industriales y "
            "empresariales, implementar sistemas de información, liderar proyectos "
            "de innovación, optimizar recursos mediante herramientas de ingeniería, "
            "resolver problemas complejos utilizando metodologías científicas, y "
            "actuar con responsabilidad ética, profesional y compromiso social.\n\n"
            "**Valores institucionales**\n\n"
            "La formación del estudiante está sustentada en valores como: calidad, "
            "compromiso, responsabilidad, ética, profesionalismo, disciplina, "
            "respeto y cooperación.\n\n"
            "Nos alegra acompañarte en tu trayectoria académica. Este espacio ha "
            "sido creado para brindarte información, orientación y apoyo durante "
            "cada etapa de tu formación universitaria, facilitando tu acceso a los "
            "servicios y recursos que la facultad pone a tu disposición.\n\n"
            "Cada semestre representa una nueva oportunidad para aprender, crecer y "
            "acercarte a tus metas profesionales. A lo largo de este camino "
            "encontrarás nuevos conocimientos, desafíos académicos, proyectos, "
            "trabajos en equipo y experiencias que fortalecerán tu carácter, tus "
            "habilidades y tu vocación profesional. Habrá momentos de satisfacción "
            "por cada objetivo alcanzado y también retos que pondrán a prueba tu "
            "perseverancia. Recuerda que cada dificultad es una oportunidad para "
            "aprender, mejorar y demostrar de lo que eres capaz.\n\n"
            "La Facultad de Ingeniería Industrial y de Sistemas pone a tu "
            "disposición docentes, laboratorios, biblioteca, actividades de "
            "investigación y diversos recursos que contribuirán a tu desarrollo "
            "académico y profesional. Aprovecha cada oportunidad para aprender, "
            "participar en proyectos, investigar, desarrollar nuevas ideas y "
            "construir una red de compañeros y docentes que enriquecerán tu "
            "experiencia universitaria.\n\n"
            "Nunca dejes de sentir curiosidad por aprender, de hacer preguntas y de "
            "buscar soluciones creativas a los problemas. La ingeniería evoluciona "
            "constantemente y quienes mantienen una actitud de aprendizaje continuo "
            "son quienes logran marcar la diferencia. Recuerda que el éxito no se "
            "mide únicamente por las calificaciones obtenidas, sino también por la "
            "disciplina, la constancia, la ética, la responsabilidad y el "
            "compromiso con los demás. Cada esfuerzo que realices hoy será la base "
            "del profesional que llegarás a ser mañana.\n\n"
            "Confía en tus capacidades, mantén siempre una actitud positiva y no "
            "tengas miedo de enfrentar nuevos retos. Disfruta cada semestre, "
            "celebra tus logros, aprende de los errores y nunca pierdas de vista el "
            "propósito que te impulsa a seguir creciendo.\n\n"
            "Cada paso que des dentro de la Facultad contribuirá a la construcción "
            "de tu futuro. Cree en ti, persevera y recuerda que los grandes "
            "ingenieros no solo resuelven problemas, sino que también crean "
            "oportunidades, transforman organizaciones y generan un impacto "
            "positivo en la sociedad.\n\n"
            "Te deseamos muchos éxitos en tu formación profesional. Que cada "
            "desafío te acerque a tus metas y que tu paso por la Facultad de "
            "Ingeniería Industrial y de Sistemas sea una experiencia llena de "
            "aprendizaje, crecimiento y logros. ¡El futuro se construye con "
            "dedicación, esfuerzo y pasión por aprender!"
        ),
    },
    {
        "titulo": "Cómo funcionan los tickets de soporte del CTIC",
        "categoria": "Otros",
        "etiquetas": "ticket,incidencia,soporte,estado,seguimiento,prioridad,sla,registrar",
        "contenido": (
            "Las solicitudes de soporte del CTIC se gestionan mediante **tickets de "
            "incidencia**, que puede crear y consultar desde este asistente virtual.\n\n"
            "Ciclo de un ticket:\n\n"
            "1. **Registro:** describe el problema (por chat o presencialmente) y "
            "recibe un código con formato `INC-AAAA-NNNN` (ej. `INC-2026-0123`). "
            "Guárdelo para el seguimiento.\n"
            "2. **Asignación:** el ticket se deriva a un técnico según categoría y "
            "prioridad (Baja, Media o Alta).\n"
            "3. **Atención:** el técnico puede contactarlo por correo institucional "
            "si necesita más datos; los tiempos referenciales de primera respuesta "
            "son 1 día hábil para prioridad Alta y hasta 3 días hábiles para Baja.\n"
            "4. **Resolución y cierre:** al resolverse recibirá la notificación y "
            "podrá calificar la atención.\n\n"
            "Recomendaciones para una atención rápida:\n\n"
            "- Incluya capturas de pantalla o el texto exacto del error.\n"
            "- Indique su código de estudiante o trabajador y un medio de contacto.\n"
            "- Un problema por ticket: no mezcle solicitudes distintas.\n\n"
            "Puede consultar el estado de su ticket en cualquier momento escribiendo "
            "el código `INC-AAAA-NNNN` en este chat, o escalarlo si considera que la "
            "atención demora más de lo indicado."
        ),
    },
    {
        "titulo": "VPN institucional para acceso remoto",
        "categoria": "Internet/WiFi",
        "etiquetas": "vpn,acceso remoto,red interna,biblioteca,bases de datos,forticlient",
        "contenido": (
            "La VPN institucional permite acceder desde fuera del campus a recursos "
            "internos: bases de datos suscritas de la biblioteca, sistemas "
            "administrativos y repositorios restringidos.\n\n"
            "¿Quiénes pueden usarla? Docentes, investigadores y personal "
            "administrativo con cuenta institucional activa; los estudiantes de "
            "posgrado pueden solicitarla con carta de su unidad.\n\n"
            "Pasos para solicitar y configurar la VPN:\n\n"
            "1. Registre una incidencia solicitando el servicio VPN, indicando su "
            "cargo/vínculo y el recurso que necesita alcanzar.\n"
            "2. El CTIC validará la solicitud y le enviará a su correo institucional "
            "el instalador de **FortiClient VPN** y su perfil de conexión.\n"
            "3. Instale FortiClient y cree una conexión nueva con los datos del "
            "perfil (servidor y puerto indicados en el correo).\n"
            "4. Conéctese con su correo institucional y contraseña.\n"
            "5. Verifique el acceso abriendo el recurso interno indicado.\n\n"
            "Recomendaciones y problemas frecuentes:\n\n"
            "- La sesión VPN se cierra automáticamente tras 8 horas de inactividad.\n"
            "- *«Credenciales inválidas»:* la contraseña es la misma del correo; si "
            "la cambió recientemente, espere 10 minutos.\n"
            "- *Conecta pero no carga el recurso:* desconecte y vuelva a conectar; si "
            "persiste, reporte la incidencia con la hora del intento."
        ),
    },
    {
        "titulo": "Cuenta bloqueada por intentos fallidos de inicio de sesión",
        "categoria": "Cuentas y Accesos",
        "etiquetas": "cuenta,bloqueada,bloqueo,intentos,fallidos,desbloquear,seguridad,phishing",
        "contenido": (
            "Por seguridad, las cuentas institucionales se **bloquean temporalmente** "
            "después de varios intentos fallidos de inicio de sesión (5 intentos en "
            "el correo y en el Aula Virtual).\n\n"
            "Qué hacer si su cuenta se bloqueó:\n\n"
            "1. Espere **30 minutos**: el bloqueo se libera de forma automática.\n"
            "2. Antes de reintentar, verifique que el bloqueo de mayúsculas esté "
            "desactivado y que no haya espacios al copiar y pegar la contraseña.\n"
            "3. Si no recuerda la contraseña con certeza, no siga probando: use la "
            "opción de recuperación de contraseña (vea el artículo correspondiente) "
            "para restablecerla.\n"
            "4. Tras recuperar el acceso, cierre las sesiones antiguas: en el correo "
            "web, vaya a su perfil → **Cerrar sesión en todas partes**; un teléfono "
            "con la contraseña antigua guardada puede volver a bloquear la cuenta.\n\n"
            "Si la cuenta se bloquea repetidamente sin que usted falle la contraseña, "
            "puede tratarse de intentos de acceso de terceros:\n\n"
            "1. Cambie su contraseña de inmediato.\n"
            "2. Registre una incidencia de seguridad indicando fechas y horas de los "
            "bloqueos.\n\n"
            "Recuerde: el CTIC nunca pide su contraseña por correo, teléfono ni "
            "mensajería; los correos que lo hacen son phishing y deben reportarse."
        ),
    },
    # ---- FAQ General (menú de botones "❓ Preguntas frecuentes") ----------
    {
        "titulo": "FAQ: ¿Cuál es el horario de atención?",
        "categoria": "FAQ General",
        "etiquetas": "horario,atencion,oficinas,faq",
        "contenido": (
            "El horario puede variar según cada oficina administrativa. Se "
            "recomienda revisar los comunicados oficiales publicados por la "
            "facultad o consultar directamente con la oficina correspondiente."
        ),
    },
    {
        "titulo": "FAQ: ¿Dónde puedo encontrar los comunicados oficiales?",
        "categoria": "FAQ General",
        "etiquetas": "comunicados,resoluciones,cronogramas,noticias,avisos,faq",
        "contenido": (
            "Los comunicados, resoluciones, cronogramas, noticias y avisos se "
            "publican en la página web oficial de la FIIS y en sus redes "
            "sociales institucionales."
        ),
    },
    {
        "titulo": "FAQ: ¿Cómo realizo mi matrícula?",
        "categoria": "FAQ General",
        "etiquetas": "matricula,sga,calendario academico,faq",
        "contenido": (
            "La matrícula se realiza durante las fechas establecidas en el "
            "calendario académico utilizando el Sistema de Gestión Académica "
            "(SGA)."
        ),
    },
    {
        "titulo": "FAQ: ¿Qué hago si no puedo matricularme?",
        "categoria": "FAQ General",
        "etiquetas": "matricula,problema,escuela profesional,registros academicos,faq",
        "contenido": (
            "Debes comunicarte con la Escuela Profesional o con la Oficina de "
            "Registros Académicos para verificar el motivo del inconveniente y "
            "recibir orientación."
        ),
    },
    {
        "titulo": "FAQ: ¿Cómo solicito una rectificación de matrícula?",
        "categoria": "FAQ General",
        "etiquetas": "rectificacion,matricula,cronograma academico,faq",
        "contenido": (
            "Debes presentar la solicitud dentro de las fechas establecidas en "
            "el cronograma académico."
        ),
    },
    {
        "titulo": "FAQ: ¿Cómo ingreso al SGA?",
        "categoria": "FAQ General",
        "etiquetas": "sga,ingreso,codigo de estudiante,contraseña,faq",
        "contenido": (
            "Debes acceder utilizando tu código de estudiante y la contraseña "
            "asignada por la universidad o también lo puedes cambiar."
        ),
    },
    {
        "titulo": "FAQ: Olvidé mi contraseña del SGA",
        "categoria": "FAQ General",
        "etiquetas": "sga,contraseña,recuperacion,otic,faq",
        "contenido": (
            "Debes comunicarte con la Oficina de Tecnologías de la Información "
            "(OTIC) o seguir el procedimiento de recuperación disponible en la "
            "plataforma, si está habilitado."
        ),
    },
    {
        "titulo": "FAQ: ¿Qué puedo hacer desde el SGA?",
        "categoria": "FAQ General",
        "etiquetas": "sga,funciones,matricula,notas,horarios,faq",
        "contenido": (
            "Entre las funciones principales se encuentran:\n\n"
            "1. Matrícula\n"
            "2. Consulta de notas\n"
            "3. Horarios\n"
            "4. Historial académico\n"
            "5. Avance curricular\n"
            "6. Información personal\n"
            "7. Consulta de docentes"
        ),
    },
    {
        "titulo": "FAQ: ¿Cómo solicito una constancia de estudios?",
        "categoria": "FAQ General",
        "etiquetas": "constancia,estudios,tramite,faq",
        "contenido": (
            "Debes realizar el trámite mediante la oficina correspondiente "
            "siguiendo el procedimiento establecido por la universidad."
        ),
    },
    {
        "titulo": "FAQ: ¿Dónde presento mi proyecto de tesis?",
        "categoria": "FAQ General",
        "etiquetas": "tesis,proyecto,investigacion,faq",
        "contenido": (
            "La presentación se realiza mediante la unidad correspondiente de "
            "investigación de la facultad."
        ),
    },
]
