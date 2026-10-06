# Arquitectura Web Interna Centralizada para Revisor-CRF

Fecha: 6 de octubre de 2026.  
Estado: Aprobado para implementación de MVP.

## 1. Objetivo y Alcance

El objetivo de este componente es proporcionar una interfaz web interna y centralizada que permita a los auditores y revisores evaluar documentos CRF (`.docx`) mediante el motor determinístico sin requerir instalaciones de Python, dependencias locales ni configuración en sus estaciones de trabajo.

El usuario interactúa exclusivamente a través del navegador web para:
1. Cargar un archivo DOCX.
2. Supervisar el estado del procesamiento (`recibido`, `procesando`, `terminado`, `fallido`).
3. Consultar el resumen de alertas y navegar el reporte HTML generado.
4. Descargar los entregables generados: informe estructurado (`.json`), reporte interactivo (`.html`) y copia comentada de Word (`.docx`).

### Alcance y exclusiones del MVP
- **Procesamiento estrictamente del lado del servidor**: Los documentos se procesan en el backend local.
- **Sin servicios externos ni nube**: No se emplean servicios externos, CDNs ni librerías remotas.
- **Aislamiento de la lógica de negocio**: Se reutiliza la API pública de `revisor_crf` (`read_docx`, `review_document`, `export_html`, `export_commented_docx`, `export_json`) sin alterar las reglas determinísticas, catálogos editoriales ni scripts existentes.
- **Exclusión explícita de Ollama y LanguageTool**: En este MVP no se activan dependencias de modelos de lenguaje ni de servidores externos. Ollama queda documentado únicamente como una futura integración opcional interna del backend; jamás se expondrá directamente al navegador.

---

## 2. Estructura de Componentes

El desarrollo se organiza en un paquete separado `src/revisor_web/` para asegurar desacoplamiento total:

```text
src/
    revisor_crf/             # Módulo núcleo existente (intacto)
    revisor_web/             # Módulo web interno (MVP)
        __init__.py
        __main__.py          # Ejecución directa: python -m revisor_web
        config.py            # Variables de configuración y límites operativos
        validation.py        # Validación estricta de archivos y firma ZIP
        storage.py           # Gestión de carpetas temporales por UUID y limpieza TTL
        service.py           # Orquestación de revisiones y control de concurrencia
        app.py               # Aplicación FastAPI, endpoints REST y rutas HTML
        templates/
            index.html       # Interfaz accesible sin CDNs ni scripts externos
tests/
    test_web.py              # Pruebas automatizadas de la API y el ciclo de vida web
requirements-web.txt         # Dependencias web adicionales (FastAPI, uvicorn, python-multipart, httpx)
```

---

## 3. Flujo de Datos y Ciclo de Vida del Trabajo

```
[ Navegador del Usuario ]
       |
       | 1. POST /api/jobs (multipart/form-data con archivo .docx)
       v
[ FastAPI Router / Validation ]
       | 2. Validación: Extensión .docx, tamaño <= límite, firma PK\x03\x04, ZIP válido
       |    Rechazo inmediato (400/413) ante anomalías técnicas.
       v
[ Job Storage (UUID) ]
       | 3. Creación de subdirectorio aislado: <jobs_dir>/<job_uuid>/
       |    Guarda input.docx original de forma intacta. Estado inicial: "recibido".
       v
[ Concurrency Limiter (Semaphore) ]
       | 4. Control de concurrencia: si hay cupo -> pasa a "procesando".
       |    Si la cola/capacidad está saturada -> HTTP 503 (Servicio Ocupado).
       v
[ Worker / ThreadPool ]
       | 5. Ejecución del motor determinístico (review_document):
       |    - Genera resultados en memoria.
       |    - Exporta report.json, report.html y commented.docx en el directorio del trabajo.
       |    - Actualiza estado a "terminado" con metadatos resumidos.
       |    - En caso de excepción -> estado "fallido" con mensaje técnico sanitizado.
       v
[ Polling / Consulta del Cliente ]
       | 6. GET /api/jobs/{id} -> Estado, métricas y URLs de descarga.
       | 7. GET /api/jobs/{id}/download/{json|html|docx} -> Entrega de artefactos.
       v
[ Background Cleaner (TTL) ]
       | 8. Tarea periódica evalúa fecha de creación de cada trabajo.
       |    Elimina completamente la carpeta del disco una vez superado el TTL.
```

---

## 4. Estados del Trabajo

Cada procesamiento atraviesa un ciclo de vida unidireccional y finito:

| Estado | Significado | Acciones Permitidas |
|---|---|---|
| `recibido` | Archivo validado y almacenado; en espera de ranura de procesamiento. | Consulta de estado. |
| `procesando` | El motor determinístico está analizando la estructura y reglas. | Consulta de estado. |
| `terminado` | Revisión finalizada exitosamente; artefactos listos en disco. | Consulta de resumen y descarga de JSON, HTML y DOCX comentado. |
| `fallido` | Ocurrió un error en la validación interna o ejecución del motor. | Consulta de motivo de error (sin revelar rutas ni texto sensible). |

---

## 5. Modelo de Amenazas y Controles de Seguridad

