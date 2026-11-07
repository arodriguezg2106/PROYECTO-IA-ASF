# Plan de trabajo: evaluación editorial y preparación del piloto

Fecha de referencia: 5 de noviembre de 2026.

Objetivo: determinar qué componentes aportan hallazgos útiles y verificables,
corregir las limitaciones de la evaluación y preparar el revisor para un piloto
controlado. La aplicación determinística puede avanzar mientras se evalúan los
proveedores editoriales experimentales.

Este documento prepara el trabajo. No ejecuta inferencias, cambia aprobaciones,
publica la aplicación ni autoriza nuevos envíos de documentos reales.

## Seguimiento de los ocho pasos de ejecución

Actualizado el 5 de noviembre de 2026. La tabla permite seguir los ocho pasos
acordados; las fases técnicas y sus dependencias se detallan más adelante.

| Paso | Trabajo | Estado |
|---|---|---|
| 1 | Preservar evidencias y cerrar la evaluación anterior. | **Completado**: [nota de cierre y verificación](cierre_consistencia_v1_2026-11-05.md). |
| 2 | Adjudicar los errores detectados. | Pendiente. |
| 3 | Corregir y probar el evaluador. | Pendiente. |
| 4 | Preparar y congelar el banco nuevo. | Pendiente. |
| 5 | Evaluar Gemma y compararlo con reglas ASF y LanguageTool. | Pendiente; presupuesto Cloud nuevo aún no autorizado. |
| 6 | Verificar funcionamiento, rendimiento y seguridad de la aplicación. | Pendiente sobre la versión entregable. |
| 7 | Preparar y acompañar el piloto institucional. | Pendiente de las compuertas técnicas y de TI. |
| 8 | Consolidar datos para aprendizaje y entregar el informe final. | Pendiente. |

## 1. Punto de partida comprobado

| Frente | Evidencia actual | Implicación |
|---|---|---|
| Gemma 4 31B | `consistency-v1`: 120/180 intentos; selección y validación A completas; B ausente. | Sigue **no validado**. |
| Calidad formal de A | Precisión 77.8%, exhaustividad 70%, exactitud 85%; acuerdo de decisión y regla 100% entre sus tres repeticiones. | Estabilidad dentro de A no acredita calidad ni estabilidad entre días. |
| Auditoría complementaria | C13/C20: citas más amplias que las permitidas; C11: puntuación adyacente a una fecha; C17: contradicción omitida. | Las interpretaciones del asistente necesitan adjudicación humana. La lectura alternativa 100%/90%/95% no sustituye las métricas formales. |
| Ventana de B | A terminó el 29 de octubre a las 10:42, UTC−06:00; B debía comenzar entre el 30 de octubre y el 1 de noviembre, a esa hora. | La ventana venció. Conservar v1 incompleto; no alterar fechas ni ejecutar B como continuación válida. |
| Caso de Sonora | Seis respuestas vacías, incluidas tres para el fragmento con la corrección humana de referencia. | Documentar la omisión; un caso no permite estimar calidad general. |
| LanguageTool | Banco de 90 casos: precisión 100%, exhaustividad 44.19% y cuatro propuestas clasificadas como inseguras. | Sigue rechazado y desactivado por defecto. |
| Aplicación | Motor determinístico, reglas ASF, reportes y controles web implementados; expediente de entrega con verificaciones pendientes. | Actualizar la evidencia sobre la versión que efectivamente se vaya a entregar. |
| Aprendizaje | Constructor de dataset y contrato de priorización disponibles; ningún modelo entrenado activo. | Primero reunir decisiones humanas suficientes. |

Fuentes: [informe de v1](../results/ollama_cloud/consistency-v1/report.md),
[auditoría de A](../results/ollama_cloud/consistency-v1/validation_a_audit.json),
[caso de Sonora](../results/ollama_cloud/real_case_sonora/report.md),
[expediente de entrega](entrega_demo_2026-11-02.md).
Los resultados locales están excluidos de Git y estos enlaces requieren el equipo
que conserva las evidencias.

## 2. Secuencia, responsables y entregables

