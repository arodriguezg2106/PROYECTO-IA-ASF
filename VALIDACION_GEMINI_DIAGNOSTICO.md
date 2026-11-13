# Validación comparativa: Gemma en Ollama Cloud y Gemini API

Actualización UTC: 2026-11-09T23:03:58.341549+00:00. Hora CDMX: 2026-11-09T17:03:58.341549-06:00.

**Conclusión:** El diagnóstico mínimo no confirmó acceso funcional a Gemini. Conservar el error observado; no habilitar facturación ni cambiar de modelo automáticamente.

Prueba independiente de conectividad y formato, no aprobación editorial ni continuación de consistency-v1.

## Resumen de resultados observados

| Vía | Solicitudes enviadas | HTTP 2xx | Latencia media (s) | Tokens entrada / salida |
|---|---:|---:|---:|---|
| gemini | 1 | 0 | 31.2995 | N/D; no se reportaron conteos |

Los tokens desconocidos no se cuentan como cero. La media incluye respuestas fallidas con latencia observada.

## Integración conservada

- Ollama existente: `scripts/evaluate_ollama_cloud.py`, `CloudSession.chat`, POST `https://ollama.com/api/chat`, modelo `gemma4:31b`, cabecera `Authorization: Bearer` desde `OLLAMA_API_KEY`. Respuesta `message.content`; tokens `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count`.
- Alternativa: POST `https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent`, cabecera `x-goog-api-key` desde `GEMINI_API_KEY`; texto visible en `candidates[0].content.parts[].text` y tokens en `usageMetadata`.
- Se reutilizan el prompt CLOUD_PROMPT, el esquema y la regla actuales, sin importar dependencias externas. Mismo texto de sistema y usuario para ambos proveedores; sin generación restringida por esquema.
- Diagnóstico mínimo: sólo contents con el saludo original; sin generationConfig, systemInstruction, semilla, límite de salida ni configuración de razonamiento. No consulta Ollama ni mide calidad editorial.

## Ejecución

- Diario local: `results/gemma_endpoint_validation/20261109T230326_639010Z/result.json`. Commit: `7e3e59b6390d680865eba9b8725157a567632de2`.
- Modo: solicitudes reales sólo si hay clave. Intentos de red registrados: 1; máximo por corrida: 1.
- Claves ausentes se registran como omitidas, sin inventar HTTP 401. Sin reintentos automáticos. Los intentos inciertos no se repiten al reanudar.
- No se habilita facturación, compran créditos ni consulta administración de cuentas. Una clave no permite comprobar que el proyecto sigue en tier gratuito.

| Proveedor | Caso | Estado | HTTP observado | Latencia (s) | Tokens entrada / salida / caché |
|---|---|---|---|---:|---|
| gemini | saludo_minimo | error | 500 | 31.2995 | N/D / N/D / N/D |

## Prompts, respuestas y errores completos

### Caso saludo_minimo

Origen: `Solicitud del usuario`. Sistema SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Prompt de usuario:
````text
Hola, responde con una sola palabra: ¿funcionas?
````

**gemini**: error

