# Revisión semántica local

## Garantías

La capa semántica recibe fragmentos candidatos producidos por el lector y nunca abre ni modifica el DOCX. Ollama propone una relación estructurada; el motor acepta una alerta `NUM-CROSS-ML-001` únicamente cuando dos pasos independientes coinciden con confianza mínima de 0.95, las unidades y vistas son compatibles, la relación es uno a uno y toda evidencia aparece literalmente en la entrada. Los cálculos continúan usando `Decimal` en el motor determinístico.

Una relación ambigua se muestra únicamente en el HTML. Una caída, tiempo agotado o respuesta inválida del modelo agrega una advertencia y conserva la revisión determinística. Solo las alertas aceptadas se convierten en comentarios de Word.

## Configuración local

1. Instalar Ollama mediante el mecanismo aprobado por TI.
2. Descargar o importar sin internet el modelo autorizado y comprobar su digest.
3. Copiar `semantic-config.example.toml` y mantener `profile="local"`. Este perfil rechaza destinos que no sean `localhost` o una dirección loopback.
4. Ejecutar:

```powershell
.\.venv\Scripts\python.exe -m revisor_crf documento.docx --review --semantic-review --semantic-config .\semantic-config.example.toml -o .\results\revision.json --html .\results\revision.html --commented-docx .\results\revision.docx
```

La configuración local predeterminada usa `qwen3.5:4b`, lotes de cuatro casos y `results/semantic_cache.sqlite3`. El modelo alternativo evaluado es `qwen3:4b-instruct`. El archivo JSON registra modelo, digest, versiones de prompt/esquema, tiempos, caché, respuestas inválidas y estado final.

## Dataset y selección del modelo

El HTML exporta `review-decisions-1.1`, que incluye alertas y sugerencias semánticas. Después de la revisión y aprobación humana:

```powershell
.\.venv\Scripts\python.exe scripts\semantic_dataset.py --report .\results\revision.json --decisions .\results\decisiones.json --output .\results\semantic_eval\dataset.jsonl --reviewer "revisor-01" --approved-by "responsable-01"

.\.venv\Scripts\python.exe scripts\evaluate_semantic_models.py .\results\semantic_eval\dataset.jsonl --config .\semantic-config.example.toml --models qwen3.5:4b,qwen3:4b-instruct --output .\results\semantic_eval\model-selection.json
```

La separación 60/20/20 se deriva del SHA-256 del documento para impedir que fragmentos del mismo CRF aparezcan en conjuntos distintos. La selección exige precisión mínima de 98 %, exactitud mínima de 95 %, cero respuestas inválidas y duración total máxima de diez minutos sobre validación. Si ningún modelo cumple, el resultado queda sin modelo aprobado.

Los datasets y documentos permanecen bajo `results/`, excluidos de Git. No existe aprendizaje automático en línea: una decisión solo entra al dataset cuando se proporcionan revisor y aprobador.

## Servicio institucional

El servicio recibe únicamente casos semánticos y serializa las llamadas al modelo mediante una cola acotada. Requiere un token en una variable de entorno; si escucha fuera de loopback también exige certificado y llave TLS.

```powershell
$env:REVISOR_CRF_SEMANTIC_TOKEN = "token-administrado-por-ti"
.\.venv\Scripts\python.exe -m revisor_crf.semantic_service --config .\semantic-config.example.toml --host 0.0.0.0 --port 8765 --certfile .\certs\servidor.crt --keyfile .\certs\servidor.key
```

Los clientes usan `semantic-config.institutional.example.toml` y leen el token desde `REVISOR_CRF_SEMANTIC_TOKEN`. El endpoint `POST /v1/semantic-relations` valida esquema, tamaño, número de casos y autenticación. Los registros contienen hash de solicitud, cantidad de casos, fase y duración; no incluyen texto del CRF.

Antes del despliegue se debe probar en una PC Windows de referencia con 16 GB de RAM y sin GPU. El criterio operativo es p95 menor o igual a diez minutos por CRF y equivalencia funcional entre ejecución local e institucional para el mismo modelo, digest, prompt y esquema.