Las duraciones son estimaciones de trabajo, contadas desde el inicio acordado.
La disponibilidad de revisores y TI puede ampliar el calendario.

| Fase | Trabajo | Responsable | Entregable y condición de salida | Estimación |
|---|---|---|---|---|
| 0. Preservación | Inventariar cambios pendientes; registrar commit, diferencias, hashes y resultados de v1. Crear un cierre complementario por vencimiento de B. | Desarrollo | Manifiesto y nota de cierre separados de los archivos originales; conteo de intentos conservado. | Medio día |
| 1. Adjudicación | Revisar C11, C13, C20 y C17 en sus tres repeticiones, y el par de Sonora; revisar controles sin penalización para evitar una auditoría sesgada. | Revisor editorial y desarrollo | Decisiones justificadas: fallo del modelo, del evaluador, del banco o caso indeterminado; los desacuerdos quedan resueltos o excluidos con motivo. | 1–2 días |
| 2. Evaluador corregido | Implementar un protocolo independiente, provisionalmente `consistency-v2`, con controles locales y reportes por caso y regla. | Desarrollo | Pruebas simuladas aprobadas y especificación revisada antes de consultar Cloud. | 2–3 días |
| 3. Banco y comparación | Revisar y congelar un banco nuevo; comparar reglas ASF, LanguageTool y Gemma sobre las mismas entradas sintéticas. Ejecutar Cloud por etapas. | Revisor editorial, desarrollo y usuario para control de uso | Informe de calidad y estabilidad, consumo observado y decisión por componente; sin activación automática. | 3–5 días, incluida la separación temporal |
| 4. Verificación de la aplicación | Instalación limpia, recorrido funcional, carga, aislamiento, purga y seguridad dinámica. Puede avanzar durante las fases 1–3. | Desarrollo; TI para entorno institucional | Expediente actualizado de la versión entregable y pendientes resueltos o documentados. | 2–3 días |
| 5. Piloto | Preparar QA y ejecutar el piloto determinístico con participantes autorizados. | TI, responsable operativo y revisores | Informe de aceptación, incidentes y decisión de continuidad. | Dos semanas de operación tras habilitar QA |
| 6. Datos para aprendizaje | Reunir decisiones y revisar suficiencia y particiones del dataset. | Revisores y desarrollo | Informe de preparación del dataset; entrenamiento sólo si alcanza los mínimos. | Continuo durante el piloto |

Meta orientativa: expediente técnico y evaluación editorial en aproximadamente
10–15 días hábiles. El piloto institucional y sus dependencias de TI tienen un
calendario adicional; no quedan incluidos en ese plazo.

## 3. Primera entrega: adjudicación y cierre de v1

1. Guardar un manifiesto de los artefactos existentes, con sus hashes y los
   cambios de código pendientes. No hacer un commit masivo sin revisar su alcance.
2. Preparar una ficha por caso con texto de entrada, regla esperada, respuesta
   literal, evidencia citada, propuesta y motivo de la penalización.
3. Solicitar al revisor una decisión independiente antes de mostrarle la lectura
   alternativa del asistente. Registrar la justificación y resolver desacuerdos
   mediante una segunda revisión cuando sea necesario.
4. Separar la puntuación original, la adjudicación humana y cualquier diagnóstico
   posterior. Si una etiqueta es discutible, no convertirla automáticamente en
   un acierto ni en un error del modelo.
5. Emitir `cierre_v1.md` y `adjudicacion_v1.json` bajo un directorio nuevo de
   `results/`. Conservar `experiment.json`, banco, respuestas e informes originales.

**Compuerta:** cada penalización investigada tiene una decisión o un estado
indeterminado explícito. El vencimiento temporal queda documentado y v1 mantiene
su conclusión de no validado.

## 4. Requisitos del nuevo evaluador

- **Evidencia:** exigir una cita literal del texto, relacionada con la regla y el
  problema adjudicado. Definir antes de las pruebas cómo aceptar una cita más
  amplia que incluya el fragmento pertinente; citar todo el texto no debe bastar
  para validar cualquier hallazgo. Puntuar también hallazgos adicionales erróneos.
