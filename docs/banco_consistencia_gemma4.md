# Revisión humana del banco Gemma 4

Estado: pendiente de revisión. Estos textos son sintéticos; las etiquetas son propuestas.
Revisar las 30 etiquetas, las evidencias, las justificaciones y los criterios antes de congelar.
La partición reservada no debe usarse para ajustar prompts tras comenzar la selección.

SHA-256 del banco: `f7be37a84c34a7d1a1cd8440e245e6f728720deb8d251421c3ce14a09934bc99`

## Criterios comunes

- Señalar gerundios de posterioridad sólo cuando el texto explicite que la segunda acción ocurrió después; aceptar los de modo y simultaneidad.
- Señalar redundancias demostrables, omisiones de nexos necesarios y errores de concordancia.
- Señalar referencias con dos antecedentes plausibles sin inventar quién actuó; la corrección debe ser null si requiere esa información.
- Señalar contradicciones explícitas dentro del fragmento; no inferir contradicciones por falta de contexto.
- Aceptar redacción técnica, voz pasiva justificada y textos claros; no proponer cambios por mera preferencia estilística.
- Conservar cifras, porcentajes, fechas, folios, nombres y sentido; suggested_text representa el fragmento completo corregido o null.

## Selección: 10 textos

### C01 — gerundio posterior

El comité aprobó el calendario el lunes, publicándolo el jueves siguiente.

Propuesta: **con hallazgo**.
Justificación: La publicación se presenta como posterior a la aprobación mediante fechas relativas explícitas.
Evidencia aceptable: `publicándolo el jueves siguiente`; `publicándolo`

### C02 — redundancia

El apartado presenta una síntesis resumida de las actividades de supervisión.

Propuesta: **con hallazgo**.
Justificación: Resumida repite el significado de síntesis sin introducir una distinción.
Evidencia aceptable: `síntesis resumida`

### C03 — omisión de nexo

La circular establece los responsables deben conservar los comprobantes originales.

Propuesta: **con hallazgo**.
Justificación: Falta el nexo que entre establece y la proposición subordinada.
Evidencia aceptable: `establece los responsables`; `establece los responsables deben`

### C04 — referente ambiguo

Marta entregó a Elena el dictamen y ella solicitó corregirlo.

Propuesta: **con hallazgo**.
Justificación: Ella puede referirse a Marta o a Elena; no hay evidencia para elegir una corrección.
Evidencia aceptable: `ella`; `ella solicitó corregirlo`

### C05 — coherencia

El acta declara que la sesión se celebró exclusivamente de forma presencial y que ninguno de los participantes estuvo físicamente presente.

Propuesta: **con hallazgo**.
Justificación: Las dos afirmaciones sobre la misma sesión son incompatibles dentro del propio fragmento.
Evidencia aceptable: `la sesión se celebró exclusivamente de forma presencial y que ninguno de los participantes estuvo físicamente presente`; `exclusivamente de forma presencial y que ninguno de los participantes estuvo físicamente presente`

### C06 — gerundio simultáneo válido

El analista verificó la relación de gastos cotejando cada asiento con el comprobante correspondiente.

Propuesta: **sin hallazgo**.
Justificación: Cotejando expresa el modo en que se realizó la verificación, sin posterioridad.
Evidencia aceptable: ninguna

### C07 — precisión técnica

El informe distingue los controles preventivos de los controles detectivos.

Propuesta: **sin hallazgo**.
Justificación: La repetición del sustantivo permite distinguir dos categorías técnicas y no constituye por sí sola un defecto.
Evidencia aceptable: ninguna

### C08 — nexo y folio correctos

El aviso REF-028/2026 precisa que los expedientes permanecerán en el archivo central.

Propuesta: **sin hallazgo**.
Justificación: El nexo está presente, la referencia es clara y el identificador debe conservarse.
Evidencia aceptable: ninguna

### C09 — referente explícito

Carmen remitió el borrador a Julia; esta última confirmó su recepción.

Propuesta: **sin hallazgo**.
Justificación: Esta última identifica a Julia y evita la ambigüedad de quién confirmó la recepción.
Evidencia aceptable: ninguna

### C10 — secuencia coherente

Primero se inspeccionó el almacén; después se redactó la minuta y, finalmente, se comunicaron los resultados.

Propuesta: **sin hallazgo**.
Justificación: Los marcadores temporales describen una secuencia explícita sin contradicción.
Evidencia aceptable: ninguna


## Validación reservada: 20 textos

### C11 — gerundio posterior

La oficina concluyó la visita el 06/04/2026, enviando las constancias el 09/04/2026.

Propuesta: **con hallazgo**.
Justificación: Las fechas sitúan el envío después de la visita; deben conservarse en cualquier propuesta.
Evidencia aceptable: `enviando las constancias el 09/04/2026`; `enviando`

### C12 — redundancia

El inventario contiene un total de 18 equipos en total.

Propuesta: **con hallazgo**.
Justificación: La cuantificación total se expresa dos veces; la cifra 18 debe permanecer intacta.
Evidencia aceptable: `un total de 18 equipos en total`; `en total`

### C13 — omisión de nexo

Se advirtió a las proveedoras tenían que entregar las garantías antes de la firma.

Propuesta: **con hallazgo**.
Justificación: Falta que para introducir el contenido de la advertencia.
Evidencia aceptable: `proveedoras tenían`; `a las proveedoras tenían que`

