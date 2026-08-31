# Manuales operativos — Chatbot CTIC-FIIS UNAC

Documentación operativa del proyecto. Cada manual está dirigido a un público
distinto:

| Manual | Contenido | Dirigido a |
|---|---|---|
| [01-despliegue.md](01-despliegue.md) | Requisitos del servidor, instalación paso a paso, configuración del `.env`, carga de la base de conocimiento, TLS en producción, backups, monitoreo, actualización/rollback y solución de problemas. | **DevOps / TI** que instala y opera el sistema. |
| [02-manual-del-panel.md](02-manual-del-panel.md) | Cómo usar el panel: ingreso y roles, gestión de incidencias (estados y transiciones), atención de handoffs (chat en vivo), administración de la base de conocimiento y dashboard de métricas. | **Personal del CTIC** (técnicos y administradores), lenguaje no técnico. |
| [03-integracion-sistema-real.md](03-integracion-sistema-real.md) | Arquitectura de integración (ADR-03), contrato REST exacto que debe implementar el sistema de tickets real (API-01, 01b, 02, 03, 06 y métricas), dos caminos de integración, el "switch" de configuración y checklist de verificación con `curl`. | **Equipo de desarrollo de la universidad** (PHP/MySQL). |
| [04-integracion-wordpress-fiis.md](04-integracion-wordpress-fiis.md) | Integración del botón flotante en el sitio WordPress de la FIIS: script, CORS, URLs, API, dependencias, local/producción y actualización de la KB. | **Webmaster FIIS / DevOps / CTIC**. |

Para el contexto de producto y diseño técnico, ver la carpeta [`prd/`](../prd/)
(documentos 00 a 08).
</content>
