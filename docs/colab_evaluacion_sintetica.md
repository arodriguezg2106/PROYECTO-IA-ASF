# Evaluación sintética segura en Google Colab

Colab es sólo un filtro preliminar con GPU. Usa exclusivamente los casos
sintéticos versionados y no autoriza un modelo para procesar CRF reales.

## Preparación del acceso privado

1. Publique primero el commit que contiene la libreta.
2. Cree en GitHub un token fino con acceso **Contents: Read-only** únicamente al
   repositorio `PROYECTO-IA-ASF` y expiración máxima de siete días.
3. En Colab, abra **Secrets**, cree `GITHUB_TOKEN` y habilite el acceso de la
   libreta. No escriba el token en una celda, URL o salida.
4. Active una GPU en **Entorno de ejecución → Cambiar tipo de entorno de ejecución**.

La libreta obtiene el commit de `main` y descarga su archivo por la API de
GitHub. El token se elimina de memoria inmediatamente después de la descarga.
No monta Google Drive.

## Dos ejecuciones independientes

Abra `notebooks/evaluacion_sintetica_colab.ipynb` y ejecute una sesión por
modelo: primero `qwen3.5:9b` y después `gemma3:12b`.

Cada sesión registra commit, GPU, VRAM, versión de Ollama, digest, tiempos y
errores. Ejecuta tres repeticiones de las etapas de 2, 10 y 30 casos y guarda un
checkpoint después de cada etapa. Descargue el JSON final y el ZIP de
checkpoints antes de cerrar la VM.

El resultado válido debe indicar `evaluation_scope: synthetic_screening_only`,
mantener `selected_model` en `null` y sólo usar `screened_model` si pasa todos
los umbrales. Después de ambas sesiones, compare los dos JSON; no mezcle sus
resultados ni elija sólo por velocidad.

Si un modelo aprueba, obtenga su digest completo de `ollama show` y genere el
perfil local:

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts/build_ollama_profile.py `
  .\results\colab\evaluacion-qwen.json `
  --digest "sha256:<64-hex>" `
  --output .\results\colab\perfil-ollama.json
```

El perfil sintético sólo puede habilitar Ollama en `--demo`. Antes de un piloto
con documentos reales, el modelo debe repetir la compuerta completa dentro de
infraestructura institucional.

## Prohibiciones y cierre

No cargue DOCX, Excel, `results/`, `data/`, bancos reales, nombres, cifras,
folios ni fragmentos institucionales. Al terminar descargue los dos JSON y
checkpoints, verifique que no contienen texto institucional y revoque el token.

La disponibilidad de GPU de Colab no está garantizada. Ningún resultado de
Colab bloquea la demostración determinística.
