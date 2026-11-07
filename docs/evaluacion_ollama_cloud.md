# Evaluación sintética mediante Ollama Cloud

Esta herramienta permite comparar modelos descargables sin disponer de una GPU.
Es una evaluación externa independiente: no habilita Cloud en la aplicación web,
no cambia el registro de modelos y nunca aprueba un modelo para uso institucional.
Usa exclusivamente `tests/data/editorial_context_cases.json` y sus casos derivados;
no admite rutas de documentos ni bancos reales.

## Acceso y consumo

La [tarifa pública](https://ollama.com/pricing), consultada el 29 de octubre de
2026, indica que Pay as you go no tiene suscripción, pero cobra por tokens.
El precio de suscripción de $0 no garantiza inferencia gratuita. Verifique sus
créditos o promoción en [Usage](https://ollama.com/settings/usage) antes de ejecutar.
El reporte no consulta el saldo y no certifica que el consumo sea gratuito.

Obtenga una clave en [API keys](https://ollama.com/settings/keys). Para una sesión
PowerShell puede introducirla sin mostrarla ni escribirla en el historial:

```powershell
$taskOllamaSecret = Read-Host 'API key de Ollama' -AsSecureString
$taskOllamaCredential = [System.Net.NetworkCredential]::new('', $taskOllamaSecret)
$env:OLLAMA_API_KEY = $taskOllamaCredential.Password
Remove-Variable taskOllamaSecret, taskOllamaCredential
```

No envíe la clave por chat ni la agregue al repositorio. El programa usa sólo
`https://ollama.com/api/chat`, no sigue redirecciones ni reintenta solicitudes.
Se detiene ante errores HTTP, de transporte o de cuota; no compra créditos.

## Un solo caso para observar créditos

También puede ejecutar este ayudante desde PowerShell sin guardar una variable
de usuario. Pide la clave sin mostrarla, ejecuta una única solicitud y restaura
el entorno del proceso al terminar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe_ollama_credit.ps1
```

Para comparar el indicador de créditos antes y después de una única solicitud:

```powershell
$env:PYTHONPATH = 'src;scripts'
.\.venv\Scripts\python.exe scripts/evaluate_ollama_cloud.py `
  --probe --models gemma4:31b --output results/ollama_cloud/credit_probe.json
```

`--probe` fuerza un único intento con un caso sintético, sin repeticiones ni
reintentos, aunque el límite indicado sea mayor. El resultado es una observación
de consumo, no una compuerta aprobada. Con `--preflight` se prepara sin usar red.
Tras ejecutarlo, revise el indicador de Usage antes de autorizar más solicitudes.

Para pasar a la prueba equilibrada de dos casos (uno positivo y uno negativo),
con tres repeticiones por caso y un máximo de seis solicitudes a Gemma 4 31B:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe_ollama_credit.ps1 -SmokeTest
```

El ayudante vuelve a pedir la clave porque no la conserva. Guarda los resultados
en `results/ollama_cloud/gemma4_smoke.json` sin sobrescribir la prueba de consumo.
Este smoke es una comprobación preliminar; no sustituye una evaluación con casos
editoriales diversos ni permite recomendar el modelo para uso institucional.

## Preparación y primera prueba

Desde la raíz del repositorio, con las dependencias instaladas:

```powershell
$env:PYTHONPATH = 'src;scripts'
.\.venv\Scripts\python.exe scripts/evaluate_ollama_cloud.py --preflight
```

El preflight no usa red ni requiere una clave. Prepara dos casos equilibrados
repetidos tres veces para cada modelo: `gemma4:31b` y `gpt-oss:20b`, un máximo de
12 solicitudes. Tras verificar saldo y configurar la clave:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_ollama_cloud.py
```

Para limitar la primera ejecución a un modelo y seis solicitudes:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_ollama_cloud.py `
  --models gemma4:31b --max-requests 6
```

El JSON se guarda en `results/ollama_cloud/evaluation.json`. Registra métricas de
precisión, exhaustividad, exactitud, acuerdo, respuestas inválidas y sugerencias
inseguras; además, tiempos, tokens reportados, hash del banco, prompt y commit.
Los tokens de solicitudes fallidas pueden no ser reportados por el servicio.
El límite de solicitudes y el parámetro `--max-output-tokens` acotan la prueba,
pero no constituyen un límite monetario garantizado por el proveedor.

## Ampliar la evaluación

Para ambos modelos, el máximo del plan difícil es 72 solicitudes y el del plan
completo sintético es 252. Cada modelo se detiene al fallar una compuerta:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_ollama_cloud.py `
  --through final --max-requests 252
```

Se conservan los umbrales existentes y tres repeticiones por etapa. El código de
salida es 0 si al menos un modelo supera todas las etapas solicitadas, 2 si
ninguno lo consigue y 1 si falta la clave o se interrumpe el acceso. El preflight
correcto devuelve 0, lo que sólo acredita preparación. Las expectativas del banco
siguen pendientes de validación humana: un resultado sintético es preliminar.

Cloud [no soporta actualmente salidas estructuradas](https://docs.ollama.com/capabilities/structured-outputs).
El esquema se incorpora al prompt y cada JSON se valida localmente. Esta variante
del prompt tiene su propio hash; sus resultados no equivalen a los obtenidos con
generación restringida por esquema. El razonamiento usa el valor predeterminado
del modelo y comparte el presupuesto de generación que aplique el servicio.

Los modelos permitidos son `gemma4:31b`, `gpt-oss:20b` y `gpt-oss:120b`, disponibles
en ambas modalidades al consultar el [catálogo](https://ollama.com/api/tags).
Para `gpt-oss:120b`, use `--models gpt-oss:120b`. El modelo, la cuantización y el
entorno local deben evaluarse de nuevo antes de migrar.

Al terminar la sesión, retire la clave de este proceso:

```powershell
Remove-Item Env:OLLAMA_API_KEY
```
