
# Aprendizaje supervisado para priorización editorial

El mecanismo de aprendizaje no sustituye las reglas ASF ni confirma hallazgos. Su única salida permitida será una probabilidad experimental para ordenar la revisión humana.

## Flujo

1. Ejecutar la revisión editorial y abrir el HTML.
2. Decidir cada ocurrencia editorial como `confirmed`, `rejected`, `not_evaluable`, `audit_team_review` o `pending`.
3. Descargar el archivo de decisiones desde el HTML.
4. Conservar juntos el reporte JSON y sus decisiones.
5. Construir el dataset anonimizado.

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/build_editorial_learning_dataset.py `
  --reports .\results\reportes `
  --decisions .\results\decisiones `
  --output .\results\aprendizaje\dataset.json
```

## Etiquetas

| Decisión humana      | Uso en aprendizaje |
| --------------------- | ------------------ |
| `confirmed`         | `valid`          |
| `rejected`          | `false_positive` |
| `pending`           | excluida           |
| `not_evaluable`     | excluida           |
| `audit_team_review` | excluida           |

Las decisiones ambiguas no se fuerzan a una clase. El comentario humano sólo se registra como presencia o ausencia; su contenido no se incorpora al dataset.

## Privacidad y separación

- No se guarda texto documental original ni texto redactado.
- Sólo se conservan rasgos agregados: longitudes, conteos, proporción de mayúsculas, puntuación y tipos de elementos protegidos, nunca sus valores.
- El SHA-256 documental se usa exclusivamente como identificador de grupo.
- La asignación es determinista: 70% entrenamiento, 15% calibración y 15% prueba.
- Todas las ocurrencias del mismo DOCX quedan en la misma partición.
- El dataset declara `contains_raw_document_text: false`.

Antes de entrenar se deberá revisar una muestra del texto anonimizado, comprobar el equilibrio de etiquetas y asegurar que las tres particiones contengan suficientes documentos y reglas.

El constructor marca `training_readiness.ready` únicamente cuando existen al menos 300 decisiones utilizables, 30 documentos, 50 ejemplos de cada etiqueta y registros en las tres particiones. Cumplir esos mínimos permite iniciar un experimento; no equivale a aprobar el modelo.

## Restricciones del futuro modelo

La interfaz `FindingPrioritizer` sólo admite probabilidades entre 0 y 1. `apply_priorities` añade `ml_priority` a una copia del hallazgo y no permite cambiar severidad, mensaje, propuesta ni estado de evaluación. Toda puntuación permanece `experimental` y `requires_human_review`.
