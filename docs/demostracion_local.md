# Demostración local antes de la reunión con TI

Esta modalidad sirve para presentar la idea desde la computadora de desarrollo.
Ejecuta el motor determinístico y la web real, pero **no** usa SQL Server, IIS
ni documentos institucionales. Los proveedores lingüísticos permanecen
apagados salvo activación explícita con un perfil aprobado.

## Preparación única

Desde PowerShell, en la raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Si `.venv` ya existe y tiene esas dependencias, no repita la preparación.

## Arranque

```powershell
.\scripts\start_local_demo.ps1
```

El script crea `data\demo_crf_sintetico.docx`, abre el backend exclusivamente en
`127.0.0.1:8000` y muestra la ruta del archivo que debe cargarse. Abra
<http://127.0.0.1:8000> en el navegador, cargue ese DOCX y muestre el JSON, HTML
y Word comentado generados. El documento contiene cifras inventadas y una
discrepancia deliberada: `100 + 50` frente a un total declarado de `200`.

Para usar otro puerto:

```powershell
.\scripts\start_local_demo.ps1 -Port 8080
```

Para mostrar también las reglas editoriales determinísticas ASF, sin Ollama ni
LanguageTool:

```powershell
.\scripts\start_local_demo.ps1 -Editorial
```

El parámetro `-LanguageTool` no debe utilizarse con el perfil candidato actual:
la compuerta vigente fue rechazada por exhaustividad insuficiente. Cuando una
evaluación futura genere un perfil aprobado, el script exigirá además
`-Editorial`, `-LanguageToolProfile` y limitará la web a un trabajo concurrente.

Un modelo que haya superado la evaluación sintética puede mostrarse, sólo con
el DOCX sintético y Ollama en loopback:

```powershell
.\scripts\start_local_demo.ps1 -Editorial -Ollama `
  -OllamaProfile .\results\colab\perfil-ollama.json
```

LanguageTool y Ollama son mutuamente excluyentes. Si Ollama se detiene, vence
el timeout o devuelve JSON inválido, la revisión determinística debe terminar y
el proveedor aparecerá como parcial.

Para obtener evidencia agregada de saturación y rendimiento, deje la demo
activa en una terminal y ejecute en otra:

```powershell
$env:PYTHONPATH = "src;scripts"
.\.venv\Scripts\python.exe scripts\load_test_web.py `
  .\data\demo_crf_sintetico.docx --requests 8
```

El JSON queda bajo `results/demo/` (ignorado por Git) y no contiene nombres ni
texto documental.

Para detenerla, presione `Ctrl+C` en PowerShell. Los trabajos se guardan en
`tmp/revisor_web_jobs`, carpeta ignorada por Git, y expiran según el TTL local.

## Límites de esta demostración

- Se presenta compartiendo la pantalla de esta computadora; no se debe cambiar
  el host a `0.0.0.0` ni abrir el puerto en el firewall.
- La identidad `demo.local` sustituye temporalmente a IIS/WIA, sólo en loopback.
- La modalidad institucional seguirá exigiendo autenticación y aislamiento por
  usuario. El modo demo no es un despliegue para usuarios finales.
- SQL Server se mantiene aplazado hasta que TI responda la compuerta formal.
