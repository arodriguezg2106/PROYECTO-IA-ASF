# Evaluación de integración directa con Microsoft Word

Fecha de evaluación: 20 de septiembre de 2026.

## Decisión

Mantener como solución operativa inmediata las copias `*_REVISION_IA.docx` con comentarios anclados y evaluar un complemento de panel lateral de Word como una segunda fase independiente.

No se recomienda depender de un enlace `ms-word:` para orientar al revisor: puede abrir el documento, pero no ofrece una navegación estable y trazable hasta una celda o párrafo específico. Tampoco se recomienda automatización COM/VSTO para esta etapa, porque limitaría la solución al Word de escritorio en Windows y aumentaría el costo de instalación, firma y soporte.

## Alternativa recomendada para una segunda fase

Un complemento de panel lateral podría:

- cargar el JSON de revisión correspondiente al documento;
- mostrar y filtrar las alertas dentro de Word;
- buscar el `texto_busqueda` de una alerta y seleccionar el rango encontrado;
- leer y administrar comentarios del documento;
- registrar la decisión humana y exportarla al mismo esquema de decisiones;
- validar el SHA-256 o un identificador documental antes de relacionar resultados.

La API JavaScript de Word permite buscar texto en el cuerpo y seleccionar rangos, y dispone de una API de comentarios desde `WordApi 1.4`. Sin embargo, el soporte varía por versión y plataforma mediante conjuntos de requisitos. Además, un complemento de Office contiene una aplicación web y requiere un método institucional de publicación o implementación.

## Condiciones para iniciar el prototipo

1. Confirmar las versiones de Word usadas por los revisores y la disponibilidad de `WordApi 1.4` o posterior.
2. Definir si el entorno institucional permite alojar internamente los archivos del complemento y la biblioteca requerida por Office.
3. Acordar con TI el método de instalación: carga lateral solo para desarrollo y despliegue administrado para producción.
4. Usar documentos de prueba, nunca originales, durante el prototipo.
5. Mantener el motor determinístico como proceso local separado; el complemento solo presentará resultados y capturará decisiones.
6. Ejecutar un piloto con cinco revisores y medir tiempo para localizar evidencia, tasa de localización correcta y problemas de compatibilidad.

## Criterio de avance

Construir el complemento solo si la prueba con los cinco HTML y DOCX comentados muestra que los comentarios no reducen suficientemente el tiempo de localización, o si se necesita una bandeja única de alertas y decisiones dentro de Word. Hasta entonces, la copia comentada ofrece la mejor relación entre orientación, trazabilidad y riesgo de despliegue.

## Referencias oficiales

- [API `Word.Body`: búsqueda de texto y selección de rangos](https://learn.microsoft.com/en-us/javascript/api/word/word.body?view=word-js-preview)
- [API de comentarios de Word](https://learn.microsoft.com/en-us/javascript/api/word/word.commentcollection?view=word-js-preview)
- [Versiones y conjuntos de requisitos de Office](https://learn.microsoft.com/en-us/office/dev/add-ins/develop/office-versions-and-requirement-sets)
- [Publicación e implementación de complementos de Office](https://learn.microsoft.com/en-us/office/dev/add-ins/publish/publish)
- [Requisitos de implementación centralizada](https://learn.microsoft.com/es-es/microsoft-365/admin/manage/centralized-deployment-of-add-ins?view=o365-worldwide)
