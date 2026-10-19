# Expediente de la demo ejecutiva — 2 de noviembre de 2026

## Entregable obligatorio

La demostración funciona sin IA: web determinística, reglas editoriales ASF,
cola FIFO y reportes JSON/HTML/DOCX con un documento sintético. Ollama sólo se
muestra si un candidato supera la evaluación sintética y existe un perfil
válido; una falla del proveedor no interrumpe el resultado base.

## Compuertas antes de etiquetar `demo-2026-11-02`

- [ ] CI verde en Python 3.11 y 3.14.
- [ ] `pip-audit`, Bandit y Gitleaks sin vulnerabilidades críticas/altas.
- [ ] SBOM CycloneDX archivado con el expediente.
- [ ] Suite completa y `git diff --check` limpios.
- [ ] Instalación limpia y guion ensayados en otra carpeta.
- [ ] Carga: FIFO, cupo por usuario, `503`, p95 ≤ 30 s y ≥95 % de éxito.
- [ ] ZAP ejecutado; alertas medias resueltas o justificadas.
- [ ] JSON de Qwen y Gemma adjuntos, incluso si ambos fallan.
- [ ] Riesgos residuales y reversión aprobados.

## Evidencia local del 19 de octubre

- 258 pruebas aprobadas en Python 3.14 (`258 passed`).
- Bandit sin hallazgos de severidad alta.
- `pip-audit` sin vulnerabilidades conocidas tras actualizar `lxml` a 6.1.0 y
  `pytest` a 9.0.3.
- Carga sintética local: 8 solicitudes, 2 aceptadas, 4 rechazadas con `503`, 2
  limitadas con `429`, 100 % de éxito entre las aceptadas y p95 de 0.311 s.

La evidencia local no reemplaza la ejecución de CI en GitHub ni ZAP. El JSON de
carga permanece en `results/demo/`, fuera de Git.

La adjudicación delegada se importa si llega a tiempo, pero no bloquea la demo.
Sí bloquea la aprobación institucional de proveedores lingüísticos.

## Guion de 10–15 minutos

1. Explicar que el documento no sale del equipo y el motor determinístico es la
   autoridad (1 min).
2. Iniciar `scripts/start_local_demo.ps1`, cargar el DOCX sintético y mostrar la
   posición de cola (2 min).
3. Mostrar alertas, limitaciones neutrales, ubicación y decisiones (4 min).
4. Descargar HTML, JSON y DOCX; recalcar que no hay autocorrección (2 min).
5. Mostrar saturación controlada, aislamiento y telemetría (2 min).
6. Presentar el comparativo Colab, incluido un resultado negativo (2 min).
7. Cerrar con pendientes de TI y ruta QA → piloto → producción (1–2 min).

## Reversión

Detener la web, restaurar el artefacto/commit anterior y eliminar la carpeta
efímera sólo tras confirmar su ruta. Ollama y LanguageTool se deshabilitan
retirando sus variables; el flujo determinístico no depende de ellos.

## Pendientes institucionales posteriores

IIS/WIA, HTTPS, cuenta de servicio, servidor/GPU, almacenamiento, retención,
monitoreo, DEV/QA/PROD y decisión de SQL Server. Persistencia y cola durable
comienzan sólo después del piloto y la compuerta formal de TI.
