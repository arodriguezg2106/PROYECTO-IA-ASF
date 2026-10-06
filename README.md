# Revisor de CRF

Lector y motor híbrido local para Word **DOCX**. Las reglas determinísticas funcionan sin servicios externos; opcionalmente, una capa semántica mediante Ollama relaciona cifras narrativas con conceptos y columnas de tablas sin enviar documentos a internet.

## Estructura

```text
src/revisor_crf/
    reader.py       # Extracción estructural y exportación JSON
    review.py       # Motor de validaciones determinísticas
    semantic.py     # Contratos, proveedor local, doble verificación y caché
    semantic_service.py # Fachada institucional con autenticación, TLS y cola
    html_report.py  # Reporte local y registro de decisiones
    catalog.py      # Expresiones configurables de las reglas
    cli.py          # Interfaz de línea de comandos
    sample.py       # Generador de un documento totalmente sintético
    __main__.py     # Ejecución con python -m revisor_crf
tests/
    test_reader.py  # Pruebas con documentos generados en una carpeta temporal
requirements.txt
pyproject.toml
.gitignore
```

## Instalación en Windows (PowerShell)

Requiere Python 3.11 o posterior (probado con 3.14.0). Ejecute los comandos desde la raíz del proyecto. No es necesario activar el entorno, cambiar la política de ejecución ni definir `PYTHONPATH`; la instalación editable conecta el comando con el código de `src`.

### Instalación normal (con internet)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

`requirements.txt` incluye las dependencias de ejecución (`python-docx`, `lxml`) y también `pytest`, que solo necesitan los desarrolladores.

### Instalación institucional (sin internet)

Requiere un repositorio de wheels preparado previamente. `vendor/wheels/` **no forma parte del repositorio** (está en `.gitignore`): debe crearse en un equipo con internet y copiarse al equipo destino, con la misma versión de Python y arquitectura Windows. Preparación, en el equipo con internet:

```powershell
python -m pip download -r requirements.txt -d .\vendor\wheels
python -m pip download setuptools wheel -d .\vendor\wheels
```

Instalación en el equipo sin internet (entorno aislado):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\vendor\wheels -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\vendor\wheels -e .
```

Si falta una versión indicada, pip falla con `No matching distribution found`: no intenta descargarla.

Alternativa para un Python que ya tiene instaladas las versiones exactas de `requirements.txt` (entorno **no aislado**, comparte los paquetes del sistema):

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-index --no-build-isolation -e .
```

### Dependencias opcionales para reportes y Excel

