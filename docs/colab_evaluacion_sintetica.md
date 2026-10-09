# Ruta segura para evaluar un modelo en Google Colab

Google Colab sirve aquí únicamente como filtro preliminar con GPU y casos
sintéticos. No sustituye la evaluación institucional ni autoriza un modelo para
procesar CRF reales.

## Antes de abrir la libreta

Los cambios que incorporan `--synthetic-only` y la libreta deben estar
publicados en la rama `main` del repositorio. Mientras permanezcan sólo en un
commit local, el enlace de Colab seguirá viendo la versión anterior.

Ruta directa, después de publicar:

<https://colab.research.google.com/github/arodriguezg2106/PROYECTO-IA-ASF/blob/main/notebooks/evaluacion_sintetica_colab.ipynb>

## Ejecución

1. Abra el enlace y seleccione **Entorno de ejecución → Cambiar tipo de entorno
   de ejecución → GPU**.
2. Ejecute las celdas en orden. La primera detiene el proceso si Colab no asignó
   una GPU.
3. La libreta clona una copia limpia del repositorio, instala Ollama, descarga
   `qwen3.5:9b` y ejecuta tres veces las compuertas sintéticas de 2, 10 y 30
   casos.
4. Descargue el JSON agregado. Debe indicar
   `evaluation_scope: synthetic_screening_only`, mantener `selected_model` en
   `null` y, si supera los umbrales, llenar únicamente `screened_model`.
5. Para probar `gemma3:12b`, primero cierre esta evaluación y ejecute otra sesión
   controlada adaptando sólo el identificador de modelo; no mezcle resultados.

## Prohibiciones de datos

No monte Google Drive y no cargue:

- documentos CRF o DOCX institucionales;
- los Excel de validación;
- bancos pareados reales;
- las carpetas `results/`, `data/` o copias de trabajo;
- nombres, cifras, folios o fragmentos institucionales.

La VM de Colab es externa y efímera. La disponibilidad y el tipo de GPU no están
garantizados. Si el modelo supera esta ronda, todavía debe repetirse dentro de
infraestructura institucional con el banco real adjudicado antes de poder quedar
como `approved`.
