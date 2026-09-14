# Validación para una sola persona

El trabajo principal se concentra en pruebas sintéticas reproducibles. La revisión humana se limita a 30 registros seleccionados después de aplicar la política de confianza. No se implementan comparaciones, sumas ni validaciones de corrección financiera.

## Banco sintético

`tests/data/numeric_cases.json` define 28 casos antes de ejecutar el extractor: tipo, Decimal, unidad, multiplicador, normalizado, confianza y elegibilidad esperados. Incluye monedas/escalas, porcentajes, años, fechas, artículos, fracciones legales arábigas y romanas, folios, auditorías y cantidades. Incluye encabezados, títulos y notas, ausencia de unidad, separadores, signos, paréntesis y distintas precisiones decimales.

La precisión declarada se conserva mediante Decimal, incluidos ceros finales. Los casos con 0, 1, 2, 3 y 4 decimales prueban representaciones con distintos niveles de precisión; no se infiere el método de redondeo original ni se aplican tolerancias o redondeos nuevos.

`scripts/synthetic_validation_bank.py` define además cinco documentos y sus expectativas independientes:

1. `cifras_correctas.docx`: valores sintéticos de referencia con unidad explícita; el nombre no implica una validación contable.
2. `cifras_ambiguas.docx`: cantidades sin unidad, posible año e intervalo sin contexto.
3. `tablas.docx`: unidad en columna, fila, título y nota posterior.
4. `revisiones.docx`: sustitución de una cifra, preservando ambas versiones y analizando final.
5. `no_importes.docx`: año, fecha, artículo, fracción legal, folio, auditoría y personas.

Las pruebas generan sus DOCX en `.pytest_tmp/`, sin utilizar los archivos del lote CRF. También se entrega una copia generada en `data/synthetic_validation_bank/`, excluida de Git.

## Política de confianza

| Confianza | Condición | usable_for_comparison |
|---|---|---|
| high | Tipo de magnitud claro, valor normalizable y unidad explícita o encabezado inequívoco; sin ambigüedades | true |
| medium | Tipo identificado pero referencia no comparable, o unidad indirecta de título/nota/texto cercano | false |
| low | Ambigüedad, unidad desconocida, encabezado dudoso, revisión desconocida o tipo no identificado | false |

Años, fechas, artículos, fracciones legales, folios y números de auditoría nunca son high. Su identificación clara no los convierte en magnitudes comparables. Los registros high son candidatos para una futura comparación: no se ha comprobado que dos registros tengan la misma identidad o significado.

Los ambiguos conservan `classification=ambiguous`, `confidence=low`, `usable_for_comparison=false` y una explicación `reason`. `tipo` conserva la hipótesis léxica previa por compatibilidad; **no debe usarse sola para decidir elegibilidad**. Los valores normalizados de registros ambiguos son provisionales; no se fuerzan decisiones ni se utilizan automáticamente. `no_clasificada` permite distinguir los no identificados dentro de low.

`origin_unit` ofrece los valores `explicit`, `column_header`, `row_header`, `table_caption`, `nearby_text` y `none`. El encabezado se considera inequívoco sólo con una unidad reconocida, sin números ni texto excesivo y sin conflicto entre fila y columna. Títulos y notas breves aportan evidencia indirecta (medium), nunca high por sí solos. La detección no reconstruye la semántica completa de tablas complejas.

## Ejecución en Windows

Desde la raíz del proyecto, con las dependencias locales ya disponibles:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\synthetic_validation_bank.py
.\.venv\Scripts\python.exe scripts\inventory_numbers.py --mode final
.\.venv\Scripts\python.exe scripts\human_validation_small.py
```

El XLSX requiere `openpyxl`, declarado en `requirements-reporting.txt`. No se consultan servicios externos. `scripts/human_validation_package.py` se conserva como entrada compatible, pero ahora llama exclusivamente al generador de 30 registros.

## Revisión humana: 30 registros

Se usa la semilla `20260909`. Se reservan cinco registros de tablas; después se seleccionan diez high, diez ambiguos clasificados y cinco no clasificados, sin reemplazo. Los grupos son excluyentes por ID, aunque las propiedades pueden solaparse: por ejemplo, un registro del grupo tablas puede ser high, y uno del grupo high puede estar en una tabla. La selección favorece documentos todavía no representados y es reproducible para el mismo inventario.

El archivo vigente es `results/validacion_humana_reducida/validacion_final_30.xlsx`. Incluye clasificación, tipo candidato, unidad, valor normalizado, confianza, contexto reducido y cinco campos humanos en blanco:

- clasificación correcta: sí/no;
- unidad correcta: sí/no;
- valor correcto: sí/no;
- puede compararse: sí/no;
- observaciones.

Cuando falte evidencia o un campo no aplique, se deja vacío y se explica en observaciones. No se solicitan decisiones forzadas. El manifiesto registra los hashes de los inventarios, IDs y cuotas. El contexto usa indicios léxicos, no párrafos completos. El XLSX y los resultados están excluidos de Git. El archivo antiguo de 200 registros es un artefacto histórico; no se regenera ni forma parte del flujo vigente.

## Reporte de cobertura

`results/inventario_cifras/final/cobertura_confianza.md` y `.json` registran totales, niveles, utilizables, excluidos, distribución por tipo/origen y verificación por documento.

La cobertura del lector mide conservación de texto XML mediante `text_all`, ubicaciones y hashes, incluso cuando final excluye una revisión o la política excluye una cifra. No mide exactitud semántica del inventario. El lote actual conserva 5,922 párrafos, 4,840 con texto, con cobertura de texto del 100 %. La incorporación de fracciones legales puede aumentar el conteo de registros numéricos sin cambiar ese denominador XML.