`openpyxl` solo se necesita para los scripts de paquetes de validación en Excel (`scripts/human_validation_small.py`, `scripts/build_*_handoff.py`, `scripts/verify_inventory_package.py`, `scripts/workbook_helpers.py`). La revisión normal del CRF no lo usa.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-reporting.txt
```

En una instalación sin internet, añada la wheel de `openpyxl` (y `et-xmlfile`) a `vendor/wheels/` y use `--no-index --find-links .\vendor\wheels`.

### Funciones opcionales y experimentales

La revisión semántica con **Ollama** y la revisión editorial con **LanguageTool** u Ollama están desactivadas por defecto, son experimentales, requieren software externo local y no son necesarias para el flujo descrito abajo. Ningún comando de las secciones principales las necesita.

## Generar y leer el ejemplo sintético (comprobación de la instalación)

```powershell
.\.venv\Scripts\python.exe -m revisor_crf.sample .\data\sintetico.docx
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx --output .\results\sintetico.json
```

Para leer otro archivo local, sustituir la ruta de entrada. La salida debe terminar en `.json`; se crean sus directorios cuando no existen. Un JSON existente en esa ruta se sobrescribe. El DOCX de entrada no se modifica. Ante una entrada inexistente o inválida, la interfaz informa el error y termina con código 1.

## Motor de validaciones determinísticas

Los ejemplos usan `.\data\sintetico.docx` (generado en la sección anterior). Para revisar su propio CRF, copie el DOCX a `.\data\` —carpeta ignorada por Git— y sustituya la ruta de entrada; el original nunca se modifica.

```powershell
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx --mode final --review -o .\results\revision.json --html .\results\revision.html --commented-docx .\results\crf_REVISION_IA.docx
```

`--review` comprueba subtotales y totales, relaciones de importes entre tabla y narrativa, y congruencia explícita entre observación y conclusión. El JSON `review-1.1` conserva operación, valores, diferencia, unidad, evidencia, origen determinístico o híbrido y una ruta humana con resultado, tabla, fila, columna y texto de búsqueda. El HTML funciona sin servidor ni recursos externos: muestra el bloque “Dónde revisar”, permite copiar la ubicación o el texto para buscar en Word, desglosa los cálculos por fila y permite filtrar, clasificar, comentar, importar y descargar decisiones humanas. Las decisiones del navegador se vinculan al SHA-256 del DOCX y nunca modifican el original.

## Revisión semántica local (opcional y experimental)

La revisión semántica es opcional. Requiere Ollama instalado, uno de los modelos aprobados descargado localmente y una copia de `semantic-config.example.toml` ajustada al equipo. El modelo propone relaciones; únicamente las reglas del programa calculan diferencias y crean alertas. Las relaciones dudosas aparecen en el HTML y nunca se agregan como comentarios de Word.

```powershell
ollama pull qwen3.5:4b
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx --review --semantic-review --semantic-config .\semantic-config.example.toml -o .\results\revision.json --html .\results\revision.html --commented-docx .\results\crf_REVISION_IA.docx
```

Si Ollama no responde, el comando termina la revisión determinística, registra una advertencia y genera los archivos solicitados. La caché SQLite usa el hash del documento, caso, modelo, prompt y esquema; no guarda documentos completos. La instalación institucional, el dataset aprobado y la selección reproducible del modelo se describen en [`docs/revision_semantica.md`](docs/revision_semantica.md).

La regla de totales reconoce subtotales con nombre de fondo y construye el total general con esos subtotales, sin duplicar sus detalles. También puede comprobar una suma dentro de una misma columna homogénea cuando la moneda no está escrita, sin atribuirle una unidad inventada; las diferencias de escala, signo o unidades explícitas continúan bloqueando la operación automática.

`--commented-docx` crea una copia independiente con comentarios verdaderos de Word anclados al párrafo o celda principal de cada alerta. Varias alertas de la misma ubicación se agrupan en un solo comentario. Los comentarios presentan el identificador, la ubicación, los valores y la acción sugerida; nunca corrigen el contenido ni sobrescriben el CRF original.

Si el documento no produce alertas (como `sintetico.docx`), la copia comentada queda idéntica en contenido al original y no contiene `comments.xml`. Para ver un comentario real, cree un documento sintético con una discrepancia (total 200 frente a una suma de 150):

```powershell
@'
from docx import Document
d = Document()
d.add_paragraph("Cuadro 1. Recursos (miles de pesos)")
t = d.add_table(rows=4, cols=2)
for r, (a, b) in enumerate([("Concepto", "Importe"), ("Rubro A", "100.0"), ("Rubro B", "50.0"), ("Total", "200.0")]):
    t.cell(r, 0).text = a
    t.cell(r, 1).text = b
