# Operación y liberación institucional

Este procedimiento comienza únicamente después de que `check_institutional_readiness.py` concluya sin bloqueos. No sustituye las aprobaciones de TI, Ciberseguridad, Privacidad y Archivo.

## Promoción de ambientes

1. **DEV:** pruebas sintéticas, migraciones reversibles y proveedores falsos. No se conecta a datos de producción.
2. **QA:** IIS/WIA, certificado institucional, SQL Server de QA y almacenamiento efímero independiente. Ejecuta UAT y el piloto controlado.
3. **PROD:** despliegue del mismo artefacto aprobado en QA; sólo cambian secretos y endpoints administrados externamente.

No se reutilizan bases, carpetas temporales, cuentas de servicio ni secretos entre ambientes. La aplicación escucha en loopback y el único ingreso permitido es el proxy institucional.

## Comprobaciones previas

- Commit y versión coinciden con el artefacto aprobado; árbol de Git limpio.
- Suite completa y migración hacia delante/rollback aprobadas en QA.
- Restauración de respaldo probada y documentada por TI.
- Cuenta de servicio restringida al esquema `crf`, sin `db_owner` ni `sysadmin`.
- Conexión SQL con `Encrypt=yes` y `TrustServerCertificate=no`.
- IIS elimina cabeceras de identidad recibidas del cliente e inyecta la identidad autenticada.
- WAF permite 25 MB y 120 segundos; sólo HTTPS está publicado.
- Ollama y LanguageTool permanecen desactivados salvo aprobación independiente.

## Monitoreo mínimo

Las métricas no deben contener nombres de archivo ni texto de documentos:

- trabajos recibidos, terminados, fallidos y rechazados;
- duración p50/p95 y profundidad de cola;
- respuestas 401, 403, 413, 429/503 y 5xx;
- descargas por tipo de artefacto;
- purgas ejecutadas, fallidas y bytes temporales en uso;
- trabajos recuperados como fallidos después de un reinicio;
- decisiones humanas por estado, sin comentarios libres en telemetría.

Alertas críticas: acceso cruzado entre usuarios, texto documental en logs, fallo de purga, certificado vencido, pérdida de conexión SQL o modificación de bitácoras append-only.

## Despliegue gradual

1. Publicar con acceso restringido al equipo administrador y ejecutar un documento sintético.
2. Habilitar dos revisores durante un día y comprobar propiedad, descargas y TTL.
3. Ampliar a los participantes del piloto; observar una semana controlada.
4. Liberar al grupo institucional autorizado sólo si no hay incidentes críticos y el éxito es al menos 95 %.

## Reversión

1. Retirar el sitio de IIS o bloquear nuevos trabajos.
2. Permitir terminar trabajos activos durante la ventana autorizada; después marcar los interrumpidos como fallidos.
3. Volver al artefacto anterior sin revertir manualmente tablas.
4. Aplicar el downgrade Alembic probado únicamente con autorización de TI y respaldo verificado.
5. Purgar archivos efímeros; conservar eventos y decisiones según la política aprobada.
6. Registrar el incidente sin incluir contenido documental.

## Evidencia de aceptación

El expediente de liberación debe contener versión, commit, resultado de pruebas, dictamen de compuerta, evidencia de UAT, resultado de restauración, métricas de la semana controlada, incidentes y firmas de aprobación. Ningún CRF ni Excel de validación se incorpora al repositorio.
