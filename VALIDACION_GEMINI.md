# Validación comparativa: Gemma en Ollama Cloud y Gemini API

Actualización UTC: 2026-11-09T22:54:14.145713+00:00. Hora CDMX: 2026-11-09T16:54:14.145713-06:00.

**Conclusión:** Gemini todavía no supera todos los casos de conectividad/formato. Revisar errores exactos y corregir su causa antes de continuar; conservar Ollama en paralelo.

Prueba independiente de conectividad y formato, no aprobación editorial ni continuación de consistency-v1.

## Resumen de resultados observados

| Vía | Solicitudes enviadas | HTTP 2xx | Latencia media (s) | Tokens entrada / salida |
|---|---:|---:|---:|---|
| ollama | 4 | 4 | 0.8964 | 3357 / 207 |
| gemini | 1 | 0 | 0.9320 | N/D; no se reportaron conteos |

Los tokens desconocidos no se cuentan como cero. La media incluye respuestas fallidas con latencia observada.

**Observación de formato en revisión posterior:** ollama/C01: Clave JSON repetida: confidence; ollama/C14: Clave JSON repetida: confidence. El parser estándar conserva la última aparición; no se considera una respuesta inequívoca para interoperabilidad estricta. Esta observación no reescribe el diario original ni sus banderas iniciales.

## Integración conservada

- Ollama existente: `scripts/evaluate_ollama_cloud.py`, `CloudSession.chat`, POST `https://ollama.com/api/chat`, modelo `gemma4:31b`, cabecera `Authorization: Bearer` desde `OLLAMA_API_KEY`. Respuesta `message.content`; tokens `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count`.
- Alternativa: POST `https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent`, cabecera `x-goog-api-key` desde `GEMINI_API_KEY`; texto visible en `candidates[0].content.parts[].text` y tokens en `usageMetadata`.
- Se reutilizan el prompt CLOUD_PROMPT, el esquema y la regla actuales, sin importar dependencias externas. Mismo texto de sistema y usuario para ambos proveedores; sin generación restringida por esquema.
- Ollama: temperatura 0, semilla 20260923, think=false. Gemini: temperatura 0, misma semilla y thinkingLevel=minimal. Esto no garantiza equivalencia de servicio, plantilla interna, pesos, precisión numérica o determinismo.

## Ejecución

- Diario local: `results/gemma_endpoint_validation/20261109T225408_925194Z/result.json`. Commit: `7e3e59b6390d680865eba9b8725157a567632de2`.
- Modo: solicitudes reales sólo si hay clave. Intentos de red registrados: 5; máximo por corrida: 8.
- Claves ausentes se registran como omitidas, sin inventar HTTP 401. Sin reintentos automáticos. Los intentos inciertos no se repiten al reanudar.
- No se habilita facturación, compran créditos ni consulta administración de cuentas. Una clave no permite comprobar que el proyecto sigue en tier gratuito.

| Proveedor | Caso | Estado | HTTP observado | Latencia (s) | Tokens entrada / salida / caché |
|---|---|---|---|---:|---|
| ollama | saludo | received | 200 | 0.7492 | 25 / 3 / 0 |
| ollama | C01 | received | 200 | 1.1011 | 1112 / 99 / 0 |
| ollama | C14 | received | 200 | 1.0691 | 1109 / 99 / 640 |
| ollama | C26 | received | 200 | 0.6662 | 1111 / 6 / 640 |
| gemini | saludo | error | 500 | 0.932 | N/D / N/D / N/D |
| gemini | C01 | skipped_after_error | N/D | N/D | N/D / N/D / N/D |
| gemini | C14 | skipped_after_error | N/D | N/D | N/D / N/D / N/D |
| gemini | C26 | skipped_after_error | N/D | N/D | N/D / N/D / N/D |

## Prompts, respuestas y errores completos

### Caso saludo

Origen: `Solicitud del usuario`. Sistema SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Prompt de usuario:
````text
Hola, responde con una sola palabra: ¿funcionas?
````

**ollama**: received