d.add_paragraph("El total fue de 150.0 miles de pesos.")
d.save("data/alerta.docx")
'@ | .\.venv\Scripts\python.exe -
.\.venv\Scripts\python.exe -m revisor_crf .\data\alerta.docx --review -o .\results\alerta.json --html .\results\alerta.html --commented-docx .\results\alerta_REVISION_IA.docx
```

La evaluación de una integración posterior mediante un complemento de panel lateral de Word se documenta en [`docs/evaluacion_integracion_word.md`](docs/evaluacion_integracion_word.md). La recomendación actual es validar primero las copias comentadas y conservar el complemento como una segunda fase sujeta a compatibilidad y despliegue institucional.

Las etiquetas y frases pueden ajustarse con `--rules catalogo.json`. El catálogo es un objeto JSON que puede sustituir `version`, `total_labels`, `observation_positive`, `observation_negative`, `conclusion_markers` o `scope_markers`; las expresiones omitidas conservan los valores predeterminados. `--numbers` se mantiene sin cambios y no puede combinarse con `--review`.

## Revisión editorial ASF (cobertura inicial, opcional)

El módulo editorial es opcional, no modifica el DOCX y funciona sin Ollama. Usa el catálogo versionado `2IN2RE01-02-2025-partial-1`, derivado del PDF institucional local. El modo recomendado y predeterminado es `final`.

```powershell
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx --mode final --review --editorial-review -o .\results\revision.json --html .\results\revision.html --markdown .\results\revision.md
```

Para activar la revisión contextual local, copie y ajuste `editorial-config.example.toml` y agregue `--editorial-ollama --editorial-config .\editorial-config.toml`. Para desactivarla, omita `--editorial-ollama` o mantenga `ollama_enabled = false`. Los fallos de Ollama se registran por fragmento y no interrumpen las reglas deterministas.

Un modelo sólo puede activarse normalmente si figura como `approved` en el registro versionado. Para una evaluación controlada de un modelo no aprobado debe agregarse `--editorial-experimental-model`; todas sus propuestas requieren revisión humana y esta opción no equivale a una aprobación.

### LanguageTool local (opcional y experimental)

LanguageTool puede complementar las reglas ASF con sugerencias gramaticales locales. La integración no consulta la API pública: sólo admite `http://localhost`, `127.0.0.1` o `::1`, permanece desactivada por defecto y no incorpora sus resultados como errores confirmados. La instancia autónoma debe iniciarse por separado en el puerto configurado; el ejemplo supone `http://127.0.0.1:8081/v2`.

Requiere Java 17 y una instalación autónoma de LanguageTool. Los valores predeterminados de [`scripts/start_languagetool.ps1`](scripts/start_languagetool.ps1) corresponden al equipo del autor; en otro equipo no se edita el script: las rutas se pasan como parámetros `-JavaExe` y `-LanguageToolDir`. El servidor se controla sin ventanas visibles y no se inicia automáticamente con Windows:

```powershell
.\scripts\start_languagetool.ps1 `
  -JavaExe "C:\ruta\a\java.exe" `
  -LanguageToolDir "C:\ruta\a\LanguageTool"
```

Para detenerlo:

```powershell
.\scripts\stop_languagetool.ps1
```

```powershell
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx --mode final --review --editorial-review --editorial-language-tool --editorial-experimental-provider -o .\results\revision.json --html .\results\revision.html --markdown .\results\revision.md
```

Las categorías y reglas admitidas pueden limitarse mediante `language_tool_categories` y `language_tool_rule_ids` en `editorial-config.example.toml`. Se usa el código `es` porque LanguageTool 6.6 no ofrece una variante `es-MX`. La categoría ortográfica `TYPOS` está habilitada y se filtran automáticamente siglas reconocidas, fragmentos demasiado cortos y términos incluidos expresamente en `language_tool_accepted_terms`. No se descarta una palabra común sólo por parecer nombre propio. Toda coincidencia se marca `possible`, `requires_human_review` y método `language_tool`; el fallo o tiempo de espera del servidor se registra sin detener el análisis determinista.

El reporte HTML presenta primero las validaciones de tablas y cifras, después concordancia, claridad y ortografía. Las incidencias de formato se agrupan por regla, mensaje y estado dentro de un bloque plegable secundario; se conservan todas sus ubicaciones para auditoría sin dominar el conteo principal. La opción `--sarif .\results\revision.sarif` genera además un archivo SARIF 2.1.0 compatible con visores especializados, sin sustituir los reportes JSON, HTML o Markdown.

Cada ocurrencia editorial del HTML permite registrar una decisión humana y un comentario. La descarga usa el esquema `review-decisions-1.2` e incluye alertas numéricas, relaciones semánticas y hallazgos editoriales con su tipo explícito. Estas decisiones pueden convertirse en un dataset anonimizado para un futuro priorizador de falsos positivos; el procedimiento y sus garantías se describen en [`docs/aprendizaje_editorial.md`](docs/aprendizaje_editorial.md). El mecanismo no entrena ni activa todavía ningún modelo.

### Piloto por lotes

