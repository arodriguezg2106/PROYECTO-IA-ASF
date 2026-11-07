# Consistencia y calidad editorial de Gemma 4 31B

El protocolo `consistency-v1` usa únicamente 30 textos sintéticos, dos prompts
existentes y un máximo de 180 intentos de inferencia. No modifica la aplicación
web, el registro de aprobación ni los resultados previos. La consistencia de una
respuesta no demuestra que sea correcta: responder siempre sin hallazgos no pasa
los umbrales de calidad.

## 1. Revisar las etiquetas, sin consumir API

Desde la raíz del proyecto:

```powershell
$env:PYTHONPATH = 'src;scripts'
.\.venv\Scripts\python.exe scripts/evaluate_ollama_cloud.py --protocol consistency-v1 --preflight
```

El preflight no consulta red ni exige clave. Genera
`results/ollama_cloud/consistency-v1/bank_review.md` y `preflight.json`. La revisión
también está disponible en [banco_consistencia_gemma4.md](banco_consistencia_gemma4.md).
El banco fuente es `src/revisor_crf/editorial_consistency_bank.json`.

El usuario debe revisar los 30 textos, el criterio aplicable, la etiqueta y todas
las alternativas de evidencia. Los casos debatibles deben corregirse o
sustituirse en el banco antes de ejecutar el modelo. Una evidencia aceptable es
un substring literal exacto, no una referencia aproximada. El preflight muestra
el hash canónico SHA-256 del contenido JSON; no es el hash de los bytes del archivo.
Después de cualquier cambio, regenerar el documento de revisión y el hash.

Tras confirmar las etiquetas, congelar explícitamente ese hash:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_ollama_cloud.py `
  --protocol consistency-v1 --freeze-bank `
  --reviewer 'Nombre de quien revisó las etiquetas' `
  --reviewed-bank-sha256 'HASH_MOSTRADO_EN_EL_PREFLIGHT'
```

Esta orden crea una copia congelada del banco y registra al revisor. No consume
API y no aprueba el modelo. No se permite sustituir esa aprobación ni modificar
el banco una vez congelado. El documento versionado de revisión debe regenerarse
si se modifica el banco fuente. Ninguna etiqueta se valida automáticamente.

## 2. Ejecutar una etapa por vez

El ayudante solicita la clave sin mostrarla, la usa sólo en el proceso y restaura
las variables al terminar. No hace falta guardarla como variable de usuario.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe_ollama_credit.ps1 -ConsistencyPhase selection
```

La selección realiza 10 casos equilibrados por tres repeticiones y dos prompts:
`conservative` y `research`, hasta 60 intentos. Ambos tienen los mismos criterios,
reglas, esquema e instrucciones de protección; difieren sólo en el prompt base.
Cada prompt debe superar precisión ≥90%, exhaustividad ≥85% y exactitud ≥90%
en **cada repetición**, con cero respuestas inválidas e inseguras. Se elige por
mayor exhaustividad agregada, después precisión y menor número de tokens
reportados de entrada y salida. Un empate completo se resuelve por nombre.

Si ninguno pasa, se detiene el experimento. No se gastan las 120 solicitudes
reservadas. Si uno pasa, consulte su uso Free antes de ejecutar la validación A:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe_ollama_credit.ps1 -ConsistencyPhase validation-a
```

