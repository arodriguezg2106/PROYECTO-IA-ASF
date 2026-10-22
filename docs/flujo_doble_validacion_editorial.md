# Doble validación y banco editorial pareado

El flujo convierte las referencias aprobadas en evidencia de evaluación con dos
revisiones independientes. Todos los libros y JSON con texto institucional se
guardan bajo `results/`, que está excluido de Git. Los nombres de revisores y
adjudicadores no se incorporan a los JSON.

## 1. Segunda revisión ciega

Generar el paquete desde la validación primaria y el corpus local:

```powershell
python scripts/editorial_reference_workflow.py prepare
```

El resultado contiene 31 referencias en
`results/editorial_second_review/segunda_revision_ciega.xlsx`. El segundo
revisor debe completar las cinco decisiones cuando la primera respuesta sea
`Sí`. Si responde `No` o `No puedo determinarlo`, puede dejar las decisiones 2
a 5 vacías siempre que incluya una explicación. Esos campos se importan como
`null`, no como decisiones inventadas. No debe editar las columnas de evidencia.
El libro omite documento, resultado, decisión y explicación del primer revisor.

Una vez contestado, importarlo con el manifiesto generado junto al paquete:

```powershell
python scripts/editorial_reference_workflow.py import-second `
  results/editorial_second_review/segunda_revision_ciega_contestada.xlsx `
  --manifest results/editorial_second_review/manifest.json `
  --output results/editorial_second_review/segunda_revision.json
```

La importación rechaza columnas, filas o evidencia fija alteradas. Exige las
cinco respuestas cuando la primera es `Sí`; una respuesta `No` o `No puedo
determinarlo` puede dejar las otras cuatro vacías si incluye explicación. El
JSON importado se considera confidencial
porque la explicación libre puede reproducir información institucional, aunque
se omita el nombre del revisor; por ello también permanece bajo `results/`.

## 2. Adjudicación de desacuerdos

El libro de adjudicación incluye exclusivamente los casos donde difieren las
cinco decisiones:

```powershell
python scripts/editorial_reference_workflow.py prepare-adjudication `
  --second results/editorial_second_review/segunda_revision.json `
  --workbook results/editorial_adjudication/adjudicacion.xlsx `
  --manifest results/editorial_adjudication/manifest.json
```

Después de completar decisiones finales y una justificación obligatoria:

```powershell
python scripts/editorial_reference_workflow.py import-adjudication `
  results/editorial_adjudication/adjudicacion_contestada.xlsx `
  --manifest results/editorial_adjudication/manifest.json `
  --corpus results/editorial_revision_corpus/corpus.json `
  --output results/editorial_adjudication/adjudicacion.json
```

La justificación de adjudicación se trata como texto potencialmente sensible y
nunca se considera apta para control de versiones.

## 3. Bancos pareados

```powershell
python scripts/editorial_reference_workflow.py build-banks `
  --second results/editorial_second_review/segunda_revision.json `
  --adjudication results/editorial_adjudication/adjudicacion.json `
  --real-output results/editorial_revision_validation/paired_evaluation_bank.json `
  --synthetic-output tests/data/editorial_paired_synthetic.json
```

El banco real usa el esquema `editorial-paired-evaluation-bank-1.0` y expande
cada par en un caso `before` que espera hallazgo y uno `after` que no lo espera.
Cada caso contiene `case_id`, `fragment`, `expected_finding`,
`acceptable_spans`, `source_pair_id`, `variant` y `category`. El banco omite
nombres de archivo e identificadores del corpus, pero contiene texto real y no
debe salir de `results/`.

El banco conserva todas las categorías adjudicadas. Una evaluación de la regla
contextual debe puntuar únicamente `Ortografía o gramática` y `Coherencia o
claridad`; cifras, formato y criterio técnico se reportan fuera del denominador
salvo que el proveedor declare explícitamente soporte para ellas.

Los pares con texto faltante, idéntico, rechazado o indeterminado se excluyen
con una razón explícita. El banco definitivo del 22 de octubre contiene 16
pares y 32 ejemplos; documenta 15 exclusiones. Su distribución es 8 pares de
coherencia o claridad, 5 de ortografía o gramática, 1 de cifras o datos y 2 de
criterio técnico o normativo. El banco sintético conserva solamente categoría
y estructura del conjunto final; no copia fragmentos, nombres, cifras ni
referencias del material institucional y sí puede versionarse.

No se debe generar el banco definitivo simulando respuestas. Si existe un solo
desacuerdo sin adjudicar, la construcción termina con error.