- **Elementos protegidos:** distinguir puntuación exterior de cambios de valor.
  Cubrir cifras, signos, decimales, porcentajes, unidades, fechas y folios;
  conservar las ambigüedades como revisión pendiente, sin normalizaciones que
  oculten una alteración. La seguridad del sentido exige revisión humana.
- **Correcciones:** mantener el contrato de `suggested_text`: fragmento completo
  corregido o `null`. Separar detección correcta, corrección aceptable y
  corrección que introduce un problema nuevo.
- **Comparabilidad:** registrar hashes del banco, reglas, prompts, esquema,
  implementación, parámetros, commit y metadatos disponibles del proveedor.
  Reportar por separado las sesiones cuya configuración o modelo cambie.
- **Diario y presupuesto:** persistir cada intento antes de enviarlo y guardar
  el resultado después; reanudar sólo pendientes, sin repetir resultados fallidos
  o inciertos. Detenerse ante autenticación, cuota o transporte y evitar
  ejecuciones concurrentes.
- **Pruebas antes de Cloud:** respuestas siempre vacías, falsas alarmas constantes,
  decisiones alternantes, JSON inválido, evidencia inventada o irrelevante,
  citas amplias válidas e inválidas, puntuación junto a números, alteraciones
  reales de valores, presupuesto agotado, caída y reanudación sin duplicados.

La implementación nueva irá en archivos independientes o preservará una copia
reproducible de v1 antes de compartir código. No se recalificarán los resultados
históricos como si se hubieran obtenido bajo v2.

## 5. Banco nuevo y diseño propuesto para Cloud

Preparar 30 textos sintéticos independientes y revisados: 15 con problemas y 15
correctos; 10 para selección (5 y 5) y 20 reservados (10 y 10). Cubrir gerundios,
redundancias, omisiones gramaticales, ambigüedad, coherencia y controles de cifras,
fechas y folios. Cada caso tendrá regla, justificación y evidencias aceptables.

Los casos conocidos de v1 y Sonora sirven para desarrollar y comprobar el
evaluador. No se reutilizan como validación reservada ni mediante simples cambios
de nombres o cifras. Agrupar por origen los textos derivados de una misma fuente
para que no queden repartidos entre desarrollo y validación. Revisar y congelar
las etiquetas antes de cualquier inferencia.

Comparar inicialmente los dos prompts existentes con reglas, esquema y protección
equivalentes. Cualquier ajuste se limita al conjunto de desarrollo; al abrir el
reservado quedan congelados prompts y evaluador.

| Etapa propuesta | Diseño | Máximo de intentos nuevos |
|---|---|---:|
| Selección | 10 casos × 3 repeticiones × 2 prompts | 60 |
| Validación A | 20 reservados × 3 repeticiones del prompt elegido | 60 |
| Validación B | Los mismos 20 × 3 repeticiones, entre 24 y 72 horas después de A | 60 |
| Total | Tres ejecuciones separadas | 180 |

Este presupuesto es una propuesta para una evaluación nueva. Los 60 intentos
no utilizados de v1 no se transfieren ni justifican reiniciar su diario.
Antes de enviar solicitudes se debe aprobar expresamente el nuevo máximo.
Preparar banco, código, adjudicación y pruebas locales no consume API.

Mantener `gemma4:31b`, temperatura 0, semilla 20260923, razonamiento desactivado,
máximo de 2048 tokens y conversación nueva por solicitud. Barajar el orden con
semillas reproducibles. Confirmar soporte y metadatos antes de comenzar; si las
capacidades cambian, resolver el protocolo antes de congelarlo. Pedir JSON y
validarlo localmente, sin presumir generación restringida por esquema.

Elegir sólo un prompt que pase en cada repetición; desempatar por exhaustividad,
precisión y tokens reportados, en ese orden. Si ninguno pasa, detener tras
selección. Revisar el indicador Free entre etapas y registrar lo que el usuario
observe; tokens y porcentaje no prueban un precio ni un saldo disponible.
Coordinar B antes de iniciar A; si vence su ventana, cerrar como incompleto.