La validación usa 20 casos reservados por tres repeticiones del prompt elegido:
hasta 60 intentos. La validación B usa los mismos casos y parámetros, **entre
24 y 72 horas después de terminar A**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe_ollama_credit.ps1 -ConsistencyPhase validation-b
```

No se agenda ni ejecuta B automáticamente. Fuera de la ventana se rechaza la
inferencia; no se modifica la hora para hacer pasar el experimento. Cada ejecución
usa conversaciones nuevas y orden barajado reproducible por perfil, fase y
repetición. Parámetros fijos: temperatura 0, semilla 20260923, `think: false`,
`num_predict: 2048`, timeout 60 segundos. El servicio puede no garantizar
determinismo aun con esos parámetros.

El código de salida es 0 si la etapa supera los umbrales (o ya estaba completa),
2 si completó pero falló calidad y 1 ante bloqueo o interrupción. Tras selección,
0 significa que existe un prompt elegible. Superar A o B por separado no sustituye
la decisión final de consistencia entre las seis repeticiones.

## 3. Diario, reanudación y comparabilidad

Todos los artefactos se guardan en el directorio fijo
`results/ollama_cloud/consistency-v1/`, separado del probe y smoke anteriores:

- `experiment.json`: configuración y diario por intento, incluidos solicitud,
  respuesta final de texto, perfil, caso, sesión, repetición, semilla de orden,
  parámetros, tokens, caché, tiempo y evaluación. No contiene la clave ni el
  razonamiento interno del modelo.
- `report.json` y `report.md`: calidad por repetición, errores, estabilidad y
  conclusión. `selected_model` permanece en `null` incluso si la prueba pasa.
- `review.json` y `frozen_bank.json`: aprobación humana y banco congelado.

Cada intento se guarda **antes de enviarlo** y su resultado se persiste de nuevo.
Se interrumpe ante errores de autenticación, cuota o transporte, sin reintentos.
Para reanudar, invoque explícitamente el mismo comando de etapa: sólo envía tareas
que no figuran en el diario. Los intentos fallidos o inciertos consumen una plaza,
se consideran inválidos y nunca se vuelven a enviar. Una caída entre recibir y
guardar una respuesta puede dejar un intento incierto; no se presume éxito.

Un bloqueo `experiment.lock` impide dos ejecuciones concurrentes. Si una caída
deja el archivo, primero compruebe que no existe otra ejecución; sólo entonces
retírelo para reanudar. No borre el diario ni reinicie etapas para mejorar métricas.
El presupuesto incluye todos los intentos y no se reinicia entre procesos.

Se congelan y comparan hashes de banco, reglas, prompts, esquema, parámetros,
commit y archivos de implementación. Se consulta `/api/tags` antes de cada etapa
o reanudación para registrar el digest y metadatos disponibles del modelo; esto
no es una llamada de inferencia. Si faltan, se detiene. Un cambio de configuración,
digest o nombre de modelo impide combinar resultados y marca el experimento como
no comparable. El digest publicado es la identificación disponible, no una
garantía de que el servicio no cambie internamente durante una etapa.

No cambie prompts, implementación ni banco durante la evaluación. Si es necesario
corregir el protocolo, se debe documentar una nueva versión y un nuevo presupuesto;
no eliminar el experimento anterior.

## 4. Métricas y decisión

En cada una de las seis repeticiones finales deben cumplirse los umbrales de
calidad, cero respuestas inválidas y cero alteraciones de elementos protegidos.
La evidencia debe ser literal y coincidir con una alternativa adjudicada. Un
hallazgo ajeno a esas alternativas cuenta como falsa alarma, incluso si el modelo
también acertó otro hallazgo del mismo caso. Si no hay detecciones, la precisión
es `null` (N/C) y la exhaustividad cero: no se convierte en un éxito.

El acuerdo final requiere que al menos 19 de los 20 textos mantengan la misma
decisión y conjunto de reglas en las seis respuestas. Una respuesta inválida
impide declarar estable ese caso. Se reporta por separado la estabilidad de
severidades, evidencias y correcciones; la redacción de las explicaciones no
interviene en el acuerdo principal. El texto de corrección sólo normaliza Unicode
y espacios para ese diagnóstico; no se afirma equivalencia semántica automática.

El informe diferencia `no validado`, `estable pero insuficiente`, `útil pero
inestable` y `candidato consistente para piloto sintético`. La ausencia de datos
finales suficientes nunca permite la última conclusión. Una selección estable
sin prompt elegible se reporta como estable pero insuficiente.

Los controles de elementos protegidos son mecánicos: no sustituyen la revisión
humana del sentido, de las explicaciones ni de la idoneidad de las correcciones.
El modelo seguiría necesitando validación institucional local antes de procesar
documentos reales.

## Consumo y pruebas locales

180 es un límite de intentos, no un tope monetario. El protocolo registra tokens
de entrada, salida y caché; la caché es parte de la entrada, no consumo adicional.
Puede haber consumo no reportado si falla una solicitud. El indicador Free debe
consultarse por el usuario entre etapas; no se infiere saldo del porcentaje 0%.

Antes de usar la API, ejecutar:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_editorial_consistency.py tests/test_ollama_cloud.py
```

Las pruebas usan transportes simulados e incluyen respuestas vacías, falsas
alarmas, decisiones alternantes, explicaciones distintas, JSON inválido,
alteración de cifras, cambios de modelo y configuración, ventana temporal,
concurrencia, presupuesto y reanudación después de fallo o caída sin duplicados.