### C14 — concordancia verbal

Las cédulas de seguimiento contiene la evidencia de las visitas.

Propuesta: **con hallazgo**.
Justificación: El sujeto plural las cédulas exige contienen.
Evidencia aceptable: `contiene`; `Las cédulas de seguimiento contiene`

### C15 — concordancia nominal

La respuesta definitiva fue notificado mediante el oficio UAF-063/2026.

Propuesta: **con hallazgo**.
Justificación: El participio debe concordar en femenino con respuesta; el folio no debe modificarse.
Evidencia aceptable: `fue notificado`; `notificado`

### C16 — posesivo ambiguo

La supervisora conversó con la directora sobre las inconsistencias de su declaración.

Propuesta: **con hallazgo**.
Justificación: El posesivo puede aludir a la supervisora o a la directora; precisar a la persona requiere contexto.
Evidencia aceptable: `su declaración`

### C17 — contradicción explícita

En un mismo corte de información, el reporte califica la revisión del contrato como concluida y como no iniciada.

Propuesta: **con hallazgo**.
Justificación: Se asignan estados incompatibles a una misma revisión en un mismo corte de información.
Evidencia aceptable: `como concluida y como no iniciada`; `la revisión del contrato como concluida y como no iniciada`

### C18 — omisión de relativo

La constancia con se acreditó la entrega quedó integrada al expediente.

Propuesta: **con hallazgo**.
Justificación: Falta la que después de con para introducir la proposición relativa.
Evidencia aceptable: `con se acreditó`; `con se`

### C19 — concordancia en pasiva

Los anexos del memorando fue entregados a la unidad receptora.

Propuesta: **con hallazgo**.
Justificación: El auxiliar singular fue no concuerda con los anexos; corresponde fueron.
Evidencia aceptable: `fue entregados`; `fue`

### C20 — coherencia de alcance

El párrafo indica que todos los expedientes incluyen firma y aclara que, dentro de ese mismo conjunto, existen expedientes sin firma.

Propuesta: **con hallazgo**.
Justificación: La excepción explícita contradice el cuantificador todos aplicado al mismo conjunto.
Evidencia aceptable: `todos los expedientes incluyen firma y aclara que, dentro de ese mismo conjunto, existen expedientes sin firma`; `existen expedientes sin firma`

### C21 — gerundio modal válido

La técnica organizó las constancias clasificándolas por fecha de recepción.

Propuesta: **sin hallazgo**.
Justificación: La clasificación describe el procedimiento seguido durante la organización.
Evidencia aceptable: ninguna

### C22 — posterioridad con nexo correcto

La inspección terminó por la mañana y el acta se firmó al día siguiente.

Propuesta: **sin hallazgo**.
Justificación: Dos acciones posteriores se enlazan con verbos personales, sin gerundio impropio.
Evidencia aceptable: ninguna

### C23 — cifras y porcentaje

La cobertura registrada fue de 17.5% y el gasto comprobado ascendió a 240,000 pesos.

Propuesta: **sin hallazgo**.
Justificación: El fragmento informa dos medidas sin relacionarlas de forma contradictoria; ambas cifras deben conservarse.
Evidencia aceptable: ninguna

### C24 — fecha y referencia

El oficio DG-114/2026 se incorporó al expediente el 22/05/2026.

Propuesta: **sin hallazgo**.
Justificación: La oración identifica documento, acción y fecha con claridad.
Evidencia aceptable: ninguna

### C25 — pasiva justificada

Las instalaciones fueron afectadas por una inundación durante el cierre del ejercicio.

Propuesta: **sin hallazgo**.
Justificación: La voz pasiva mantiene el foco en las instalaciones afectadas y no constituye por sí sola una infracción.
Evidencia aceptable: ninguna

### C26 — concordancia correcta

El listado de observaciones contiene las referencias necesarias para localizar cada evidencia.

Propuesta: **sin hallazgo**.
Justificación: Contiene concuerda con el núcleo singular listado, aunque observaciones sea plural.
Evidencia aceptable: ninguna

### C27 — referencia nominal clara

La coordinadora pidió a la responsable del archivo que esta última remitiera las copias certificadas.

Propuesta: **sin hallazgo**.
Justificación: Esta última identifica explícitamente a la responsable del archivo como quien debe remitir las copias.
Evidencia aceptable: ninguna

### C28 — repetición con función técnica

La falta de evidencia no demuestra la falta de ejecución de la actividad.

Propuesta: **sin hallazgo**.
Justificación: Las dos apariciones de falta distinguen ausencia de evidencia y ausencia de ejecución.
Evidencia aceptable: ninguna

### C29 — alcance coherente

Se revisaron únicamente los contratos de obra; los contratos de servicios quedaron fuera de la muestra.

Propuesta: **sin hallazgo**.
Justificación: La segunda proposición aclara el alcance restrictivo de únicamente.
Evidencia aceptable: ninguna

### C30 — coherencia temporal

Aunque la autorización se emitió en junio, el trámite había comenzado en mayo y permaneció abierto hasta julio.

Propuesta: **sin hallazgo**.
Justificación: El inicio, la autorización y el cierre son hitos distintos con una secuencia temporal compatible.
Evidencia aceptable: ninguna
