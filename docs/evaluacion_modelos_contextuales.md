# Evaluación de modelos contextuales

La IA contextual permanece experimental, se ejecuta sólo en infraestructura institucional y no modifica documentos, cifras, severidades ni reglas. El motor determinístico no depende de esta evaluación.

## Candidatos y estado

| Modelo | Estado | Condición |
|---|---|---|
| `qwen3.5:9b` | experimental | Pendiente de servidor interno y evaluación completa |
| `gemma3:12b` | experimental | Pendiente de servidor interno y evaluación completa |
| `qwen3.5:27b` | experimental condicionado | Requiere acreditar al menos 24 GB de memoria de acelerador |
| `qwen3.5:4b` | rechazado | No alcanzó los umbrales vigentes |
| `qwen3:8b` | rechazado | No alcanzó los umbrales vigentes |

El equipo de desarrollo comprobado tiene aproximadamente 16 GB de RAM y no tiene GPU NVIDIA detectada. Los candidatos 9B/12B no están instalados. Por ello, la ejecución real queda pendiente de un servidor interno adecuado; no deben descargarse para sortear esa limitación. Ese inventario puede registrarse en el preflight con `--available-models qwen3:8b,qwen3.5:4b`, que marcará los candidatos como `model_not_available_locally` sin llamar a Ollama.

## Secuencia obligatoria

Cada etapa se ejecuta tres veces, con temperatura cero, y sólo comienza si la anterior aprobó:

1. Smoke equilibrado de 2 casos.
2. Compuerta difícil de 10 casos.
3. Partición sintética final de 30 casos.
4. Banco real pareado local.

Los umbrales no cambian entre etapas: precisión ≥0.90, exhaustividad ≥0.85, exactitud ≥0.90, acuerdo ≥0.95, cero respuestas inválidas y cero propuestas que alteren elementos protegidos. Un fallo detiene las etapas restantes y ningún resultado actualiza automáticamente el registro de modelos.

El banco real predeterminado es `results/editorial_revision_validation/paired_evaluation_bank.json`. Contiene texto institucional, debe declarar `privacy.contains_raw_institutional_text: true` y permanecer fuera de Git.

## Tamizaje externo sólo con datos sintéticos

Cuando se disponga de una GPU temporal fuera de la infraestructura institucional,
se permite omitir por completo el banco real con `--synthetic-only`. Esta ruta
ejecuta sólo las compuertas 2+10+30, deja `selected_model` en `null` y puede
producir únicamente el estado `synthetic_screen_passed`. Por diseño no puede
aprobar un modelo.

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/evaluate_editorial_context.py `
  --synthetic-only `
  --models qwen3.5:9b `
  --available-models qwen3.5:9b `
  --output results/editorial_context/qwen35_9b_synthetic.json
```

La ruta guiada para Colab está en
[`docs/colab_evaluacion_sintetica.md`](colab_evaluacion_sintetica.md). No se
permite subir documentos, Excel ni bancos reales a ese servicio.

La compuerta contextual puntúa por defecto sólo los pares adjudicados como `Ortografía o gramática` o `Coherencia o claridad`. Conserva y reporta como no compatibles, fuera del denominador, las categorías de cifras, formato y criterio técnico. Ampliar la cobertura requiere declararlo de forma explícita con `--real-categories`; no se infiere de la respuesta del modelo.

## Preflight sin Ollama

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/evaluate_editorial_context.py --preflight
```

El preflight carga ambos bancos, verifica las cantidades de las compuertas y revisa el registro y las restricciones de hardware. No construye el proveedor ni contacta Ollama.

## Ejecución en el servidor institucional

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/evaluate_editorial_context.py `
  --models qwen3.5:9b,gemma3:12b `
  --repetitions 3 `
  --real-bank results/editorial_revision_validation/paired_evaluation_bank.json `
  --output results/editorial_context/staged-model-evaluation.json
```

Para `qwen3.5:27b` también debe indicarse la memoria acreditada, por ejemplo `--accelerator-memory-gb 24`. El valor es una declaración de inventario, no una detección automática.

El código de salida es `0` si todos los modelos del preflight son elegibles o si existe un modelo aprobado; `2` si hay una restricción o ningún modelo supera todas las compuertas; y `1` si los argumentos o bancos son inválidos.
