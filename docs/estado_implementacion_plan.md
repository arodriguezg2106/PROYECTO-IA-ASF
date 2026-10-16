# Estado del plan integral

Actualizado: 16 de octubre de 2026.

| Fase | Estado verificable | Siguiente condición |
|---|---|---|
| 0. Consolidación | Completa. Importador y diseño institucional están en commits locales separados. | Mantener commits temáticos; no se realizó `push`. |
| 1. Doble validación | La segunda revisión de 31 casos fue importada: 6 quedaron terminales y 26 requieren adjudicación. El libro `results/editorial_adjudication/adjudicacion.xlsx` existe, pero sus 26 decisiones y justificaciones siguen vacías. | Completar las 26 filas del libro de adjudicación e importarlo; no se inferirán decisiones faltantes. |
| 2. Banco pareado | Generador y pruebas completos. El banco real no puede cerrarse hasta importar la adjudicación. El banco sintético específico de LanguageTool ya contiene 30 pares/60 casos versionables. | Importar la adjudicación y generar el banco real; confirmar que existan al menos 10 pares reales de ortografía o gramática antes del piloto. |
| 3. Lingüística e IA | Ollama quedó fuera del MVP. LanguageTool 6.6 se evaluó localmente con 80 casos y dos repeticiones: precisión 1.0, pero exhaustividad 0.4737 en la compuerta. El perfil quedó `rejected` y la web lo mantiene apagado. | Repetir la compuerta con el banco real adjudicado. No reducir el umbral de exhaustividad de 0.75. |
| 4. Web segura | Implementada localmente: identidad, propiedad, recuperación, decisiones, cabeceras y telemetría. La revisión editorial determinística puede activarse por separado; LanguageTool exige perfil aprobado, loopback y concurrencia 1. | Demostrar primero el flujo determinístico/editorial. LanguageTool sólo podrá habilitarse si una evaluación posterior aprueba el perfil. |
| 5. Piloto | Runbook y criterios preparados. | IIS/HTTPS disponible; 5–10 usuarios durante dos semanas. |
| 6. Compuerta TI | Verificador y plantilla implementados. La plantilla sin respuestas informa 17 bloqueos. | Obtener aprobaciones y completar la plantilla con evidencia institucional. |
| 7. SQL Server | No iniciado deliberadamente. | Sólo comienza cuando el verificador de compuerta termina sin bloqueos. |
| 8. Producción | Runbook de promoción, monitoreo y reversión preparado. | Depende de SQL, UAT, respaldo/restauración y semana controlada. |
| 9. ML supervisado | Contrato seguro y umbrales de preparación ya disponibles. | Reunir 300 decisiones, 30 documentos y al menos 50 ejemplos por clase. |

La línea base posterior a esta implementación es de **248 pruebas aprobadas**. Los archivos reales, libros de validación, reportes de evaluación y bancos con texto institucional continúan excluidos de Git; sólo se versionan casos sintéticos, hashes y métricas agregadas.
