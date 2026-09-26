# Revisión editorial ASF

La revisión usa el catálogo `2IN2RE01-02-2025-partial-1` y no modifica el DOCX. El análisis determinista funciona sin Ollama; el modelo local sólo interviene en reglas contextuales recuperadas para cada fragmento.

## Estados

- `confirmed`: el XML aporta evidencia suficiente.
- `possible`: existe una señal, pero puede aplicar una excepción o requiere interpretación.
- `not_evaluable`: OOXML no permite demostrar el cumplimiento.
- `excluded`: la categoría, el estilo o la configuración excluyó la comprobación.

Cada hallazgo conserva el valor efectivo, el origen del valor y evidencia estructural. La precedencia es formato directo, estilo aplicado, estilos base y `docDefaults`.

## Cobertura

| Área | Cobertura actual |
|---|---|
| Página | Carta, vertical, márgenes, encuadernación y distancias de encabezado/pie |
| Párrafos | Fuente, tamaño, alineación, interlineado, espaciado y longitud configurable |
| Notas | Fuente, tamaño y alineación cuando la parte OOXML está disponible |
| Cuadros | Fuente/tamaño, espaciado, bordes verticales explícitos y señal de alineación decimal |
| Siglas | Forma, plural, primera mención, reinicio en apartados especiales y glosario |
| Abreviaturas | Formas generales controladas y unidades de medida |
| Cifras | Separadores, porcentajes, mezclas, fracciones y decimales comparables mediante `numbers-1.3` |
| Gramática segura | Ocho detectores cerrados para gerundios, omisión de que, redundancia, repetición, perífrasis, subjuntivo, omisión de se y referencias vagas |
| Contexto | Registro de aprobación, recuperación léxica, JSON estricto, protección y tolerancia a fallos de Ollama |
| LanguageTool | Proveedor HTTP local experimental; sugerencias filtrables y siempre sujetas a revisión humana |
| Interoperabilidad | Exportación opcional SARIF 2.1.0 además de JSON, HTML y Markdown |

La alineación visual final, la paginación y la apariencia renderizada de bordes quedan reservadas a `VisualVerifier`. La implementación predeterminada `NullVisualVerifier` no requiere Microsoft Word y reporta estas limitaciones sin convertirlas en errores.

## Configuración

`min_paragraph_words`, `max_paragraph_words` y `excluded_style_patterns` controlan las heurísticas estructurales. `check_format` permite desactivar las comprobaciones de formato. `autofix` continúa desactivado y no se aceptan propuestas de Ollama que alteren elementos protegidos.

LanguageTool permanece desactivado por defecto. Su transporte sólo admite loopback y requiere activación experimental explícita. `language_tool_categories` y `language_tool_rule_ids` forman una lista de admisión; una caída o respuesta inválida se registra como estado parcial sin interrumpir las reglas ASF. Las propuestas que cambian elementos protegidos se separan como rechazadas.

La instalación local validada utiliza Temurin JRE 17 mediante su ruta explícita y LanguageTool 6.6 en `D:\arodriguezg\Tools\LanguageTool`. El Java 8 predeterminado del equipo no se modifica. Los scripts `start_languagetool.ps1` y `stop_languagetool.ps1` gestionan el proceso oculto y comprueban el puerto/PID antes de actuar. LanguageTool no ofrece `es-MX`; se usa español general (`es`). La ortografía `TYPOS` se evalúa como `possible`, con filtros para siglas conocidas, fragmentos cortos y una lista blanca institucional configurable.

La caché SQLite utiliza el hash del párrafo, idioma, reglas, endpoint y espacio de versión. No almacena el texto ni el contexto devuelto por LanguageTool. El piloto por lotes conserva aciertos, omisiones y ruta de la caché en cada reporte, permite reanudación por hash y genera un tablero HTML consolidado.

## Evidencia editorial de revisiones humanas

`scripts/build_revision_evidence_handoff.py` extrae localmente comentarios anclados y pares antes/después del control de cambios. El corpus conserva ubicación OOXML, hash documental, categoría sugerida y verificación de elementos protegidos, pero omite los nombres de los revisores. Los cambios no se consideran correctos automáticamente: el paquete humano solicita confirmar utilidad, categoría, interpretación, mejora y cualquier cambio de cifras, fechas, folios, siglas o nombres. La selección se separa por documento para reducir dependencia entre casos y se utiliza como evidencia de evaluación, no como entrenamiento automático.

## Presentación e interoperabilidad

El HTML ordena la revisión por utilidad: tablas y cifras; concordancia, claridad y ortografía; y finalmente formato agrupado en un bloque plegable. JSON conserva cada hallazgo individual y añade conteos `substantive_findings`, `format_occurrences`, `by_focus` y `groups_by_focus`.

La salida SARIF 2.1.0 conserva regla, nivel, método, estado, hash del DOCX y ubicación lógica. Es una salida complementaria para visores especializados; JSON continúa siendo el contrato completo del revisor.

Se evaluó reemplazar el escritor OOXML de comentarios por `Document.add_comment()` de `python-docx` 1.2.0. La API oficial sólo ancla rangos no vacíos de runs, mientras que el escritor actual localiza evidencia por XPath, agrupa alertas y valida comentarios preexistentes. Se conserva la implementación actual hasta disponer de pruebas equivalentes para párrafos vacíos, celdas, documentos con comentarios y estructuras OOXML no expuestas por la biblioteca.

## Bancos sintéticos

El banco determinista incluye casos positivos, negativos difíciles y formato OOXML. Se evalúa por ocurrencia de regla y fragmento, no sólo por conteos globales. El banco contextual permanece separado para no mezclar resultados deterministas con variabilidad del modelo.

El banco contextual efectivo contiene 100 casos sintéticos balanceados: 40 de desarrollo, 30 de calibración y 30 de prueba final. Incluye pares mínimos correctos/incorrectos y diez casos difíciles para una compuerta previa. Las expectativas se marcan pendientes de validación humana y los textos no constituyen datos de entrenamiento.

En la prueba rápida local del 23 de septiembre de 2026, `qwen3.5:4b` obtuvo precisión, exhaustividad, exactitud y acuerdo entre repeticiones de 1.0 sobre seis casos, sin respuestas inválidas ni propuestas inseguras. Dos ejecuciones tardaron 177.38 y 112.44 segundos. Estos resultados validan el mecanismo de estabilidad, pero la aprobación lingüística definitiva requiere ejecutar las 30 muestras y revisión humana de sus expectativas.

La corrida completa posterior cambió la conclusión: sobre 30 casos obtuvo precisión de 0.75, exhaustividad de 0.8571 y exactitud de 0.80, con tres respuestas estructuralmente inválidas y 893.32 segundos de duración. Una reevaluación focalizada de seis casos difíciles, después de reforzar el prompt, obtuvo precisión de 0.3333 y exhaustividad de 1.0 porque el modelo continuó marcando cuatro redacciones correctas. En consecuencia, `qwen3.5:4b` **no está aprobado para revisión contextual general**; Ollama permanece desactivado por defecto y sus resultados, cuando se habilite experimentalmente, requieren revisión humana.

`qwen3:8b` también está rechazado: en los seis casos difíciles obtuvo precisión de 0.3333, exhaustividad de 1.0 y exactitud de 0.3333, con cuatro falsos positivos y 420.75 segundos de duración. El registro `editorial-model-registry-1.0` impide activar normalmente ambos modelos. La aprobación futura exige precisión ≥ 0.90, exhaustividad ≥ 0.85, exactitud ≥ 0.90, acuerdo ≥ 0.95 en tres repeticiones y cero respuestas inválidas o alteraciones protegidas.
