# Demostración local antes de la reunión con TI

Esta modalidad sirve para presentar la idea desde la computadora de desarrollo.
Ejecuta el motor determinístico y la web real, pero **no** usa SQL Server, IIS,
Ollama, servicios externos ni documentos institucionales.

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

Para detenerla, presione `Ctrl+C` en PowerShell. Los trabajos se guardan en
`tmp/revisor_web_jobs`, carpeta ignorada por Git, y expiran según el TTL local.

## Límites de esta demostración

- Se presenta compartiendo la pantalla de esta computadora; no se debe cambiar
  el host a `0.0.0.0` ni abrir el puerto en el firewall.
- La identidad `demo.local` sustituye temporalmente a IIS/WIA, sólo en loopback.
- La modalidad institucional seguirá exigiendo autenticación y aislamiento por
  usuario. El modo demo no es un despliegue para usuarios finales.
- SQL Server se mantiene aplazado hasta que TI responda la compuerta formal.
