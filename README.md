# Revisor de CRF

Lector y motor de validaciones determinísticas para Word **DOCX**, sin Ollama, RAG, normativa ni inteligencia artificial. No utiliza servicios externos ni necesita internet para ejecutarse.

## Estructura

```text
src/revisor_crf/
    reader.py       # Extracción estructural y exportación JSON
    review.py       # Motor de validaciones determinísticas
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

Requiere Python 3.11 o posterior. Ejecutar los comandos desde la raíz del proyecto. La primera configuración se realizó con Python 3.14.0 y paquetes ya instalados, sin descargas:

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --no-index -r requirements.txt
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
```

Este entorno virtual aprovecha los paquetes de la instalación local de Python; **no está completamente aislado**. `--no-index` impide consultar índices de paquetes. Si faltan las versiones indicadas, la instalación falla: no intenta descargarlas.

Para una instalación aislada y sin internet en otro equipo, colocar previamente las ruedas (`.whl`) compatibles de las dependencias y sus dependencias transitivas en `vendor/wheels/`, dentro del proyecto. En un entorno nuevo:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\vendor\wheels -r requirements.txt
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
```

No es necesario activar el entorno ni cambiar la política de ejecución de PowerShell. Repetir la asignación de `PYTHONPATH` al abrir una nueva terminal. El código funciona directamente desde `src`, sin instalar el proyecto ni descargar herramientas de construcción.

## Generar y leer el ejemplo sintético

```powershell
.\.venv\Scripts\python.exe -m revisor_crf.sample .\data\sintetico.docx
.\.venv\Scripts\python.exe -m revisor_crf .\data\sintetico.docx --output .\results\sintetico.json
```

Para leer otro archivo local, sustituir la ruta de entrada. La salida debe terminar en `.json`; se crean sus directorios cuando no existen. Un JSON existente en esa ruta se sobrescribe. El DOCX de entrada no se modifica. Ante una entrada inexistente o inválida, la interfaz informa el error y termina con código 1.

## Motor de validaciones determinísticas

```powershell
.\.venv\Scripts\python.exe -m revisor_crf .\data\crf.docx --mode final --review -o .\results\revision.json --html .\results\revision.html --commented-docx .\results\crf_REVISION_IA.docx
```

`--review` comprueba subtotales y totales, relaciones de importes entre tabla y narrativa, y congruencia explícita entre observación y conclusión. El JSON `review-1.0` conserva operación, valores, diferencia, unidad, evidencia y una ruta humana con resultado, tabla, fila, columna y texto de búsqueda. El HTML funciona sin servidor ni recursos externos: muestra el bloque “Dónde revisar”, permite copiar la ubicación o el texto para buscar en Word, desglosa los cálculos por fila y permite filtrar, clasificar, comentar, importar y descargar decisiones humanas. Las decisiones del navegador se vinculan al SHA-256 del DOCX y nunca modifican el original.

La regla de totales reconoce subtotales con nombre de fondo y construye el total general con esos subtotales, sin duplicar sus detalles. También puede comprobar una suma dentro de una misma columna homogénea cuando la moneda no está escrita, sin atribuirle una unidad inventada; las diferencias de escala, signo o unidades explícitas continúan bloqueando la operación automática.

`--commented-docx` crea una copia independiente con comentarios verdaderos de Word anclados al párrafo o celda principal de cada alerta. Varias alertas de la misma ubicación se agrupan en un solo comentario. Los comentarios presentan el identificador, la ubicación, los valores y la acción sugerida; nunca corrigen el contenido ni sobrescriben el CRF original.

La evaluación de una integración posterior mediante un complemento de panel lateral de Word se documenta en [`docs/evaluacion_integracion_word.md`](docs/evaluacion_integracion_word.md). La recomendación actual es validar primero las copias comentadas y conservar el complemento como una segunda fase sujeta a compatibilidad y despliegue institucional.

Las etiquetas y frases pueden ajustarse con `--rules catalogo.json`. El catálogo es un objeto JSON que puede sustituir `version`, `total_labels`, `observation_positive`, `observation_negative`, `conclusion_markers` o `scope_markers`; las expresiones omitidas conservan los valores predeterminados. `--numbers` se mantiene sin cambios y no puede combinarse con `--review`.

## Ejecutar las pruebas

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

# Los 14 DOCX de tests/CRF-sinteticas; no muestra su texto en terminal.
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
