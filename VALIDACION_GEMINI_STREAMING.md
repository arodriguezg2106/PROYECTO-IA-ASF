# Validación comparativa: Gemma en Ollama Cloud y Gemini API

Actualización UTC: 2026-11-09T23:28:06.597200+00:00. Hora CDMX: 2026-11-09T17:28:06.597200-06:00.

**Conclusión:** El diagnóstico de streaming no confirmó acceso funcional. Conservar los errores y no atribuir el fallo a una sola causa ni aprobar la migración.

Prueba independiente de conectividad y formato, no aprobación editorial ni continuación de consistency-v1.

## Resumen de resultados observados

| Vía | Solicitudes enviadas | HTTP 2xx | Latencia media (s) | Tokens entrada / salida |
|---|---:|---:|---:|---|
| gemini | 1 | 0 | 9.1620 | N/D; no se reportaron conteos |

Los tokens desconocidos no se cuentan como cero. La media incluye respuestas fallidas con latencia observada.

## Integración conservada

- Ollama existente: `scripts/evaluate_ollama_cloud.py`, `CloudSession.chat`, POST `https://ollama.com/api/chat`, modelo `gemma4:31b`, cabecera `Authorization: Bearer` desde `OLLAMA_API_KEY`. Respuesta `message.content`; tokens `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count`.
- Alternativa: POST `https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent`, cabecera `x-goog-api-key` desde `GEMINI_API_KEY`; texto visible en `candidates[0].content.parts[].text` y tokens en `usageMetadata`.
- Se reutilizan el prompt CLOUD_PROMPT, el esquema y la regla actuales, sin importar dependencias externas. Mismo texto de sistema y usuario para ambos proveedores; sin generación restringida por esquema.
- Diagnóstico de streaming: contents mínimo y una segunda configuración HIGH con límite 2048; temperatura y semilla no se fijan. Los resultados son de transporte y no se combinan con la evaluación editorial.

## Ejecución

- Diario local: `results/gemma_endpoint_validation/20261109T232756_978455Z/result.json`. Commit: `7e3e59b6390d680865eba9b8725157a567632de2`.
- Modo: solicitudes reales sólo si hay clave. Intentos de red registrados: 1; máximo por corrida: 1.
- Claves ausentes se registran como omitidas, sin inventar HTTP 401. Sin reintentos automáticos. Los intentos inciertos no se repiten al reanudar.
- No se habilita facturación, compran créditos ni consulta administración de cuentas. Una clave no permite comprobar que el proyecto sigue en tier gratuito.

Diagnóstico de streaming: POST `https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:streamGenerateContent?alt=sse`. Configuraciones de esta corrida: saludo_stream_high. El modo HIGH tiene un máximo de 2048 tokens, límite que no aparece en el ejemplo exportado. No se incluyen Google Search ni transcripción de audio, que no forman parte del análisis editorial de texto. No es una reproducción exacta del Playground.

Cada configuración se envía como máximo una vez. Un 500 en la primera no impide comprobar la segunda configuración distinta; autenticación, cuota, créditos y transporte detienen el proveedor. Sin reintentos de la misma configuración.

| Proveedor | Caso | Estado | HTTP observado | Latencia (s) | Tokens entrada / salida / caché |
|---|---|---|---|---:|---|
| gemini | saludo_stream_high | error | 503 | 9.162 | N/D / N/D / N/D |

## Prompts, respuestas y errores completos

### Caso saludo_stream_high

Origen: `Solicitud del usuario`. Sistema SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Prompt de usuario:
````text
Hola, responde con una sola palabra: ¿funcionas?
````

**gemini**: error

````json
{
  "task_id": "gemini:saludo_stream_high",
  "model": "gemma-4-31b-it",
  "request_mode": "streaming_diagnostic",
  "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:streamGenerateContent?alt=sse",
  "started_at": "2026-11-09T23:27:57.359012+00:00",
  "attempted": true,
  "payload_sha256": "3d315ed83c48fd49b5f4d5915260f46b3e831ec143e0f6e2eccf801484e7dc44",
  "status": "error",
  "http_status": 503,
  "latency_seconds": 9.162,
  "response_text": null,
  "response_body": "{\n  \"error\": {\n    \"code\": 503,\n    \"message\": \"This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.\",\n    \"status\": \"UNAVAILABLE\"\n  }\n}\n",
  "tokens": null,
  "error": {
    "type": "HTTPError",
    "message": "HTTP Error 503: Service Unavailable",
    "reason": "Service Unavailable",
    "body": "{\n  \"error\": {\n    \"code\": 503,\n    \"message\": \"This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.\",\n    \"status\": \"UNAVAILABLE\"\n  }\n}\n",
    "diagnostic": "Error del servicio; conservar evidencia sin reintentos automáticos."
  }
}
````

## Imágenes y alcance

El flujo actual extrae texto del DOCX; no envía imágenes a los modelos. La prueba con imagen no aplica al análisis actual y no se ejecutó; puede solicitarse con --include-image.
Un 400 INVALID_ARGUMENT con imagen sólo confirma el rechazo de ese cuerpo en esa sesión. Sin una prueba remota no se confirma el incidente reportado por el usuario desde el 1 de noviembre; la documentación de Google describe capacidad de imagen en Gemma 4.