### Criterios de aceptación

- Precisión ≥90%, exhaustividad ≥85% y exactitud ≥90% en cada repetición final.
- Acuerdo de decisión y conjunto de reglas ≥95%: al menos 19 de 20 casos iguales
  en las seis repeticiones de validación A y B.
- Cero respuestas inválidas y cero sugerencias que alteren elementos protegidos.
- Evidencia literal pertinente; severidad, evidencia y correcciones con
  estabilidad reportada por separado.
- Sin detecciones: precisión no calculable y exhaustividad cero; nunca aprobado.

## 6. Comparar componentes sin confundir su cobertura

Ejecutar reglas ASF y LanguageTool localmente sobre el mismo banco sintético de
la fase 3; reutilizar las respuestas de Gemma para no añadir solicitudes Cloud.
Congelar también versiones y configuración de los proveedores locales.

Presentar por componente y por familia de problemas: aciertos, omisiones, falsas
alarmas, correcciones aceptables, propuestas inseguras, tiempo y cobertura
declarada. Calcular tanto el resultado global sobre el banco como el resultado
sobre el alcance común fijado antes de observar respuestas. No excluir omisiones
después para favorecer a un proveedor.

Medir una combinación de componentes sólo si se fija previamente su política de
unión, conflictos y duplicados. Una mejor puntuación combinada no aprueba por sí
sola cada proveedor ni habilita autocorrección.

Los pares reales adjudicados pueden aportar una evaluación local adicional de
los componentes compatibles. No equiparar ese resultado con el obtenido por
Gemma sobre textos sintéticos. Un nuevo envío de texto real a Cloud requiere
revisión del contenido y autorización específica para ese lote.

Conclusiones permitidas: **no validado**, **estable pero insuficiente**,
**útil pero inestable** o **candidato consistente para piloto sintético**.
La aprobación institucional es una decisión posterior.

## 7. Preparación de la aplicación y piloto

Actualizar el [expediente de entrega](entrega_demo_2026-11-02.md) sobre una versión
identificada y revisada: suite apropiada, instalación limpia, cuatro casos de
demo, reportes descargables y conservación del DOCX original. No trasladar
automáticamente la evidencia de CI de octubre al código pendiente actual.

Completar pruebas de carga y seguridad: éxito ≥95% entre trabajos válidos
admitidos, p95 determinístico ≤30 segundos, saturación controlada, cero accesos
entre usuarios y eliminación del 100% de archivos vencidos. Ejecutar DAST local;
resolver o justificar hallazgos medios y no aceptar críticos o altos.

Para el piloto institucional seguir [piloto_web_operacion.md](piloto_web_operacion.md):
QA con IIS/WIA y HTTPS, responsable operativo, 5–10 participantes durante dos
semanas y proveedores experimentales apagados. Sin ese entorno, realizar sólo
pruebas técnicas sintéticas locales. SQL Server y la cola durable quedan para la
compuerta posterior de TI.

## 8. Datos para aprendizaje y cierre del plan

Recoger decisiones humanas vinculadas al hash del documento y construir el
dataset sin texto documental. Comprobar al menos 300 decisiones utilizables,
30 documentos, 50 ejemplos por etiqueta y presencia en entrenamiento,
calibración y prueba; todas las ocurrencias de un documento van a la misma
partición. Si no alcanza, continuar recabando datos sin entrenar por cumplir fecha.

El futuro experimento sólo priorizará la revisión humana y deberá superar una
línea base en documentos reservados. No podrá cambiar mensaje, severidad,
corrección ni estado del hallazgo.

El cierre entregará: adjudicación humana y cierre de v1, especificación y pruebas
de v2, banco revisado, informes Markdown/JSON por componente, registro de uso
observado, expediente de la aplicación y recomendación de piloto. Los textos
reales y decisiones identificables permanecerán en almacenamiento local protegido;
en Git sólo código, documentación, casos sintéticos y métricas agregadas.

**Primer bloque ejecutable:** fases 0 y 1. Preparar evidencia y fichas de revisión,
sin consumir API ni cambiar la aplicación o el registro de modelos.
