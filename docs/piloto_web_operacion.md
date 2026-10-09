# Piloto interno de la web determinística

## Condiciones de entrada

- Ambiente QA detrás de IIS y HTTPS; el backend sólo escucha en `127.0.0.1`.
- Windows Integrated Authentication activa y cabeceras entrantes de identidad eliminadas antes de que IIS inyecte la identidad auténtica.
- Entre 5 y 10 participantes autorizados durante dos semanas.
- Ollama, LanguageTool y cualquier API externa desactivados.
- Carpeta temporal dedicada con al menos 20 GB libres y TTL de 30 minutos.
- Responsable operativo y canal institucional de incidentes definidos.

Si IIS/WIA o el certificado aún no están disponibles, sólo puede realizarse una prueba técnica en un equipo aislado con documentos sintéticos; no se considera piloto institucional.

## Secuencia

1. Ejecutar la suite completa y guardar versión, commit y resultado.
2. Ejecutar el banco sintético y comprobar carga, consulta, visualización y las tres descargas.
3. Verificar con dos identidades que ninguna pueda consultar o descargar trabajos de la otra.
4. Procesar durante los primeros dos días exclusivamente documentos sintéticos.
5. Autorizar CRF reales sólo después de confirmar logs sin texto, limpieza TTL y aislamiento.
6. Registrar diariamente trabajos recibidos, terminados, fallidos, duración, saturaciones, descargas e incidentes. No registrar nombres de archivo ni texto documental.
7. Al término de dos semanas, cerrar el acceso, ejecutar la purga y emitir el informe de aceptación.

## Criterios de salida

| Indicador | Umbral |
|---|---:|
| Trabajos válidos terminados | al menos 95 % |
| Procesamiento determinístico p95 | máximo 30 segundos |
| Archivos vencidos eliminados | 100 % |
| Accesos entre usuarios | 0 |
| Texto o nombres de archivo en logs | 0 |
| Incidentes críticos | 0 |

Un incumplimiento de aislamiento, confidencialidad o purga detiene el piloto inmediatamente. Un problema de rendimiento o usabilidad no crítico se registra para corrección y nueva comprobación.

## Reversión

1. Retirar la publicación en IIS sin borrar evidencias técnicas autorizadas.
2. Detener el servicio backend.
3. Confirmar que no existan trabajos en estado `procesando` y purgar el almacenamiento efímero.
4. Conservar sólo métricas agregadas y bitácoras permitidas.
5. Volver al último commit aprobado; no modificar el motor determinístico durante la investigación del incidente.

## Compuerta posterior

La implementación de SQL Server comienza únicamente cuando el archivo basado en `institutional-readiness.example.json` produce un dictamen satisfactorio con:

```powershell
$env:PYTHONPATH = "src;scripts"
python scripts\check_institutional_readiness.py .\ruta\respuestas-ti.json
```
