# Auditoría focalizada del inventario

El inventario `numbers-1.3` mantiene las ocurrencias y separa `numero_de_auditoria` de `folio`. La etiqueta explícita o el encabezado inequívoco es obligatorio: la forma del número no basta. El formato original, incluidos ceros iniciales, se conserva. Estos identificadores nunca son aritméticos.

La prioridad de unidades es `explicit > column_header > row_header > table_title > table_note > previous_paragraph > none`. Una contradicción entre fuentes aplicables bloquea la normalización y produce confianza `low`; la prioridad no oculta conflictos. Las menciones narrativas sin declaración se conservan en `unit_candidates` con `applicable=false`.

Los encabezados incluyen la banda inicial posterior a rótulos fusionados, además de filas marcadas `tblHeader`. Un rótulo fusionado sólo aporta una unidad de tabla cuando contiene una expresión de unidad separada. Los encabezados requieren una única unidad, relación de fila/columna y ausencia de señales de duda para obtener `high`. Las notas y declaraciones del párrafo anterior conservan `medium`. Una unidad directamente anterior a la cifra dentro del mismo párrafo es `explicit`.

La certeza de encabezados utiliza ahora el catálogo completo de unidades, incluyendo cantidades como municipios. Si una fuente adicional contradice esa unidad, prevalece `low`. No se atribuye certeza sólo por la posición.

En PowerShell, desde la raíz del proyecto:

```powershell
$env:PYTHONPATH = "src;scripts"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\inventory_numbers.py --mode final
.\.venv\Scripts\python.exe scripts\focused_inventory_audit.py
.\.venv\Scripts\python.exe scripts\human_validation_small.py
```

El diagnóstico usa el snapshot anterior conservado en `results/auditoria_focalizada/before` y no lo sobrescribe. Sus JSON/Markdown incluyen las 70 tablas, encabezados mediante IDs y longitudes, expresiones de unidad, motivos de no herencia, el seguimiento de los 717 orígenes anteriores y de las 114 exclusiones high/medium señaladas. Los reportes contienen las copias documentales; las métricas excluyen una copia idéntica.

`results/inventario_cifras/final/tablas_cruzadas.*` incluye los cinco cruces adicionales. `results/validacion_humana_reducida/validacion_final_30.xlsx` conserva la semilla fija, 30 registros sin reemplazo y los campos de validación humana vacíos. Todos los resultados y XLSX están excluidos por `.gitignore`.

Los indicadores de elegibilidad no ejecutan operaciones ni validaciones de congruencia. `usable_for_comparison` permanece únicamente como campo legado de trazabilidad; las decisiones usan los cuatro indicadores específicos.