Existe un [reporte de usuarios en el foro de Google](https://discuss.ai.google.dev/t/gemma-4-on-the-gemini-api-every-request-with-an-image-returns-400-invalid-argument-since-1-nov/197258); es un antecedente, no una confirmación de que ocurra en esta cuenta.

## Interpretación de errores

- 401/403: revisar llave, permisos y restricciones; 403 también puede obedecer a región o acceso al servicio.
- 429: cuota/límite del proyecto; no prueba por sí solo qué tier tiene la cuenta.
- 400: revisar el cuerpo y mensaje, incluidos parámetros no admitidos, imágenes o clave inválida. 404: modelo/ruta/acceso.
- 402 o mensaje explícito de créditos/pago: detener Ollama. El corte del 9 de noviembre a las 19:40 CDMX es un dato del usuario; no atribuirle un error genérico sin evidencia del servicio.
- Errores TLS/DNS/timeout: HTTP no observado; no se desactiva la validación de certificados.

## Costos, cuotas y tratamiento de datos

Ollama publica USD 0.14 por millón de tokens de entrada, USD 0.40 de salida y USD 0.05 de entrada en caché. Estimación sin descuento: (entrada × 0.14 + salida × 0.40) / 1,000,000. La caché es parte de la entrada y no debe sumarse otra vez. Una estimación no es un cargo confirmado. [Tarifas oficiales](https://ollama.com/pricing).

Gemini/Gemma puede usarse sin cargo dentro de la cuota gratuita disponible; verificar el modelo y los límites del proyecto en AI Studio. No se deduce el saldo desde una respuesta exitosa. [Precios](https://ai.google.dev/gemini-api/docs/pricing), [límites por proyecto](https://ai.google.dev/gemini-api/docs/rate-limits).

En servicios gratuitos Google puede utilizar prompts y respuestas para mejorar sus productos; por eso esta corrida sólo usa textos sintéticos versionados, nunca DOCX ni párrafos institucionales. [Condiciones oficiales](https://ai.google.dev/gemini-api/terms).

Google documenta el identificador solicitado y el control de razonamiento; no se sustituye por otro modelo. [Gemma en Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api).

## Reproducción y manejo de la llave

En PowerShell, desde la raíz del repositorio:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_gemma_endpoints.ps1 -GeminiStreamHighOnly
```

Pegar la clave únicamente en el aviso oculto de la consola. Enter vacío omite Ollama; no pegar claves en el chat, código ni comandos. El ayudante restaura las variables del proceso al finalizar y no usa setx ni archivos .env. Para sólo Gemini añadir -GeminiOnly; para imagen sintética opcional añadir -IncludeImage.

El script Python acepta --dry-run (sin red), --providers gemini o --resume RUTA_AL_DIARIO. Cada ejecución nueva guarda otro directorio; reanudar no repite respuestas fallidas, omitidas o inciertas. Este reporte se actualiza con la última corrida; cada corrida guarda también su propio report.md y result.json.

## Dictamen consolidado tras la variante HIGH

La ?ltima solicitud de `gemma-4-31b-it`, con streaming y razonamiento HIGH,
devolvi? **HTTP 503 UNAVAILABLE** en **9.162 segundos**. El servicio indic?:

> This model is currently experiencing high demand.

El mensaje completo a?ade que los picos de demanda suelen ser temporales y
sugiere intentarlo m?s tarde. En esta solicitud s? hay evidencia expl?cita de
alta demanda; no se atribuyen autom?ticamente a ella todos los 500 previos.

| Prueba Gemini | HTTP | Error dentro del stream | Resultado |
|---|---:|---:|---|
| Saludo comparativo | 500 | No aplica | Sin respuesta final |
| Cuerpo m?nimo, ejecuci?n 1 | 500 | No aplica | Sin respuesta final |
| Cuerpo m?nimo, ejecuci?n 2 | 500 | No aplica | Sin respuesta final |
| Streaming m?nimo | 200 | 500 INTERNAL | Procesamiento parcial y sin respuesta final |
| Streaming HIGH | 503 | No aplica | Alta demanda declarada por el servicio |

Se registraron **cinco solicitudes reales a Gemini**, sin respuestas finales
utilizables; los casos editoriales no llegaron a ejecutarse en esa v?a. Los
cuatro casos de Ollama respondieron 200 en la corrida anterior, antes del corte
anunciado. Estos antecedentes se mantienen separados de `consistency-v1`.
La prueba manual del usuario s? mostr? una respuesta en el Playground de AI
Studio, lo que no garantiza igual disponibilidad en la ruta REST de la API.

**Conclusi?n:** Gemma 4 31B mediante Gemini API permanece **no validado para
continuar el an?lisis autom?ticamente**. La disponibilidad del servicio es un
bloqueo observado. No hay evidencia que justifique cambiar la clave o habilitar
facturaci?n para solucionar este error. No se migrar? la integraci?n de Ollama.

**Siguiente acci?n recomendada:** pausar las inferencias por ahora y continuar
con el evaluador y el banco local. Cuando la API se recupere, comprobar una
?nica solicitud controlada y despu?s los tres casos editoriales pendientes.
Mantener los l?mites del proyecto gratuito y usar textos sint?ticos. La tarifa
baja de Ollama no sustituye autorizaci?n de gasto ni prueba que siga gratuito.

Esta revisi?n s?lo ley? los diarios: cero solicitudes adicionales. Los errores
originales y las respuestas se conservan, y sus hashes est?n registrados en
`results/gemma_endpoint_validation/final_summary.json`.
