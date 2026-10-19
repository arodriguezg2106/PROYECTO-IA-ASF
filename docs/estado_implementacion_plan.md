# Estado maestro del plan

Actualizado: 19 de octubre de 2026. Objetivo inmediato: demo reproducible el 2
de noviembre de 2026.

| Frente | Estado verificable | Próxima compuerta |
|---|---|---|
| Adjudicación | Segunda revisión importada; 26 decisiones fueron delegadas y aún no se consideran recibidas. | Validar el libro final, importar y generar banco real/hashes. No bloquea la demo sintética. |
| Banco editorial | Generadores y bancos sintéticos disponibles. LanguageTool 6.6 obtuvo precisión 1.0 y exhaustividad 0.4737; permanece rechazado. | Repetir con banco real sin reducir exhaustividad 0.75. |
| Web | Identidad, propiedad, decisiones, purga, cabeceras, carga a disco y validación DOCX reforzada implementadas. | Ensayo limpio, carga y DAST. |
| Cola | FIFO explícita, capacidad y cupo por usuario, admisión atómica, trabajadores limitados, timeout cooperativo y métricas agregadas. | Medir éxito y p95; documentar evidencia. |
| Ollama | Integración opcional detrás de perfil/digest, loopback, modo demo y un trabajador. Falla como `partial` sin bloquear el motor. | Ejecutar Qwen 9B y Gemma 12B en sesiones Colab separadas. |
| Colab | Libreta privada parametrizada, token en Secrets, checkpoints 2/10/30 y metadatos de GPU/modelo. | Publicar commit, ejecutar dos sesiones, descargar JSON y revocar token. |
| CI/seguridad | Workflow preparado: Python 3.11/3.14, `pip-audit`, Bandit, Gitleaks y SBOM. Pruebas de aplicación ampliadas. | Confirmar primera ejecución en GitHub y ejecutar ZAP local. |
| SQL Server | Aplazado deliberadamente. | Sólo después del piloto y respuestas formales de TI. |
| Release | No creada: sería incorrecto etiquetar sin evidencia Colab, CI, carga y DAST. | Satisfacer checklist de `entrega_demo_2026-11-02.md` y entonces crear `demo-2026-11-02`. |

Los documentos, Excel, resultados de Colab y bancos reales permanecen fuera de
Git. Sólo se versionan código, casos sintéticos, hashes y métricas agregadas.
