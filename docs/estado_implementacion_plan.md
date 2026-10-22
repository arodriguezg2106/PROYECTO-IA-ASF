# Estado maestro del plan

Actualizado: 22 de octubre de 2026. Objetivo inmediato: demo reproducible el 2
de noviembre de 2026.

| Frente | Estado verificable | Próxima compuerta |
|---|---|---|
| Adjudicación | Las 26 decisiones finales fueron importadas; 6 son respuestas terminales justificadas. La evidencia fija no cambió y no se almacenaron nombres. | Conservar el Excel y el JSON real sólo en almacenamiento local protegido. |
| Banco editorial | Banco final de 16 pares/32 ejemplos; 15 exclusiones documentadas. Distribución: 8 coherencia, 5 ortografía, 1 cifras y 2 criterio técnico. | Usarlo como referencia local y mantener en Git únicamente el equivalente sintético y sus hashes. |
| LanguageTool | Repetido sobre 90 casos, incluidos 5 pares reales compatibles. La compuerta obtuvo precisión 1.0, exhaustividad 0.4419, cero falsos positivos, acuerdo 1.0 y 4 propuestas inseguras; permanece rechazado. | Mantenerlo apagado. Sólo reevaluar con más evidencia real o una mejora comprobable, sin reducir umbrales. |
| Web | Identidad, propiedad, decisiones, purga, cabeceras, carga a disco y validación DOCX reforzada implementadas. | Ensayo limpio, carga y DAST. |
| Cola | FIFO explícita, capacidad y cupo por usuario, admisión atómica, trabajadores limitados, timeout cooperativo y métricas agregadas. | Medir éxito y p95; documentar evidencia. |
| Ollama | Qwen 9B y Gemma 12B rechazados. Gemma v2.1 pasó smoke y obtuvo precisión 1.0 sin falsos positivos en difícil, pero exhaustividad 0.25 y exactitud 0.70. Sigue apagado. | Detener ajustes de prompt; considerar 27B sólo después de la demo y con ≥24 GB de acelerador. |
| Colab | Evidencias de Qwen v1 y Gemma v1/v2.0/v2.1 respaldadas localmente con hashes y checkpoints. | Revocar el token temporal; frente Colab cerrado para la demo. |
| CI/seguridad | CI aprobada en Python 3.11/3.14, análisis estático, dependencias/SBOM y secretos en el commit `34ff5bf`. | Ejecutar ZAP local y archivar los artefactos finales de seguridad. |
| SQL Server | Aplazado deliberadamente. | Sólo después del piloto y respuestas formales de TI. |
| Release | No creada: sería incorrecto etiquetar sin evidencia Colab, CI, carga y DAST. | Satisfacer checklist de `entrega_demo_2026-11-02.md` y entonces crear `demo-2026-11-02`. |

Los documentos, Excel, resultados de Colab y bancos reales permanecen fuera de
Git. Sólo se versionan código, casos sintéticos, hashes y métricas agregadas.