````json
{
  "task_id": "gemini:saludo_minimo",
  "model": "gemma-4-31b-it",
  "request_mode": "minimal",
  "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
  "started_at": "2026-11-09T23:03:26.941077+00:00",
  "attempted": true,
  "payload_sha256": "4331819b230b225d7d62e9588e1c5c98ae552ba2d7e3f71d88edac048d08c9a5",
  "status": "error",
  "http_status": 500,
  "latency_seconds": 31.2995,
  "response_text": null,
  "response_body": "{\n  \"error\": {\n    \"code\": 500,\n    \"message\": \"Internal error encountered.\",\n    \"status\": \"INTERNAL\"\n  }\n}\n",
  "tokens": null,
  "error": {
    "type": "HTTPError",
    "message": "HTTP Error 500: Internal Server Error",
    "reason": "Internal Server Error",
    "body": "{\n  \"error\": {\n    \"code\": 500,\n    \"message\": \"Internal error encountered.\",\n    \"status\": \"INTERNAL\"\n  }\n}\n",
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
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_gemma_endpoints.ps1
```

Pegar la clave únicamente en el aviso oculto de la consola. Enter vacío omite Ollama; no pegar claves en el chat, código ni comandos. El ayudante restaura las variables del proceso al finalizar y no usa setx ni archivos .env. Para sólo Gemini añadir -GeminiOnly; para imagen sintética opcional añadir -IncludeImage.

El script Python acepta --dry-run (sin red), --providers gemini o --resume RUTA_AL_DIARIO. Cada ejecución nueva guarda otro directorio; reanudar no repite respuestas fallidas, omitidas o inciertas. Este reporte se actualiza con la última corrida; cada corrida guarda también su propio report.md y result.json.

## Seguimiento: diagn?stico m?nimo del 9 de noviembre

Se encontraron dos ejecuciones manuales de una solicitud cada una al mismo
modelo `gemma-4-31b-it`, con s?lo `contents`: sin instrucciones de sistema,
im?genes, semilla, configuraci?n de razonamiento ni otros par?metros de generaci?n.

| Inicio UTC | HTTP | Latencia (s) | Texto / tokens |
|---|---:|---:|---|
| 2026-11-09T23:02:58.500454+00:00 | 500 | 1.0377 | Sin texto; tokens no reportados |
| 2026-11-09T23:03:26.941077+00:00 | 500 | 31.2995 | Sin texto; tokens no reportados |

Ambas devolvieron el mismo error: `500 INTERNAL`, `Internal error encountered.`
Sumadas a la prueba comparativa anterior, se observaron tres solicitudes de
Gemini con HTTP 500. No son reintentos autom?ticos: se conservaron tres diarios
independientes y este seguimiento no envi? solicitudes adicionales.

El fallo persiste al retirar los par?metros: no puede atribuirse ?nicamente a
la configuraci?n de generaci?n de la primera solicitud. No se observaron
401/403 ni 429, pero esto tampoco certifica la validez de la clave, permisos,
saldo o cuota. No se ha demostrado una ca?da general del servicio ni una causa
exclusiva. No hay evidencia que justifique habilitar facturaci?n como soluci?n.

**Dictamen:** alternativa Gemini a?n no validada; pausar nuevas solicitudes por
ahora. Como siguiente comprobaci?n de acceso, revisar el modelo exacto en Google
AI Studio y su disponibilidad para el proyecto antes de otra inferencia acotada.
Conservar Ollama en paralelo; su ?xito previo al corte no acredita gratuidad
posterior. El trabajo local del evaluador y el banco puede continuar sin API.

Las claves permanecen fuera de los reportes. Evidencia local:
`results/gemma_endpoint_validation/diagnostic_review.json` y los diarios indicados.

## Prueba manual en Google AI Studio aportada por el usuario

La captura compartida muestra el modelo **Gemma 4 31B IT** con identificador
`gemma-4-31b-it`. Ante ?hola?, la interfaz devuelve ??Hola! ?En qu? puedo ayudarte hoy??.
Esto confirma una respuesta visible en el Playground; no demuestra todav?a una
llamada exitosa mediante la clave y el proyecto usados por el script REST.

La configuraci?n visible tiene temperatura 1 y Thinking level High. Tambi?n
aparece Grounding with Google Search en la interfaz; no se verific? si se
utiliz? en esa respuesta ni qu? cuerpo o credenciales envi? el Playground.
Las llamadas REST anteriores emplearon configuraci?n expl?cita diferente y,
despu?s, un cuerpo m?nimo sin generationConfig; ambas v?as devolvieron 500.

El siguiente dato requerido es el ejemplo generado por **Get code**, incluyendo
modelo, contents y configuraci?n, sin claves ni valores de credenciales. Se
comparar? con el request REST antes de preparar otra prueba acotada. No se
concluye una ca?da general del modelo ni se habilita facturaci?n. La migraci?n
por API permanece pendiente de validaci?n.
