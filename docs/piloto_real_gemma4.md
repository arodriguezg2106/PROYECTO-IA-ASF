# Piloto autorizado de un caso real con cifras alteradas

El usuario autorizó expresamente utilizar cualquier caso local y declaró que las
cifras están alteradas. Se seleccionó el DOCX de Sonora de `tests/CRF-sinteticas`,
con un cambio humano registrado de «agua nacionales» a «aguas nacionales».
Las cifras del párrafo permanecen iguales entre ambas versiones.

La prueba es descriptiva: un cambio de Word no demuestra que toda la versión
final sea correcta. El resultado no aprueba al modelo ni sustituye la validación
institucional. Su diario está separado de las 180 solicitudes de `consistency-v1`;
no cambia el código ni los datos congelados de ese experimento.

Preparación local sin clave ni red:

```powershell
$env:PYTHONPATH = 'src;scripts'
.\.venv\Scripts\python.exe scripts/probe_real_ollama_case.py --prepare
```

El preview se guarda en `results/ollama_cloud/real_case_sonora/case_preview.md`.
Se envía únicamente el texto de un párrafo por solicitud: versión anterior y
posterior, repetidas tres veces cada una, máximo seis intentos. No se envían el
DOCX completo, nombre del archivo, comentarios, autores ni el par como respuesta
esperada. Las dos versiones conservan el contenido del documento autorizado;
no se realiza una anonimización adicional automática.

Ejecutar usando una clave temporal en PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\probe_real_ollama_case.ps1
```

Si ya existe `OLLAMA_API_KEY` en el proceso, también puede ejecutar directamente
`python scripts/probe_real_ollama_case.py` con `PYTHONPATH` configurado. El modelo
es `gemma4:31b`, prompt conservador y criterios comunes del experimento, temperatura
0, semilla 20260923, `think: false`, máximo 2048 tokens de generación y timeout 60 s.

Los resultados están en `report.md`, `report.json` y `result.json`, junto al caso
congelado `case.json`. Cada intento se guarda antes de enviarse. Los errores
detienen la ejecución sin reintentos; volver a invocar el comando sólo envía los
pendientes, preservando como inválidos los intentos fallidos o inciertos. Tras
seis intentos no vuelve a consultar inferencia. La prueba requiere revisión
humana de cada hallazgo, evidencia y propuesta; los controles mecánicos de cifras
pueden tener falsas alarmas de puntuación, documentadas en la auditoría de A.

El consumo real y la cuota Free deben consultarse en Ollama. El límite de seis
intentos no es un tope monetario garantizado.
