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
- La ruta recomendada es Linux de servidor sin escritorio gráfico. Windows se
  conserva como alternativa para la primera prueba si no se desea reinstalar.
- Ollama para Windows requiere Windows 10 22H2 o posterior.
- Ollama escucha inicialmente en `http://127.0.0.1:11434`.
- `qwen3.5:9b` ocupa aproximadamente 7.6 GB descargado y
  `gemma3:12b`, aproximadamente 8.2 GB. A esto se suman el sistema operativo,
  el contexto y las estructuras de inferencia.
- Con 8 GB de RAM se espera poder demostrar un modelo de 4B, pero no evaluar
  de forma confiable los candidatos 9B/12B.
- Recomendación provisional: 16 GB como mínimo para intentar 9B y 32 GB como
  configuración preferible para evaluar 9B/12B por CPU o descarga parcial.
- Con los 8 GB actuales, Linux puede liberar más memoria que Windows, pero no
  sustituye la ampliación física. El objetivo es saber si el modelo 9B puede
  evaluarse lentamente, no prometer rendimiento interactivo.
- El repositorio publicado tiene una línea base de **248 pruebas**. LanguageTool
  no forma parte de esta jornada y debe permanecer desactivado.

Referencias oficiales:

- [Ollama para Windows](https://docs.ollama.com/windows)
- [Ollama para Linux](https://docs.ollama.com/linux)
- [Compatibilidad de GPU](https://docs.ollama.com/gpu)
- [Memoria, concurrencia y caché de Ollama](https://docs.ollama.com/faq)
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
| Sistema actual y versión | Pendiente |
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

### Decisión del sistema operativo

Si el inventario confirma compatibilidad de la GPU en Linux, se utilizará
**Ubuntu Server LTS sin entorno gráfico**. Esta opción reduce servicios y memoria
residentes, facilita ejecutar Ollama mediante `systemd` y permite administrar el
equipo por SSH.

Antes de reemplazar Windows:

1. respaldar cualquier archivo que deba conservarse;
2. crear un USB arrancable con una distribución Linux que permita modo vivo;
3. iniciar primero una sesión en modo vivo, sin instalar;
4. comprobar red, disco y GPU;
5. instalar solo después de confirmar el inventario y el respaldo.

No se formateará ningún disco durante la etapa de diagnóstico. Si la GPU no es
compatible en Linux, se comparará con Windows antes de tomar una decisión.

## Fase 3: preparar el equipo sin datos reales

### Ruta A: Linux de servidor, recomendada

1. Actualizar BIOS o firmware solo si el fabricante lo exige para la GPU o una
   ampliación de RAM; no hacerlo como paso rutinario.
2. Probar Linux desde USB en modo vivo y confirmar GPU, red y almacenamiento.
3. Instalar Ubuntu Server LTS sin escritorio únicamente después del respaldo.
4. Habilitar SSH durante la instalación para administrar el equipo sin monitor.
5. Reservar al menos 25 GB libres para Ollama, un modelo y resultados. Se
   prefiere SSD; el uso intensivo de swap en un disco mecánico será demasiado
   lento para esta evaluación.
6. Instalar primero el controlador compatible de la GPU y comprobarlo. Para
   NVIDIA:

```bash
nvidia-smi
```

7. Instalar Ollama por el procedimiento oficial:

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl status ollama
ollama --version
```

8. Crear una personalización del servicio:

```bash
sudo systemctl edit ollama
```

Agregar:

```ini
[Service]
Environment="OLLAMA_NO_CLOUD=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_CONTEXT_LENGTH=2048"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="OLLAMA_KEEP_ALIVE=5m"
```

Aplicar y comprobar:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl status ollama
journalctl -u ollama -n 50 --no-pager
```

`OLLAMA_KV_CACHE_TYPE=q8_0` reduce aproximadamente a la mitad la memoria de la
caché K/V cuando el backend admite Flash Attention, con una pérdida normalmente
muy pequeña. No se usará `q4_0` durante la evaluación inicial porque puede
afectar más la calidad.

### Memoria virtual

El swap será únicamente una red de seguridad. Antes de crearlo se comprobarán
el tipo de disco, el espacio disponible y si ya existe swap:

```bash
free -h
swapon --show
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,MODEL
```

Si hay SSD y no existe swap suficiente, se podrá preparar entre 8 y 16 GB tras
revisar el estado del disco. Si el modelo trabaja continuamente desde swap, el
resultado se marcará como no apto para demostración interactiva aunque consiga
terminar las pruebas.

### Ruta B: Windows, alternativa sin reinstalación

1. Actualizar el controlador de la GPU desde el fabricante.
2. Confirmar que Windows cumple la versión requerida.
3. Reservar por lo menos 25 GB libres.
4. Instalar Ollama desde su sitio oficial.
5. Desactivar las funciones cloud:

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
```

6. Limitar Ollama a un modelo, una solicitud y contexto de 2,048 tokens:

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_MAX_LOADED_MODELS', '1', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_NUM_PARALLEL', '1', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', '2048', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_KV_CACHE_TYPE', 'q8_0', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_KEEP_ALIVE', '5m', 'User')
```

7. Cerrar Ollama desde el área de notificación y volverlo a iniciar para que
   lea la variable.
8. Confirmar la instalación:

```powershell
ollama --version
ollama list
```

En ambas rutas, no configurar todavía `OLLAMA_HOST=0.0.0.0:11434`. La primera
evaluación se hará enteramente en la computadora servidor mediante `localhost`.

## Fase 4: prueba mínima de Ollama

Con los 8 GB actuales, descargar inicialmente el modelo pequeño usado solo para
comprobar el conducto técnico. En Linux o Windows:

```powershell
ollama pull qwen3.5:4b
ollama run qwen3.5:4b "Responde únicamente con la palabra listo."
```

Probar la API local:

En Linux:

```bash
curl http://127.0.0.1:11434/api/generate -d '{
  "model": "qwen3.5:4b",
  "prompt": "Responde únicamente con la palabra listo.",
  "stream": false,
  "keep_alive": "5m",
  "options": {"num_ctx": 2048, "temperature": 0}
}'

ollama ps
```

En Windows PowerShell:

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
mixto. En Windows observar también Administrador de tareas > Rendimiento. En
Linux se puede vigilar en otra terminal:

```bash
watch -n 2 free -h
```

Para una GPU NVIDIA:

```bash
watch -n 2 nvidia-smi
```

## Fase 5: obtener el código publicado

El código se obtiene directamente del repositorio remoto. No copiar la carpeta
de trabajo institucional ni usar USB para trasladar `results/`, `data/`, Excel
o documentos. En Windows PowerShell:

```powershell
git clone https://github.com/arodriguezg2106/PROYECTO-IA-ASF.git
Set-Location .\PROYECTO-IA-ASF
git status --short
git log -1 --oneline
```

En Linux:

```bash
git clone https://github.com/arodriguezg2106/PROYECTO-IA-ASF.git
cd PROYECTO-IA-ASF
git status --short
git log -1 --oneline
```

Antes de continuar, comprobar que no llegaron datos privados:

```powershell
git status --short
Get-ChildItem .\results -Recurse -ErrorAction SilentlyContinue
Get-ChildItem .\data -Recurse -ErrorAction SilentlyContinue
```

## Fase 6: preparar Python y verificar el proyecto

Desde la raíz del repositorio, en Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m pytest -q
```

O en Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m pytest -q
```

La línea base al preparar esta guía es de **248 pruebas aprobadas**. Si el
número cambia por commits posteriores, se utilizará la línea base documentada
en ese momento y no se continuará si aparecen fallos.

Ejecutar el preflight, que no contacta Ollama. En Linux:

```bash
export PYTHONPATH='src:scripts'
python scripts/evaluate_editorial_context.py --preflight --synthetic-only
```

En Windows PowerShell:

```powershell
$env:PYTHONPATH = 'src;scripts'
python scripts\evaluate_editorial_context.py --preflight --synthetic-only
```

## Fase 7: evaluación sintética de candidatos

Esta fase solo se ejecutará si el inventario indica memoria suficiente. Probar
los modelos secuencialmente, nunca al mismo tiempo.

### Qwen 3.5 9B

En Linux:

```bash
ollama pull qwen3.5:9b
export PYTHONPATH='src:scripts'
python scripts/evaluate_editorial_context.py \
  --synthetic-only \
  --models qwen3.5:9b \
  --available-models qwen3.5:9b \
  --output results/editorial_context/qwen35_9b_synthetic.json
```

En Windows PowerShell:

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

En Linux:

```bash
ollama stop qwen3.5:9b
ollama pull gemma3:12b
export PYTHONPATH='src:scripts'
python scripts/evaluate_editorial_context.py \
  --synthetic-only \
  --models gemma3:12b \
  --available-models gemma3:12b \
  --output results/editorial_context/gemma3_12b_synthetic.json
```

En Windows PowerShell:

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

La primera conexión entre la laptop y el servidor doméstico se hará mediante un
túnel SSH, manteniendo Ollama en `127.0.0.1` en ambas puntas. Desde la laptop:

```powershell
ssh -N -L 11434:127.0.0.1:11434 usuario@IP_DEL_SERVIDOR
```

Mientras esa terminal permanezca abierta, en otra terminal de la laptop:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags'
```

Si responde, Revisor-CRF puede seguir usando su URL de loopback habitual sin
publicar el puerto de Ollama. Esta prueba se hará sólo después de completar las
pruebas locales en el servidor. No se configurará `OLLAMA_HOST=0.0.0.0:11434`.

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

- el sistema empieza a intercambiar memoria continuamente y deja de responder;
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