| Amenaza | Vector / Escenario | Medida de Mitigación Implementada |
|---|---|---|
| **Carga de ejecutables o scripts** | Subir `.exe`, `.bat` o `.php` renombrados. | Verificación doble: extensión `.docx` + firma mágica `PK\x03\x04` + inspección obligatoria de estructura ZIP conteniendo `word/document.xml`. |
| **Denegación de servicio por tamaño (Zip Bomb / Archivo Gigante)** | Subir archivos de cientos de megabytes o zips altamente comprimidos. | Límite estricto de tamaño (`MAX_FILE_SIZE_MB`, por defecto 25 MB). Se verifica `Content-Length` y se interrumpe la lectura si el flujo excede el límite. Descompresión controlada mediante `python-docx` y `lxml`. |
| **Agotamiento de CPU por concurrencia desmedida** | Múltiples cargas simultáneas colapsan la máquina servidora. | Semáforo de concurrencia acotado (`MAX_CONCURRENT_JOBS`, por defecto 2 procesamientos simultáneos). Rechazo inmediato con código HTTP 503 ante saturación. |
| **Fuga de información confidencial en registros (Logs)** | Registro involuntario de párrafos, cifras o nombres de auditoría en los archivos de log del servidor. | **Política de Cero Texto en Logs**: El subsistema de registro únicamente emite marcas temporales, identificadores aleatorios (UUID), tamaño en bytes, código de estado y tiempos de ejecución. Nunca se imprimen cadenas extraídas de los documentos. |
| **Persistencia indebida de documentos en el servidor** | Acumulación de auditorías sensibles en el disco del servidor central. | **Limpieza estricta por TTL**: Parámetro `JOB_TTL_SECONDS` (por defecto 1800 s / 30 minutos). Un recolector en segundo plano elimina de forma irrecuperable los archivos y directorios del trabajo una vez expirado el plazo. |
| **Exposición no autorizada de servicios auxiliares (Ollama/LLM)** | Acceso directo de clientes al puerto de Ollama o reconfiguración de prompts. | Ollama no se expone a la red ni al navegador. Toda interacción futura ocurrirá estrictamente de backend a backend vía HTTP local autenticado. |
| **Acceso directo no controlado desde la red** | Exposición del puerto de desarrollo a interfaces externas sin cifrado. | Por diseño, la aplicación escucha exclusivamente en `127.0.0.1` de forma predeterminada. |

---

## 6. Supuestos y Lineamientos para Despliegue en Producción

El backend de este MVP opera como servicio interno local (`127.0.0.1:8000`). En un entorno de producción institucional no se expone directamente a los usuarios finales, sino a través de la infraestructura perimetral existente:

1. **Proxy Inverso con Terminación TLS**:
   - Se debe anteponer un proxy corporativo (por ejemplo, IIS con ARR, Nginx o Apache) configurado con certificados válidos (HTTPS).
   - El proxy debe reescribir cabeceras estándar: `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`.
2. **Autenticación Institucional**:
   - La autenticación (Active Directory / Kerberos / Windows Integrated Auth o SAML/OAuth2) debe resolverse en el proxy inverso antes de canalizar la petición hacia la aplicación web interna.
3. **Límites de Petición en Proxy**:
   - El proxy debe reflejar el límite configurado (`client_max_body_size 25M` o directiva equivalente en IIS) y tiempos de espera adecuados para revisiones extensas (`proxy_read_timeout 120s`).
4. **Protección de Cabeceras HTTP**:
   - Cabeceras de seguridad recomendadas añadidas en el proxy o middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Content-Security-Policy: default-src 'self' 'unsafe-inline'`.

---

## 7. Estimación Básica de Consumo de Recursos (Sin Ollama)

> **Nota Metodológica**: Las cifras presentadas a continuación corresponden a **mediciones preliminares de referencia** obtenidas en laboratorio mediante documentos sintéticos y de prueba; **no representan límites máximos garantizados ni techos absolutos**, dado que el consumo real varía en función de la complejidad estructural del documento, el volumen de cuadros anidados y la profundidad del marcado XML.

- **CPU**: El análisis determinístico es monohilo intensivo por documento (recorrido XML y cotejo de expresiones regulares). Tiempo típico en CPU moderna:
  - Documentos sintéticos o cortos (1 a 10 páginas): 0.2 a 0.8 segundos.
  - Documentos CRF extensos (50 a 200 páginas): 2 a 8 segundos.
- **Memoria RAM**: 
  - `python-docx` y `lxml` cargan el árbol XML en memoria. Para un DOCX típico de 2 MB a 10 MB, la huella observada en memoria durante el análisis osciló entre 40 MB y 120 MB por proceso activo.
  - Con el límite de concurrencia de 2 trabajos simultáneos, el consumo adicional de memoria del backend se estima preliminarmente en $< 300\text{ MB}$ en picos de demanda.
- **Disco**:
  - Almacenamiento efímero acotado: cada trabajo retiene el DOCX de entrada (~2-10 MB), JSON (~1 MB), HTML (~1 MB) y DOCX comentado (~2-10 MB).
  - Típicamente $\le 25\text{ MB}$ por trabajo. Con 10 trabajos activos en ventana TTL de 30 minutos, la ocupación en disco temporal se estima en $\approx 250\text{ MB}$, siendo liberada de forma automática tras el vencimiento del plazo configurado.

