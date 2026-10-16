# Laboratorio doméstico de Ollama para Revisor-CRF

## Propósito

Esta guía permite preparar una computadora de escritorio doméstica como
laboratorio temporal de inferencia para Revisor-CRF. El objetivo inmediato es:

1. comprobar que Ollama funciona en el equipo;
2. conocer el uso real de CPU, RAM, GPU y VRAM;
3. validar la comunicación por API;
4. ejecutar las compuertas editoriales **exclusivamente con casos sintéticos**;
5. decidir con evidencia si conviene ampliar la memoria o utilizar otro equipo.

Este laboratorio no será el despliegue institucional definitivo. SQL Server,
IIS, autenticación corporativa y documentos reales quedan fuera de esta etapa.

## Límites obligatorios

- No copiar al equipo documentos CRF reales, Excel de validación, bancos con
  texto institucional ni archivos bajo `results/` que contengan esos datos.
- No enviar textos a APIs externas ni utilizar modelos cloud de Ollama.
- No abrir el puerto `11434` en el router ni publicarlo en internet.
- No bajar los umbrales de evaluación para aprobar un modelo.
- La IA continuará siendo experimental: no modifica DOCX, cifras, reglas ni
  severidades y toda propuesta requiere revisión humana.
- `qwen3.5:4b` puede utilizarse para probar la instalación, pero permanece
  rechazado como modelo editorial porque no superó la evaluación completa.
- Una evaluación doméstica sintética puede descartar candidatos, pero no puede
  aprobarlos definitivamente sin el banco real dentro de infraestructura
  institucional autorizada.

## Situación conocida

- Equipo: computadora de escritorio con Intel Core i5 de sexta generación,
  8 GB de RAM y tarjeta gráfica todavía no identificada.
- Ollama para Windows requiere Windows 10 22H2 o posterior.
- Ollama escucha inicialmente en `http://127.0.0.1:11434`.
- `qwen3.5:9b` ocupa aproximadamente 7.6 GB descargado y
  `gemma3:12b`, aproximadamente 8.2 GB. A esto se suman el sistema operativo,
  el contexto y las estructuras de inferencia.
- Con 8 GB de RAM se espera poder demostrar un modelo de 4B, pero no evaluar
  de forma confiable los candidatos 9B/12B.
- Recomendación provisional: 16 GB como mínimo para intentar 9B y 32 GB como
  configuración preferible para evaluar 9B/12B por CPU o descarga parcial.

Referencias oficiales:

- [Ollama para Windows](https://docs.ollama.com/windows)
- [Compatibilidad de GPU](https://docs.ollama.com/gpu)
- [API local de Ollama](https://docs.ollama.com/api/introduction)
- [Qwen 3.5 9B](https://ollama.com/library/qwen3.5:9b)
- [Gemma 3 12B](https://ollama.com/library/gemma3:12b)

## Fase 1: inventario antes de instalar

Abrir PowerShell y ejecutar:

```powershell
Get-CimInstance Win32_Processor |
  Select-Object Name, NumberOfCores, NumberOfLogicalProcessors

Get-CimInstance Win32_PhysicalMemory |
  Select-Object Capacity, Speed, Manufacturer, PartNumber

Get-CimInstance Win32_BaseBoard |
  Select-Object Manufacturer, Product, Version

Get-CimInstance Win32_VideoController |
  Select-Object Name, AdapterRAM, DriverVersion

Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, OSArchitecture

Get-Volume |
  Select-Object DriveLetter, FileSystemLabel, SizeRemaining, Size
```

Si la tarjeta es NVIDIA, ejecutar también:

```powershell
nvidia-smi
```

Guardar o copiar la salida. Antes de elegir un modelo se necesitan estos datos:

| Dato | Valor observado |
|---|---|
| Procesador exacto | Pendiente |
| RAM instalada y módulos libres | Pendiente |
| Tarjeta gráfica exacta | Pendiente |
| VRAM detectada | Pendiente |
| Controlador | Pendiente |
| Windows y versión | Pendiente |
| Espacio libre | Pendiente |

`AdapterRAM` puede ser impreciso en algunas tarjetas. Para NVIDIA se preferirá
el dato de `nvidia-smi`. No comprar memoria o GPU hasta identificar la tarjeta
madre, el número de ranuras y la fuente de poder.

## Fase 2: decisión de hardware

Aplicar esta guía después del inventario:

| Condición | Alcance recomendado |
|---|---|
| 8 GB de RAM y GPU de 2 GB o no compatible | Prueba técnica con 4B; no ejecutar 9B/12B |
| 8 GB de RAM y GPU compatible de 4 GB | Prueba con 4B y medición; ampliar RAM antes de 9B |
| 16 GB de RAM y 4–6 GB de VRAM | Intentar `qwen3.5:9b`, una solicitud a la vez |
| 24–32 GB de RAM y 6–8 GB de VRAM | Evaluar 9B; intentar 12B de manera secuencial |
| 32 GB de RAM y 12 GB o más de VRAM | Buen laboratorio para comparar 9B y 12B |

Una GPU compatible acelera el proceso, pero la RAM sigue siendo necesaria si
el modelo no cabe por completo en VRAM. Un i5 de sexta generación puede ejecutar
modelos mediante CPU, aunque una evaluación completa puede tardar horas.

## Fase 3: preparar el equipo sin datos reales

1. Actualizar el controlador de la GPU desde el fabricante.
2. Confirmar que Windows cumple la versión requerida.
3. Reservar por lo menos 25 GB libres para Ollama, un modelo y resultados.
4. Instalar Ollama desde su sitio oficial.
5. Desactivar las funciones cloud para mantener el laboratorio local:

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
```

6. Cerrar Ollama desde el área de notificación y volverlo a iniciar para que
   lea la variable.
7. Confirmar la instalación:

```powershell
ollama --version
ollama list
```

No configurar todavía `OLLAMA_HOST=0.0.0.0:11434`. La primera evaluación se
hará enteramente en la computadora servidor mediante `localhost`.

## Fase 4: prueba mínima de Ollama

Con los 8 GB actuales, descargar inicialmente el modelo pequeño usado solo para
comprobar el conducto técnico:

```powershell
ollama pull qwen3.5:4b
ollama run qwen3.5:4b "Responde únicamente con la palabra listo."
```

Probar la API local:

```powershell
$body = @{
  model = 'qwen3.5:4b'
  prompt = 'Responde únicamente con la palabra listo.'
  stream = $false
  options = @{ num_ctx = 2048; temperature = 0 }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:11434/api/generate' `
  -ContentType 'application/json' `
  -Body $body

ollama ps
```

Registrar del resultado de `ollama ps` si el procesamiento fue `CPU`, `GPU` o
mixto. Durante la prueba observar también Administrador de tareas > Rendimiento.

## Fase 5: trasladar el código de manera segura

El repositorio local contiene commits que podrían no estar publicados. Antes de
trabajar en casa hay que elegir uno de estos mecanismos:

1. clonar el repositorio remoto solo después de autorizar y realizar el `push`;
2. crear un `git bundle` del historial local y llevarlo por un medio autorizado;
3. copiar únicamente el código fuente limpio, excluyendo `.venv/`, `results/`,
   `data/`, documentos reales y Excel.

Un bundle contiene únicamente archivos rastreados por Git:

```powershell
git bundle create revisor-crf-main.bundle main
```

En la computadora doméstica:

```powershell
git clone .\revisor-crf-main.bundle revisor-crf
Set-Location .\revisor-crf
```

Antes de continuar, comprobar que no llegaron datos privados:

```powershell
git status --short
Get-ChildItem .\results -Recurse -ErrorAction SilentlyContinue
Get-ChildItem .\data -Recurse -ErrorAction SilentlyContinue
```

## Fase 6: preparar Python y verificar el proyecto

Desde la raíz del repositorio:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m pytest -q
```

La línea base al preparar esta guía es de **242 pruebas aprobadas**. Si el
número cambia por commits posteriores, se utilizará la línea base documentada
en ese momento y no se continuará si aparecen fallos.

Ejecutar el preflight, que no contacta Ollama:

```powershell
$env:PYTHONPATH = 'src;scripts'
python scripts\evaluate_editorial_context.py --preflight
```

## Fase 7: evaluación sintética de candidatos

Esta fase solo se ejecutará si el inventario indica memoria suficiente. Probar
los modelos secuencialmente, nunca al mismo tiempo.

### Qwen 3.5 9B

```powershell
ollama pull qwen3.5:9b
$env:PYTHONPATH = 'src;scripts'
python scripts\evaluate_editorial_context.py `
  --synthetic-only `
  --models qwen3.5:9b `
  --available-models qwen3.5:9b `
  --output results\editorial_context\qwen35_9b_synthetic.json
```

### Gemma 3 12B

Ejecutar solo si Qwen terminó y el equipo conserva suficiente memoria:

```powershell
ollama stop qwen3.5:9b
ollama pull gemma3:12b
$env:PYTHONPATH = 'src;scripts'
python scripts\evaluate_editorial_context.py `
  --synthetic-only `
  --models gemma3:12b `
  --available-models gemma3:12b `
  --output results\editorial_context\gemma3_12b_synthetic.json
```

La secuencia interna ejecuta tres repeticiones de las compuertas de 2, 10 y 30
casos. Los umbrales permanecen en precisión ≥ 0.90, exhaustividad ≥ 0.85,
exactitud ≥ 0.90, acuerdo ≥ 0.95 y cero respuestas inválidas o cambios
protegidos. El estado máximo doméstico será `synthetic_screen_passed`.

## Fase 8: conexión con otra computadora

La conexión remota no es necesaria para seleccionar el modelo: la evaluación
puede ejecutarse localmente en el servidor. Después de aprobar el conducto
técnico se probará la separación entre equipos.

El adaptador editorial actual acepta Ollama únicamente por loopback y la web
mantiene la IA desactivada. Para la demostración se preparará una de estas rutas:

1. un túnel cifrado que presente el Ollama remoto como `localhost` en la
   computadora cliente; o
2. el servicio intermediario de Revisor-CRF con TLS, token, límite de cuerpo,
   cola de una solicitud y comprobación del digest del modelo.

No se expondrá directamente la API de Ollama. Si ambos equipos están en casa,
se utilizará la misma red local. Cualquier acceso desde otra ubicación requerirá
una VPN autorizada y seguirá limitado a datos sintéticos.

La integración visual con la web será un trabajo posterior: actualmente el MVP
web desactiva Ollama de forma deliberada. Primero se valida modelo y rendimiento;
después se conecta el backend, nunca el navegador directamente.

## Evidencias que se recopilarán

No guardar prompts ni texto institucional. Registrar únicamente:

| Evidencia | Resultado |
|---|---|
| Modelo y digest | Pendiente |
| Tamaño descargado | Pendiente |
| CPU/GPU/mixto según `ollama ps` | Pendiente |
| RAM máxima observada | Pendiente |
| VRAM máxima observada | Pendiente |
| Tiempo de la prueba mínima | Pendiente |
| Tiempo de 2 casos | Pendiente |
| Tiempo de 10 casos | Pendiente |
| Tiempo de 30 casos | Pendiente |
| JSON inválidos | Pendiente |
| Precisión/exhaustividad/exactitud/acuerdo | Pendiente |
| Temperatura o reinicios del equipo | Pendiente |

## Criterios para detenerse

Detener la prueba y conservar los resultados si ocurre cualquiera de estos
casos:

- Windows empieza a intercambiar memoria continuamente y deja de responder;
- el modelo no puede cargarse;
- la temperatura del equipo o la GPU se vuelve insegura;
- aparecen respuestas inválidas en una compuerta;
- el modelo no alcanza un umbral;
- la ejecución exige copiar datos institucionales al equipo doméstico;
- sería necesario exponer Ollama directamente a internet.

## Resultado esperado de la jornada

Al terminar se debe poder responder:

1. ¿La GPU es compatible y cuánta inferencia descarga Ollama en ella?
2. ¿Es suficiente ampliar RAM o también se necesita otra GPU?
3. ¿Cuánto tarda `qwen3.5:9b` por caso en este equipo?
4. ¿El candidato supera las compuertas sintéticas de manera estable?
5. ¿Vale la pena integrar este servidor con la demostración web?

La primera actividad de la próxima sesión será revisar el inventario. Solo
después se decidirá qué instalar y qué modelo descargar.
