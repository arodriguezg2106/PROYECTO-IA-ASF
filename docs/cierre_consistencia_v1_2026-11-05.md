# Punto 1 completado: preservación y cierre de consistency-v1

Fecha: 5 de noviembre de 2026. Estado del trabajo: **completado**.
Estado administrativo de la evaluación: **cerrada incompleta**.
Conclusión original del modelo: **no validado**.

## Motivo del cierre

El diario contiene 120 intentos únicos de un máximo de 180: 60 de selección y
60 de validación A, todos con estado `received`. No hay intentos de validación B.
A terminó el 29 de octubre de 2026 a las 10:42:04.943433, UTC−06:00. La ventana
para iniciar B fue del 30 de octubre al 1 de noviembre, a esa misma hora.
El plazo venció; no se ejecutó B ni se alteraron fechas o controles temporales.

El cierre es un registro complementario. El diario y los informes originales
permanecen intactos, con precisión formal de A de 77.8%, exhaustividad de 70% y
exactitud de 85%. El acuerdo de decisión y regla de 100% sólo describe las tres
repeticiones de A; no acredita estabilidad entre días ni aprobación.

Los 60 intentos no utilizados no se transfieren a otro experimento. Las seis
solicitudes del caso de Sonora se conservan como antecedente independiente y no
se suman al presupuesto de v1. Este trabajo realizó **cero inferencias nuevas**.

## Evidencia preservada y comprobada

Paquete local:
[`results/ollama_cloud/consistency-v1_cierre_20261105/`](../results/ollama_cloud/consistency-v1_cierre_20261105/).
Contiene texto del caso real autorizado; permanece excluido de Git.

| Artefacto | Contenido y comprobación |
|---|---|
| `evidence/` | 30 copias de archivos Cloud y LanguageTool, cotejadas byte a byte mediante SHA-256; v1 y antecedentes identificados por separado. |
| `working_tree.zip` | 172 archivos del árbol de trabajo: 157 registrados en Git y 15 nuevos. Incluye el evaluador todavía no registrado. Cada miembro se verificó contra el hash del archivo original. |
| `committed_HEAD.zip` | Los 157 archivos del commit `000d8e5b584a81664ddcb25a1c5287331137264a`. Ambos ZIP superaron la comprobación CRC. |
| Parches y estados Git | Diferencias contra HEAD, diferencias preparadas y estado del árbol; no se creó un commit ni se prepararon archivos. |
| `inventario_codigo.json` | Rutas, tamaños y hashes; commit y versiones del entorno. |
| `cierre_v1.json` y `cierre_v1.md` | Motivo del cierre, fechas, conteo de intentos y alcance. |
| `manifest.json` y `SHA256SUMS.txt` | Inventario y hashes para comprobar las copias y el propio manifiesto. |
| `verificacion.json` | Resultado de los controles de integridad y correspondencia con la configuración congelada. |

Se confirmó que el hash canónico de la configuración, el banco congelado, el
banco fuente, los cuatro archivos de implementación y el commit corresponden
al experimento registrado. El conteo del informe coincide con el diario y no
hay identificadores de intento duplicados. Los archivos originales y el estado
de Git no cambiaron durante la preservación.

El paquete captura el árbol anterior a esta nota de seguimiento. Es una copia
local en el mismo equipo, no un respaldo externo ni un sello de tiempo de una
tercera parte.

## Pendiente para el punto 2

Adjudicar las penalizaciones de C11, C13 y C20, la omisión de C17 y el par de
Sonora, incorporando controles sin penalización. La auditoría técnica del
asistente sigue pendiente de revisión humana. No se recalificaron resultados,
modificó la aplicación ni cambió el registro de aprobación de modelos.

El siguiente trabajo se rige por el
[plan de validación editorial](plan_trabajo_validacion_editorial_2026-11.md).