> **Solo desarrolladores.** Desde esta sección hasta antes de «Ejecutar las pruebas» los comandos con `scripts/` se ejecutan desde la raíz del clon, con `$env:PYTHONPATH = "src;scripts"`, y suponen carpetas locales que no vienen en el repositorio (`.\CRF-ejemplos`). `scripts/evaluate_editorial.py --regenerate` sí es reproducible: genera sus propios DOCX sintéticos.

El piloto puede seleccionar documentos representativos por extensión, cuadros, siglas y control de cambios. Genera un tablero consolidado, cuatro formatos por documento, conserva un punto de reanudación y comparte una caché de LanguageTool que almacena hashes y metadatos, nunca párrafos.

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/pilot_editorial_crf.py .\CRF-ejemplos `
  --output .\results\editorial_pilot_5_lt `
  --sample-size 5 `
  --language-tool `
  --resume
```

La opción `--resume` sólo reutiliza un documento cuando conserva el mismo SHA-256 y siguen presentes todas sus salidas. `language_tool_cache_namespace` debe cambiar cuando se actualice la versión o configuración lingüística que afecte los resultados.

La cobertura determinista comprende porcentajes, separadores, cantidades mixtas, fracciones, consistencia decimal, siglas, abreviaturas, unidades, palabras no recomendadas y formato OOXML efectivo de páginas, párrafos, notas y cuadros. La paginación y apariencia renderizada permanecen desacopladas mediante un verificador visual nulo. La matriz de cobertura, estados y limitaciones se documenta en [`docs/revision_editorial_asf.md`](docs/revision_editorial_asf.md). No se afirma cobertura total de las instrucciones.

Para generar y evaluar el banco editorial sintético determinista:

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/evaluate_editorial.py --regenerate
```

El comando crea DOCX inventados y exporta `results/editorial_validation/evaluation.json` y `.md`. Devuelve código `0` cuando no hay falsos positivos ni omisiones, `2` cuando las métricas detectan diferencias y `1` ante un error de ejecución. El banco no acepta Ollama para evitar mezclar la calibración determinista con la evaluación contextual.