````json
{
  "task_id": "ollama:saludo",
  "model": "gemma4:31b",
  "endpoint": "https://ollama.com/api/chat",
  "started_at": "2026-11-09T22:54:09.145182+00:00",
  "attempted": true,
  "payload_sha256": "0eaa26f646116bc3361a2fcf2688b804b50e95726ecdab89c8a66f18c4e7f17c",
  "status": "received",
  "http_status": 200,
  "latency_seconds": 0.7492,
  "response_text": "Sí.",
  "response_body": "{\"model\":\"gemma4:31b\",\"created_at\":\"2026-11-09T22:54:09.8182476Z\",\"message\":{\"role\":\"assistant\",\"content\":\"Sí.\"},\"done\":true,\"done_reason\":\"stop\",\"total_duration\":198010646,\"prompt_eval_count\":25,\"prompt_eval_cached_count\":0,\"eval_count\":3}\n",
  "tokens": {
    "input": 25,
    "cached_input": 0,
    "output": 3
  },
  "error": null,
  "analysis": null,
  "returned_model": "gemma4:31b"
}
````

**gemini**: error

````json
{
  "task_id": "gemini:saludo",
  "model": "gemma-4-31b-it",
  "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
  "started_at": "2026-11-09T22:54:13.037162+00:00",
  "attempted": true,
  "payload_sha256": "e8c472b145e928513e8e7dda53086fec162dbb26625b535e1fea0041ff1a1226",
  "status": "error",
  "http_status": 500,
  "latency_seconds": 0.932,
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

### Caso C01

Origen: `src/revisor_crf/editorial_consistency_bank.json#C01`. Sistema SHA-256: `3002beae50fabbddc3c63d2c7b33e87281eb293b834a1ec94b0bc6a6c27ef239`.

Prompt de usuario:
````text
{"fragment": "El comité aprobó el calendario el lunes, publicándolo el jueves siguiente.", "location": {"case_id": "C01"}, "rules": [{"rule_id": "ASF-ED-I-CONTEXT", "title": "Claridad y corrección contextual", "category": "grammar", "description": "Revisar sólo con evidencia concreta claridad, precisión, coherencia, voz pasiva innecesaria, ambigüedad y orden lógico. No marcar una oración por ser pasiva, breve, técnica o concluyente cuando su sentido sea claro; no proponer cambios meramente estilísticos sin problema identificable.", "correct_examples": ["La auditoría identificó deficiencias en los controles.", "El inmueble fue dañado durante el sismo."], "incorrect_examples": ["La dirección comunicó a la unidad que su informe contenía errores."], "source_section": "I.3-I.5", "source_page": 10, "document_code": "2IN2RE01", "document_version": "02-2025", "detection_type": "contextual", "severity": "suggestion", "autofix_allowed": false, "requires_context": true, "enabled": true}], "criteria": ["Señalar gerundios de posterioridad sólo cuando el texto explicite que la segunda acción ocurrió después; aceptar los de modo y simultaneidad.", "Señalar redundancias demostrables, omisiones de nexos necesarios y errores de concordancia.", "Señalar referencias con dos antecedentes plausibles sin inventar quién actuó; la corrección debe ser null si requiere esa información.", "Señalar contradicciones explícitas dentro del fragmento; no inferir contradicciones por falta de contexto.", "Aceptar redacción técnica, voz pasiva justificada y textos claros; no proponer cambios por mera preferencia estilística.", "Conservar cifras, porcentajes, fechas, folios, nombres y sentido; suggested_text representa el fragmento completo corregido o null."], "protected_elements": []}
````

**ollama**: received

````json
{
  "task_id": "ollama:C01",
  "model": "gemma4:31b",
  "endpoint": "https://ollama.com/api/chat",
  "started_at": "2026-11-09T22:54:09.963157+00:00",
  "attempted": true,
  "payload_sha256": "481eee30f6a6e9e9615b160b538a837f101b0af9cae1e015818f39862af4eca7",
  "status": "received",
  "http_status": 200,
  "latency_seconds": 1.1011,
  "response_text": "{\"findings\": [{\"category\": \"grammar\", \"confidence\": 1, \"message\": \"El gerundio expresa una acción posterior a la acción principal, lo cual es incorrecto gramaticalmente.\", \"problem_span\": \"publicándolo\", \"rule_id\": \"ASF-ED-I-CONTEXT\", \"severity\": \"suggestion\", \"suggested_text\": \"El comité aprobó el calendario el lunes y lo publicó el jueves siguiente.\", \"confidence\": 1}]}",
  "response_body": "{\"model\":\"gemma4:31b\",\"created_at\":\"2026-11-09T22:54:10.971248254Z\",\"message\":{\"role\":\"assistant\",\"content\":\"{\\\"findings\\\": [{\\\"category\\\": \\\"grammar\\\", \\\"confidence\\\": 1, \\\"message\\\": \\\"El gerundio expresa una acción posterior a la acción principal, lo cual es incorrecto gramaticalmente.\\\", \\\"problem_span\\\": \\\"publicándolo\\\", \\\"rule_id\\\": \\\"ASF-ED-I-CONTEXT\\\", \\\"severity\\\": \\\"suggestion\\\", \\\"suggested_text\\\": \\\"El comité aprobó el calendario el lunes y lo publicó el jueves siguiente.\\\", \\\"confidence\\\": 1}]}\"},\"done\":true,\"done_reason\":\"stop\",\"total_duration\":502657251,\"prompt_eval_count\":1112,\"prompt_eval_cached_count\":0,\"eval_count\":99}\n",
  "tokens": {
    "input": 1112,
    "cached_input": 0,
    "output": 99
  },
  "error": null,
  "analysis": {
    "json_schema_valid": true,
    "finding_count": 1,
    "expected_decision_matches": true,
    "editorial_quality_approved": false
  },
  "returned_model": "gemma4:31b"
}
````

**gemini**: skipped_after_error

````json
{
  "task_id": "gemini:C01",
  "model": "gemma-4-31b-it",
  "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
  "started_at": "2026-11-09T22:54:14.038154+00:00",
  "attempted": false,
  "payload_sha256": "7c1ccefadc49d9cad84593f03fa22f58d87fcd713a3df7fc19659bedaea3d9ef",
  "status": "skipped_after_error",
  "http_status": null,
  "latency_seconds": null,
  "response_text": null,
  "tokens": null,
  "error": "No se envió solicitud; no es una respuesta del servidor."
}
````

### Caso C14

Origen: `src/revisor_crf/editorial_consistency_bank.json#C14`. Sistema SHA-256: `3002beae50fabbddc3c63d2c7b33e87281eb293b834a1ec94b0bc6a6c27ef239`.

Prompt de usuario:
````text
{"fragment": "Las cédulas de seguimiento contiene la evidencia de las visitas.", "location": {"case_id": "C14"}, "rules": [{"rule_id": "ASF-ED-I-CONTEXT", "title": "Claridad y corrección contextual", "category": "grammar", "description": "Revisar sólo con evidencia concreta claridad, precisión, coherencia, voz pasiva innecesaria, ambigüedad y orden lógico. No marcar una oración por ser pasiva, breve, técnica o concluyente cuando su sentido sea claro; no proponer cambios meramente estilísticos sin problema identificable.", "correct_examples": ["La auditoría identificó deficiencias en los controles.", "El inmueble fue dañado durante el sismo."], "incorrect_examples": ["La dirección comunicó a la unidad que su informe contenía errores."], "source_section": "I.3-I.5", "source_page": 10, "document_code": "2IN2RE01", "document_version": "02-2025", "detection_type": "contextual", "severity": "suggestion", "autofix_allowed": false, "requires_context": true, "enabled": true}], "criteria": ["Señalar gerundios de posterioridad sólo cuando el texto explicite que la segunda acción ocurrió después; aceptar los de modo y simultaneidad.", "Señalar redundancias demostrables, omisiones de nexos necesarios y errores de concordancia.", "Señalar referencias con dos antecedentes plausibles sin inventar quién actuó; la corrección debe ser null si requiere esa información.", "Señalar contradicciones explícitas dentro del fragmento; no inferir contradicciones por falta de contexto.", "Aceptar redacción técnica, voz pasiva justificada y textos claros; no proponer cambios por mera preferencia estilística.", "Conservar cifras, porcentajes, fechas, folios, nombres y sentido; suggested_text representa el fragmento completo corregido o null."], "protected_elements": []}
````

**ollama**: received

````json
{
  "task_id": "ollama:C14",
  "model": "gemma4:31b",
  "endpoint": "https://ollama.com/api/chat",
  "started_at": "2026-11-09T22:54:11.163838+00:00",
  "attempted": true,
  "payload_sha256": "d41d6a61f0deee53cf407de30923a5d1b95c774c330c97dc23ac6bf5cfb4e8da",
  "status": "received",
  "http_status": 200,
  "latency_seconds": 1.0691,
  "response_text": "{\"findings\": [{\"category\": \"grammar\", \"confidence\": 1, \"message\": \"Error de concordancia entre el sujeto plural 'Las cédulas de seguimiento' y el verbo en singular 'contiene'.\", \"problem_span\": \"contiene\", \"rule_id\": \"ASF-ED-I-CONTEXT\", \"severity\": \"suggestion\", \"suggested_text\": \"Las cédulas de seguimiento contienen la evidencia de las visitas.\", \"confidence\": 1}]}",
  "response_body": "{\"model\":\"gemma4:31b\",\"created_at\":\"2026-11-09T22:54:12.105150262Z\",\"message\":{\"role\":\"assistant\",\"content\":\"{\\\"findings\\\": [{\\\"category\\\": \\\"grammar\\\", \\\"confidence\\\": 1, \\\"message\\\": \\\"Error de concordancia entre el sujeto plural 'Las cédulas de seguimiento' y el verbo en singular 'contiene'.\\\", \\\"problem_span\\\": \\\"contiene\\\", \\\"rule_id\\\": \\\"ASF-ED-I-CONTEXT\\\", \\\"severity\\\": \\\"suggestion\\\", \\\"suggested_text\\\": \\\"Las cédulas de seguimiento contienen la evidencia de las visitas.\\\", \\\"confidence\\\": 1}]}\"},\"done\":true,\"done_reason\":\"stop\",\"total_duration\":521853437,\"prompt_eval_count\":1109,\"prompt_eval_cached_count\":640,\"eval_count\":99}\n",
  "tokens": {
    "input": 1109,
    "cached_input": 640,
    "output": 99
  },
  "error": null,
  "analysis": {
    "json_schema_valid": true,
    "finding_count": 1,
    "expected_decision_matches": true,
    "editorial_quality_approved": false
  },
  "returned_model": "gemma4:31b"
}
````

**gemini**: skipped_after_error

````json
{
  "task_id": "gemini:C14",
  "model": "gemma-4-31b-it",
  "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
  "started_at": "2026-11-09T22:54:14.073227+00:00",
  "attempted": false,
  "payload_sha256": "c6e3df135c57ec878c7f277b9de4cce1c1eb51027e4556265848e8d849a5a4c2",
  "status": "skipped_after_error",
  "http_status": null,
  "latency_seconds": null,
  "response_text": null,
  "tokens": null,
  "error": "No se envió solicitud; no es una respuesta del servidor."
}
````

### Caso C26

Origen: `src/revisor_crf/editorial_consistency_bank.json#C26`. Sistema SHA-256: `3002beae50fabbddc3c63d2c7b33e87281eb293b834a1ec94b0bc6a6c27ef239`.

Prompt de usuario:
````text
{"fragment": "El listado de observaciones contiene las referencias necesarias para localizar cada evidencia.", "location": {"case_id": "C26"}, "rules": [{"rule_id": "ASF-ED-I-CONTEXT", "title": "Claridad y corrección contextual", "category": "grammar", "description": "Revisar sólo con evidencia concreta claridad, precisión, coherencia, voz pasiva innecesaria, ambigüedad y orden lógico. No marcar una oración por ser pasiva, breve, técnica o concluyente cuando su sentido sea claro; no proponer cambios meramente estilísticos sin problema identificable.", "correct_examples": ["La auditoría identificó deficiencias en los controles.", "El inmueble fue dañado durante el sismo."], "incorrect_examples": ["La dirección comunicó a la unidad que su informe contenía errores."], "source_section": "I.3-I.5", "source_page": 10, "document_code": "2IN2RE01", "document_version": "02-2025", "detection_type": "contextual", "severity": "suggestion", "autofix_allowed": false, "requires_context": true, "enabled": true}], "criteria": ["Señalar gerundios de posterioridad sólo cuando el texto explicite que la segunda acción ocurrió después; aceptar los de modo y simultaneidad.", "Señalar redundancias demostrables, omisiones de nexos necesarios y errores de concordancia.", "Señalar referencias con dos antecedentes plausibles sin inventar quién actuó; la corrección debe ser null si requiere esa información.", "Señalar contradicciones explícitas dentro del fragmento; no inferir contradicciones por falta de contexto.", "Aceptar redacción técnica, voz pasiva justificada y textos claros; no proponer cambios por mera preferencia estilística.", "Conservar cifras, porcentajes, fechas, folios, nombres y sentido; suggested_text representa el fragmento completo corregido o null."], "protected_elements": []}
````

**ollama**: received

````json
{
  "task_id": "ollama:C26",
  "model": "gemma4:31b",
  "endpoint": "https://ollama.com/api/chat",
  "started_at": "2026-11-09T22:54:12.300052+00:00",
  "attempted": true,
  "payload_sha256": "158a5256a452374441417d0956b42e860896bf3c6b48aacd66a8afb68758a21b",
  "status": "received",
  "http_status": 200,
  "latency_seconds": 0.6662,
  "response_text": "{\"findings\": []}",
  "response_body": "{\"model\":\"gemma4:31b\",\"created_at\":\"2026-11-09T22:54:12.859134803Z\",\"message\":{\"role\":\"assistant\",\"content\":\"{\\\"findings\\\": []}\"},\"done\":true,\"done_reason\":\"stop\",\"total_duration\":205892363,\"prompt_eval_count\":1111,\"prompt_eval_cached_count\":640,\"eval_count\":6}\n",
  "tokens": {
    "input": 1111,
    "cached_input": 640,
    "output": 6
  },
  "error": null,
  "analysis": {
    "json_schema_valid": true,
    "finding_count": 0,
    "expected_decision_matches": true,
    "editorial_quality_approved": false
  },
  "returned_model": "gemma4:31b"
}
````

**gemini**: skipped_after_error

````json
{
  "task_id": "gemini:C26",
  "model": "gemma-4-31b-it",
  "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent",
  "started_at": "2026-11-09T22:54:14.110040+00:00",
  "attempted": false,
  "payload_sha256": "adff4bc95a0309aedba7717091573e1018aae0fbc2bc7f5980369998aa019d1e",
  "status": "skipped_after_error",
  "http_status": null,
  "latency_seconds": null,
  "response_text": null,
  "tokens": null,
  "error": "No se envió solicitud; no es una respuesta del servidor."
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

Estimación Ollama sin descuento para 4 respuestas con conteos: USD 0.00055278; solicitudes sin conteos quedan fuera de la estimación.

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

## Dictamen de la corrida del 9 de noviembre de 2026

- Ollama: cuatro respuestas HTTP 200; saludo ?S?.?, detecci?n de gerundio posterior y concordancia verbal, y ausencia de hallazgo en el control correcto. Las tres decisiones editoriales coinciden con las etiquetas de estos ejemplos; esta muestra no estima calidad general.
- Latencia media Ollama: 0.8964 segundos. Tokens reportados: 3,357 de entrada (1,280 en cach?, incluidos en la entrada) y 207 de salida. Estimaci?n a tarifas publicadas: USD 0.00055278 sin descuento de cach?; USD 0.00043758 aplicando la tarifa de cach?. No se verific? un cargo ni el saldo de la cuenta.
- Las solicitudes se hicieron alrededor de las 16:54 CDMX, antes del corte de las 19:40 indicado por el usuario. No demuestran que Ollama vaya a seguir disponible gratuitamente despu?s de ese corte.
- Gemini: una solicitud de texto con HTTP 500 INTERNAL en 0.932 segundos. Error completo: `{"error":{"code":500,"message":"Internal error encountered.","status":"INTERNAL"}}`. No hubo texto ni conteos de tokens. Se omitieron tres solicitudes al detener el proveedor; no son fallos observados de esos tres prompts.
- No se observaron 401/403, 429 ni rechazos por cr?ditos. El 500 no demuestra una llave incorrecta, cuota agotada o disponibilidad general del modelo; la causa no qued? aislada. El saludo inclu?a generationConfig (semilla, l?mite y thinkingLevel=minimal); una prueba futura m?nima deber?a separar esos par?metros del acceso b?sico. No se realizaron reintentos.
- Ollama/C01 repiti? `confidence` dentro del mismo objeto. La lectura est?ndar inicial lo acept?; la revisi?n estricta posterior lo se?ala. Se a?adi? una prueba que impide aceptar claves JSON duplicadas en futuras corridas.
- El an?lisis actual no env?a im?genes; no se prob? el incidente multimodal en esta cuenta.

**Recomendaci?n:** no migrar todav?a el an?lisis a Gemini como ?nico proveedor. Conservar Ollama en paralelo, sin asumir uso gratuito tras el corte. Resolver primero el 500 mediante un diagn?stico m?nimo y acotado, y s?lo despu?s validar los tres casos editoriales en Gemini. No activar facturaci?n ni sustituir silenciosamente el modelo.

Esta revisi?n se gener? localmente sin nuevas inferencias. Se preservaron result.json y report.md originales; review.md contiene esta lectura posterior y sus fuentes quedan en review.json.

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

## Diagn?stico preparado a partir del c?digo Get code

El ejemplo aportado por el usuario usa `generate_content_stream`, el mismo
modelo `gemma-4-31b-it`, thinking_level HIGH y una herramienta Google Search;
tambi?n incluye un objeto vac?o de configuraci?n de transcripci?n de audio.
Es c?digo exportado, no evidencia de ejecuci?n de ese script con la clave REST.

Se a?adi? el modo `-GeminiStreaming`, implementado s?lo con biblioteca est?ndar:
POST a `:streamGenerateContent?alt=sse`, lectura de eventos SSE, uni?n de texto
visible y conservaci?n de los ?ltimos conteos acumulados de tokens (sin sumarlos).
El diagn?stico usa como m?ximo dos solicitudes nuevas y distintas: contents
m?nimo, y HIGH con l?mite de 2048 tokens. No consulta Ollama ni modifica sus pruebas.
Google Search y transcripci?n de audio quedan fuera porque no son requisitos
del an?lisis de texto; esto no reproduce exactamente toda la configuraci?n exportada.

La ruta nueva est? pendiente de prueba remota. Este cambio no demuestra que el
streaming sea la causa del 500 ni que lo resuelva. Sus resultados se guardar?n
en `VALIDACION_GEMINI_STREAMING.md` y en otro diario local, preservando las
corridas anteriores. No se instal? google-genai ni se habilit? facturaci?n.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts
alidate_gemma_endpoints.ps1 -GeminiStreaming
```

## Revisi?n del streaming del 9 de noviembre

La llamada abri? HTTP 200 y recibi? cinco eventos de procesamiento antes de un
sexto evento con error 500 INTERNAL. No lleg? texto de respuesta final. Dur?
34.1233 segundos. Un HTTP 200 de apertura no equivale a una generaci?n exitosa.

Los ?ltimos conteos acumulados recibidos fueron 13 tokens de entrada,
109 de razonamiento y 122 totales. Son conteos parciales: no se suman los valores
de cada evento y no se infiere un conteo final de salida ni un cargo.

La variante HIGH no se envi?. El controlador inicial distingu?a el 500 HTTP,
pero deten?a la corrida ante el 500 interno de un stream HTTP 200; se corrigi?
ese manejo y se agreg? una prueba. El parser tambi?n conservaba s?lo el evento
de error y descartaba del resumen los conteos anteriores; ahora los retiene.
El diario y el informe originales se conservan intactos, incluidas sus banderas
iniciales. Esta nota es una revisi?n posterior basada en la respuesta guardada.

Esto confirma que la API inici? procesamiento del modelo para el proyecto en
esa sesi?n; la falla se produjo durante la generaci?n. No demuestra que el
servicio est? inutilizable para toda configuraci?n ni que el Playground y la
API usen id?ntica ruta. No justifica habilitar facturaci?n ni cambiar la llave.

Se prepar? un modo de una sola solicitud para comprobar ?nicamente la variante
HIGH pendiente, sin repetir el caso m?nimo ni consultar Ollama:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts
alidate_gemma_endpoints.ps1 -GeminiStreamHighOnly
```

Ese modo usa HIGH con l?mite de 2048 tokens, sin b?squeda web ni audio. Permanece
pendiente de ejecuci?n remota. Esta revisi?n no realiz? nuevas inferencias.

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

**Conclusi?n:** Ollama respondi? en los cuatro casos; Gemini API no qued? validada: se observaron errores 500 y un 503 que declara alta demanda. Mantener la integraci?n en paralelo y pausar nuevas inferencias por ahora.
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
