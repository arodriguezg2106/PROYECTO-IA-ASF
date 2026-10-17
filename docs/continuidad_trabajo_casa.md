# Continuidad del proyecto en otro equipo

Estado respaldado: 16 de octubre de 2026. El repositorio contiene el código,
pruebas, catálogos, configuraciones de ejemplo y generadores de paquetes. Los
documentos y resultados institucionales no se versionan.

## Objetivo de la sesión en casa

La sesión doméstica tiene un alcance deliberadamente pequeño:

1. clonar y verificar el código publicado;
2. inventariar la PC de escritorio y su GPU sin comprar ni instalar hardware;
3. comprobar Ollama con un modelo pequeño y texto sintético;
4. ejecutar el preflight y, sólo si la memoria lo permite, las compuertas
   sintéticas del candidato de 9B;
5. guardar únicamente métricas técnicas, nunca documentos o Excel reales.

La guía paso a paso está en
[`laboratorio_ollama_equipo_casa.md`](laboratorio_ollama_equipo_casa.md). Este
documento es la lista corta para retomar sin reconstruir el contexto.

## Preparación

```powershell
git clone https://github.com/arodriguezg2106/PROYECTO-IA-ASF.git
cd PROYECTO-IA-ASF
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest -q
```

Después de clonar, `git log -1 --oneline` debe mostrar el último commit publicado
y `git status --short` debe quedar vacío. La línea base vigente es de **248
pruebas**. El modo ordinario es determinista, `final`, sin autocorrección y sin
modificar el DOCX.

Si la computadora usa Linux:

```bash
git clone https://github.com/arodriguezg2106/PROYECTO-IA-ASF.git
cd PROYECTO-IA-ASF
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest -q
```

## Datos que deben obtenerse por medios institucionales

GitHub no contiene:

- CRF reales (`*.docx`);
- fuente normativa PDF 2IN2RE01;
- libros de validación humana (`*.xlsx`);
- corpus y reportes en `results/`;
- cachés SQLite;
- Java, LanguageTool u Ollama;
- tokens o configuraciones locales.

En otro equipo institucional, esos archivos sólo se sincronizan mediante medios
autorizados. En la computadora doméstica **no se copiará ninguno**: las pruebas
de Ollama utilizarán exclusivamente los bancos sintéticos versionados.

## Estado que debe conservarse

- Motor determinístico y web: funcionales.
- LanguageTool: infraestructura implementada, pero perfil **rechazado** por
  exhaustividad 0.4737 frente al mínimo 0.75; permanece apagado.
- Ollama: fuera del MVP y sólo para investigación sintética.
- SQL Server: aplazado hasta la compuerta formal de TI.
- Banco real: bloqueado hasta completar las 26 decisiones y justificaciones de
  adjudicación en el entorno institucional.

## LanguageTool local

No es necesario instalarlo durante la sesión doméstica de Ollama. Esta sección
se conserva únicamente para reconstruir el entorno completo en otro equipo
institucional.

Instale Java 17 y LanguageTool 6.6. Las rutas se pasan como parámetros, porque las predeterminadas corresponden al equipo de desarrollo:

```powershell
.\scripts\start_languagetool.ps1 `
  -JavaExe "C:\ruta\a\java.exe" `
  -LanguageToolDir "C:\ruta\a\LanguageTool"
```

LanguageTool sólo admite loopback, permanece experimental y marca sus propuestas para revisión humana.

## Ollama

Ollama sigue integrado pero desactivado por defecto. `qwen3.5:4b` y `qwen3:8b` están rechazados para revisión ordinaria. Un modelo nuevo debe superar el banco contextual antes de aprobarse.

En la PC doméstica, `qwen3.5:4b` se usa únicamente para comprobar instalación,
API y uso CPU/GPU. No se vuelve a considerar candidato. El primer candidato a
evaluar es `qwen3.5:9b`, pero sólo se descargará después de conocer RAM, VRAM,
espacio libre y compatibilidad de la GPU.

## Orden exacto al llegar a casa

1. Clonar el repositorio y confirmar las 248 pruebas.
2. Ejecutar únicamente el inventario de la fase 1 de la guía de Ollama.
3. Anotar el modelo exacto de GPU, VRAM, módulos de RAM y espacio libre.
4. No formatear ni instalar Linux hasta revisar ese inventario.
5. Si el equipo actual es utilizable, instalar Ollama y probar `qwen3.5:4b` con
   el texto sintético indicado en la guía.
6. Ejecutar el preflight doméstico con `--preflight --synthetic-only`.
7. Descargar `qwen3.5:9b` sólo si el cuadro de decisión de hardware lo permite.
8. Detenerse ante intercambio continuo de memoria, temperatura insegura,
   reinicios o respuestas inválidas.

## Estado funcional

- Resolución de formato OOXML efectivo.
- Reglas deterministas de cifras, porcentajes, siglas, abreviaturas, redacción y cuadros.
- Reportes JSON, HTML, Markdown y SARIF.
- Formato agrupado en segundo plano; prioridad para tablas, cifras, concordancia, claridad y ortografía.
- LanguageTool local con caché sin texto y filtro ortográfico.
- Registro y compuerta de modelos contextuales.
- Banco contextual sintético y evaluación reproducible.
- Captura de decisiones humanas y dataset anonimizado para un futuro priorizador.
- Extracción real de comentarios anclados y pares antes/después del control de cambios.

`validacion_cambios_editoriales.xlsx` y la segunda revisión ya se importaron en
el entorno institucional. La adjudicación de 26 casos permanece incompleta. Ese
trabajo no se continuará en casa: la sesión doméstica termina al obtener el
inventario, la prueba técnica de Ollama y, si el hardware lo permite, el
resultado sintético de `qwen3.5:9b`.
