# Seguridad de la demostración del 2 de noviembre de 2026

## Alcance y fronteras de confianza

La demo usa una sola instancia del backend y almacenamiento efímero local. El
navegador sólo habla con el backend; LanguageTool u Ollama, si se habilitan, se
conectan desde el backend por loopback. SQL Server, Internet público y
producción están fuera del alcance.

Activos protegidos: DOCX de entrada, reportes, decisiones, identidad del
revisor y disponibilidad de la cola. Amenazas principales: archivos DOCX/ZIP
maliciosos, agotamiento de recursos, acceso cruzado, suplantación del proxy,
CSRF/XSS, fuga por logs y sustitución del modelo.

## Controles implementados

- carga transmitida directamente a archivo temporal con límite de tamaño;
- validación de firma DOCX, rutas ZIP, duplicados, cifrado, número/tamaño/ratio
  de entradas y declaraciones XML peligrosas;
- cola FIFO de capacidad fija, admisión atómica, cupo por usuario, trabajadores
  limitados, timeout cooperativo, `503` y `Retry-After` al saturarse;
- propiedad obligatoria antes de estado, decisiones y descargas;
- identidad delegada sólo desde proxies explícitos, sin comodines;
- comprobación same-origin en operaciones mutables y límite por usuario/IP;
- comentarios de hasta 500 caracteres y estados/UUID/artefactos con lista blanca;
- cabeceras CSP, nombres de descarga controlados y HTML escapado;
- logs agregados sin nombres de archivo ni texto documental;
- `/api/health` público reducido y `/api/ready` protegido;
- Ollama desactivado por defecto, URL local, digest/perfil verificados y
  degradación segura al resultado determinístico.

El timeout es cooperativo: una biblioteca que ignore la cancelación puede
terminar su llamada antes de liberar el trabajador. La cola no pierde trabajos
aceptados ni excede la concurrencia, pero producción deberá aislar el
procesamiento en procesos reemplazables o una cola durable.

## Verificación

GitHub Actions ejecuta la suite en Python 3.11 y 3.14, Bandit, `pip-audit`,
Gitleaks y genera SBOM CycloneDX. Ningún hallazgo crítico o alto puede aceptarse
en la etiqueta.

DAST local, exclusivamente con documentos sintéticos:

```powershell
.\scripts\start_local_demo.ps1 -Port 8000
docker run --rm --network host -t ghcr.io/zaproxy/zaproxy:stable `
  zap-baseline.py -t http://127.0.0.1:8000 -r zap-demo.html
```

En Docker Desktop para Windows puede requerirse
`http://host.docker.internal:8000`. El informe permanece fuera de Git. Las
medias se corrigen o justifican; una prueba de penetración institucional formal
sigue siendo obligatoria antes de producción.

## Riesgos residuales aceptados para la demo

- estado y cola no sobreviven como trabajos reanudables a un reinicio;
- limitación de tasa y telemetría viven en memoria de un único proceso;
- el almacenamiento local no sustituye controles institucionales de respaldo;
- Colab sólo acredita comportamiento sintético y es infraestructura externa;
- aún no existen IIS/WIA, HTTPS institucional ni SQL Server.