La evaluación contextual se ejecuta por separado sobre textos completamente sintéticos:

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/evaluate_editorial_context.py --models qwen3.5:4b
```

El resultado queda en `results/editorial_context/model-evaluation.json`. El banco efectivo contiene 100 casos sintéticos separados en desarrollo, calibración y prueba. Puede usarse `--focused-first` para ejecutar primero diez casos difíciles. Un modelo sólo se aprueba con precisión ≥ 0.90, exhaustividad ≥ 0.85, exactitud ≥ 0.90, acuerdo ≥ 0.95 en tres repeticiones, sin JSON inválido ni alteraciones de elementos protegidos.

Para medir estabilidad, use `--repetitions 3`. Una prueba rápida puede limitarse con `--max-cases 6`; la aprobación completa debe ejecutarse sin ese límite y exige al menos 0.95 de acuerdo entre repeticiones.

La evaluación completa vigente no aprueba `qwen3.5:4b` para uso contextual general. La prueba corta fue perfecta, pero no se sostuvo al ampliar la diversidad: Ollama debe mantenerse desactivado salvo experimentación controlada y revisión humana.

## Ejecutar las pruebas (desarrolladores)

Requiere `pytest` (incluido en `requirements.txt`) y el proyecto instalado en modo editable.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Pytest utiliza `.pytest_runtime`, una carpeta temporal exclusiva para la ejecución, porque el directorio temporal global de Windows puede quedar con permisos bloqueados. Las pruebas generan todos sus documentos: no requieren datos reales. Verifican orden, Unicode, estilos, secciones, encabezados y pies heredados, tablas anidadas, combinaciones, trazabilidad XML, identificadores únicos y deterministas, JSON, errores y conservación del archivo original.

## Contrato del JSON

- `schema_version`: versión del formato de salida (`1.2`); `reading_mode` identifica la vista elegida.
- `blocks`: párrafos y tablas del cuerpo en orden XML, incluidos los párrafos vacíos.
- `sections`: secciones de Word y sus encabezados y pies, con variantes normal, primera página y páginas pares cuando existen. Se indican las opciones que controlan su uso y si se heredan de la sección anterior. Una parte compartida se extrae una sola vez: las demás secciones conservan `part` y `content_ref` al identificador de la primera representación, con `blocks` vacío.
- `supplementary_parts`: comentarios, notas al pie y notas finales, separados del cuerpo, con `xml_id`, `kind`, `note_type` y `blocks`. Incluye los párrafos vacíos de separadores; `section_id` es `null` porque estas partes no tienen una sección propia.
- `warnings`: contenido detectado que no se interpreta completamente.

Cada párrafo, tabla, fila y celda conserva `id`, `type`, `parent_id`, `section_id`, `headings`, `text` y `source`. Los párrafos y tablas incluyen `style` (identificador y nombre); las filas y celdas no tienen un estilo de párrafo propio: sus párrafos conservan el suyo y la tabla conserva su estilo. `headings` contiene la jerarquía de títulos vigente, detectada mediante el nivel de esquema del párrafo o sus estilos base. Un título se incluye en su propia jerarquía. Los títulos dentro de una celda se limitan a esa celda.

Los identificadores expresan la jerarquía, por ejemplo `body/b0003/r0001/c0002/b0001`. Son reproducibles para el mismo documento y cambian si se insertan o eliminan elementos anteriores; no son identificadores persistentes entre ediciones. Las posiciones empiezan en 1.

El recorrido atraviesa controles de contenido, XML personalizado y envoltorios de revisiones sin perder la secuencia de párrafos y tablas. Las celdas y filas también pueden tener envoltorios. `xml_containers` conserva la cadena de contenedores de origen.

Los párrafos dentro de formas/cuadros de texto aparecen en `blocks` del párrafo contenedor. Su campo `content` alterna fragmentos de texto y referencias a bloques en el orden XML; el texto del párrafo contenedor no duplica el de sus párrafos descendientes. Esta secuencia indica el anclaje XML, no el orden visual de formas flotantes. Si el paquete incluye ramas alternativas Choice/Fallback, ambas se conservan como ubicaciones XML distintas, identificables por sus contenedores.

`text` contiene el texto de la vista seleccionada; `text_all` conserva el texto XML propio completo, incluido texto insertado y eliminado. `content` mantiene todos los fragmentos, con `revision_status`, `included`, `source_start` y `source_end` (offsets en `text_all` para fragmentos de texto). Los fragmentos y los bloques conservan además `revisions` con tipo e identificador: no se aceptan ni rechazan cambios en el DOCX. Las instrucciones de campos se separan del texto visible almacenado; no se calculan. Las referencias a notas/comentarios conservan sus identificadores XML.

`source` conserva el nombre del archivo, la parte del paquete (por ejemplo `/word/document.xml`) y una ruta XPath al elemento XML. Los prefijos de la ruta se resuelven con los espacios de nombres de esa parte. La sección se determina por las propiedades `sectPr` de Word: el párrafo que cierra una sección pertenece a esa sección.

Las tablas contienen `rows`; las filas contienen `cells`; cada celda contiene `blocks`, incluidas las tablas anidadas. El texto agregado usa saltos de línea entre bloques/filas y tabulaciones entre celdas; para reconstruir la estructura debe usarse la jerarquía, no ese texto agregado.

Se recorren las celdas físicas del XML, sin expandir combinaciones ni duplicar su contenido. `column_span` indica cuántas columnas ocupa una celda; `vertical_merge` vale `restart`, `continue` o `null`. `grid_column`, `grid_before` y `grid_after` conservan la posición en la cuadrícula incluso con celdas omitidas.

## Alcance y límites

La ubicación es estructural: no se calculan páginas, coordenadas visuales ni numeración automática de listas. El lector conserva texto y estilo de párrafo/tabla, no el formato visual completo de cada fragmento, imágenes o apariencia final de Word. No evalúa campos ni interpreta objetos, `altChunk`, imágenes o símbolos que requieran una fuente especial. Se emiten advertencias para los elementos especiales contemplados por el lector. No es una reproducción completa de todos los componentes del formato Word.

El recorrido utiliza `python-docx` y acceso XML con `lxml`; algunas operaciones necesitan interfaces internas de `python-docx`, por eso se fijan versiones y se prueban las estructuras relevantes. El archivo se procesa en memoria. `.doc`, `.docm`, archivos cifrados y documentos dañados no son entradas compatibles.

`.gitignore` excluye documentos Word/PDF, carpetas de entradas y resultados, temporales y entornos virtuales. Mantener los resultados en `results/` para que queden excluidos. No se han utilizado documentos reales.

## Auditoría del lote CRF

> **Solo desarrolladores.** Requiere un clon del repositorio y `$env:PYTHONPATH`. Los DOCX de `tests/CRF-sinteticas` y los resultados históricos son artefactos locales ignorados por Git; no vienen en una instalación nueva.

La carpeta `tests/CRF-sinteticas` contiene los ejemplos aportados para la auditoría manual; las pruebas automatizadas siguen generando exclusivamente sus propios documentos. La auditoría compara todos los párrafos `w:p` de `word/*.xml` con las ubicaciones recuperadas y verifica integridad SHA-256, texto completo, duplicados y orden. No imprime texto de las CRF ni exporta su contenido completo.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv\Scripts\python.exe scripts\audit_crf.py despues
.\.venv\Scripts\python.exe scripts\summarize_audit.py
```

Resultados en `results/auditoria_crf/`:

- `antes.json`: línea base conservada, tomada antes de corregir el lector. No se sobrescribe.
- `despues.json`: inventario y métricas por documento, sin texto, con longitudes, hashes, tipos de contenedor y estilos.
- `reporte.md`: comparación y trazabilidad de los 157 párrafos inicialmente omitidos, y de los párrafos previamente parciales.
- `estilos_y_formatos.md`: frecuencias de estilos y combinaciones de tamaño/negrita/alineación, con alcance y limitaciones de la resolución de formato.

El resumen requiere la línea base y el reporte histórico `results/reporte_crf/reporte.json`; ambos son artefactos locales ignorados por Git. El modo `antes` existe para capturar una línea base en un directorio de resultados nuevo, pero ejecutarlo con el lector actual no reproduce la versión anterior. La cobertura mide texto Unicode explícito en el XML, no texto visible en imágenes ni valores recalculados de campos. No incluye evaluación gramatical, normativa o de cifras, ni detección heurística de títulos.

## Vistas de cambios controlados

```powershell
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx -o .\results\lectura.json --mode final
```

| Modo | Texto incluido para análisis |
|---|---|
| `final` (predeterminado) | `normal`, `inserted`, `moved_to` |
| `original` | `normal`, `deleted`, `moved_from` |
| `all` | Todos, incluido `unknown`, con estado explícito |

La estructura completa y los fragmentos excluidos siempre se conservan: un párrafo eliminado sigue teniendo ID, origen y `text_all`, aunque su `text` esté vacío en modo final. Un párrafo con estados mezclados tiene `revision_status=unknown` y `revision_status_reason=mixed_fragments`; sus fragmentos conservan los estados individuales y se filtran por separado. Revisiones anidadas incompatibles se etiquetan `unknown` y solo se analizan en `all`.

Se reconocen envoltorios de inserción/eliminación/movimiento, rangos XML de movimiento y marcas de inserción/eliminación de filas y celdas. La eliminación de la marca de fin de párrafo no se interpreta como eliminación de todo su contenido. La vista no simula la maquetación ni las uniones visuales de párrafos de Word.

## Inventario y normalización de cifras

```powershell
# Un documento; exporta exclusivamente el inventario y sus metadatos.
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx --numbers --mode final -o .\results\cifras.json

# Solo desarrolladores: requiere el clon del repositorio y los 14 DOCX locales de tests/CRF-sinteticas (no incluidos).
.\.venv\Scripts\python.exe scripts\inventory_numbers.py --mode final
.\.venv\Scripts\python.exe scripts\inventory_numbers.py --mode original
.\.venv\Scripts\python.exe scripts\inventory_numbers.py --mode all
```

Cada ejecución guarda un JSON y un Markdown por documento, más `resumen.json` y `resumen.md`, en `results/inventario_cifras/<modo>/`. Los informes incluyen cifras ambiguas y no clasificadas, sin exportar el texto completo. El contexto inmediato está limitado a 150 caracteres y los encabezados candidatos de fila/columna a 80.

La API `revisor_crf.numbers.extract_numbers(read_docx(ruta, mode='final'))` devuelve valores `Decimal`. `export_json` los serializa como cadenas exactas, evitando la pérdida de precisión de JSON/float. Cada cifra conserva texto y valor originales, valor decimal, clasificación, unidad, multiplicador, valor normalizado, símbolo monetario, contexto, coordenadas de tabla, IDs, sección, origen XML, estado de revisión y offsets. Para fechas y folios alfanuméricos el decimal puede ser `null`; los identificadores no se escalan y su normalizado es `null`. Los ceros iniciales se conservan en `valor_original`.

- Pesos: multiplicador 1; miles de pesos: 1000; millones de pesos y `mdp`: 1000000. `$` sin otra evidencia no identifica una moneda concreta y se marca ambiguo.
- Porcentajes: se conservan en puntos porcentuales, con multiplicador 1; `12.5%` permanece en 12.5, no se convierte en 0.125.
- Convención numérica de base mexicana: coma de miles y punto decimal. Se admiten espacios de agrupación, coma decimal no compatible con agrupación, y pares invertidos como `1.234,56`. `1,234` se interpreta como 1234 y `1.234` como 1.234 según esa convención; no se detecta automáticamente la configuración regional del documento. Separadores inválidos o inferencias adicionales se señalan.
- Fechas numéricas día/mes/año o ISO, y fechas con mes español, se registran como un candidato completo. Artículos, folios y números de auditoría se identifican mediante rótulos explícitos. Los años inferidos solo por el rango 1900–2099 se marcan ambiguos.
- Las cantidades sin unidad explícita se conservan como cantidades ambiguas; los identificadores o intervalos sin contexto quedan como `otro`/no clasificados. No se supone que todos los números sean importes.
- En tablas se usan filas `tblHeader` o, como candidato estructural, la primera fila anterior, y la celda textual izquierda. Se registran IDs y método de atribución; no es un detector semántico de encabezados. Un rótulo breve de unidad inmediatamente anterior a una tabla también puede aportar escala. Las tablas anidadas tienen coordenadas propias. Los encabezados y unidades se proyectan por modo de revisión.

En el inventario `all`, las vistas final y original se examinan por separado: una sustitución de `100` por `200` no produce `100200`. Las mismas ocurrencias compartidas entre ambas vistas se deduplican por posiciones de origen y clasificación/unidad, no por igualdad del valor. Cada registro indica sus `vistas`; las revisiones desconocidas se examinan aisladas y se marcan ambiguas. El estado numérico refleja los fragmentos del número y su unidad explícita; las unidades heredadas de encabezados conservan su vista y origen aparte.

El inventario es léxico y conservador: no interpreta cifras escritas con palabras, no garantiza clasificación semántica completa y no evalúa consistencia, suma tablas, compara cifras repetidas ni revisa gramática. La comprobación de cobertura del lote utiliza `text_all`, y la auditoría XML usa `mode='all'`, para distinguir filtrado de revisiones de pérdida de información.

## Validación individual

La estrategia vigente sustituye la muestra de 200 registros por 30 y prioriza pruebas sintéticas automatizadas. El paquete anterior no se regenera.

Consulta [la guía de validación individual](docs/validacion_individual.md) para los resultados esperados, los cinco DOCX sintéticos, la política high/medium/low y los comandos de ejecución.

El XLSX vigente es results/validacion_humana_reducida/validacion_final_30.xlsx. Incluye cinco campos humanos en blanco. El reporte es results/inventario_cifras/final/cobertura_confianza.md.

El formato numbers-1.1 añade classification, confidence, usable_for_comparison, reason y origin_unit. Los ambiguos conservan classification=ambiguous; tipo mantiene la hipótesis léxica, no una decisión forzada. Sólo high es utilizable. Años, fechas y referencias legales/documentales nunca son high. El filtrado no elimina evidencia XML.
## Auditoría focalizada

La política actual de unidades e identificadores y los comandos para regenerar el diagnóstico y la muestra se documentan en [docs/auditoria_focalizada.md](docs/auditoria_focalizada.md). Esa política sustituye las descripciones históricas anteriores de confianza y elegibilidad genérica.
