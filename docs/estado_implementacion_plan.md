# Estado del plan integral

Actualizado: 9 de octubre de 2026.

| Fase | Estado verificable | Siguiente condición |
|---|---|---|
| 0. Consolidación | Completa. Importador y diseño institucional están en commits locales separados. | Mantener commits temáticos; no se realizó `push`. |
| 1. Doble validación | Implementación completa. Paquete ciego de 31 casos generado bajo `results/`. | El segundo revisor debe devolver el Excel contestado; después se adjudican sólo los desacuerdos. |
| 2. Banco pareado | Generador y pruebas completos. El material actual permite como máximo 24 pares/48 casos; siete referencias no forman un par utilizable. | Ejecutar el generador tras segunda revisión y adjudicación. |
| 3. IA interna | Cuatro compuertas y candidatos implementados, sin ejecutar ni descargar modelos. | Requiere banco pareado final y servidor interno con los modelos 9B/12B instalados. El equipo actual no tiene GPU detectada. |
| 4. Web segura | Implementada localmente: identidad, propiedad, recuperación, decisiones, cabeceras y telemetría. | Desplegar detrás de IIS/WIA en QA y ejecutar pruebas con dos identidades reales. |
| 5. Piloto | Runbook y criterios preparados. | IIS/HTTPS disponible; 5–10 usuarios durante dos semanas. |
| 6. Compuerta TI | Verificador y plantilla implementados. La plantilla sin respuestas informa 17 bloqueos. | Obtener aprobaciones y completar la plantilla con evidencia institucional. |
| 7. SQL Server | No iniciado deliberadamente. | Sólo comienza cuando el verificador de compuerta termina sin bloqueos. |
| 8. Producción | Runbook de promoción, monitoreo y reversión preparado. | Depende de SQL, UAT, respaldo/restauración y semana controlada. |
| 9. ML supervisado | Contrato seguro y umbrales de preparación ya disponibles. | Reunir 300 decisiones, 30 documentos y al menos 50 ejemplos por clase. |

La línea base posterior a esta implementación es de **228 pruebas aprobadas**. Los archivos reales, libros de validación y bancos con texto institucional continúan excluidos de Git.
