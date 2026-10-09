# Continuidad del proyecto en otro equipo

Estado respaldado: 25 de septiembre de 2026. El repositorio contiene el código, pruebas, catálogos, configuraciones de ejemplo y generadores de paquetes. Los documentos y resultados institucionales no se versionan.

## Preparación

```powershell
git clone https://github.com/arodriguezg2106/PROYECTO-IA-ASF.git
cd PROYECTO-IA-ASF
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r requirements-reporting.txt
pytest -q
```

La línea base vigente es de 191 pruebas. El modo ordinario es determinista, `final`, sin autocorrección y sin modificar el DOCX.

## Datos que deben obtenerse por medios institucionales

GitHub no contiene:

- CRF reales (`*.docx`);
- fuente normativa PDF 2IN2RE01;
- libros de validación humana (`*.xlsx`);
- corpus y reportes en `results/`;
- cachés SQLite;
- Java, LanguageTool u Ollama;
- tokens o configuraciones locales.

En otro equipo, sincronice las CRF mediante OneDrive institucional y conserve la fuente normativa en una ubicación local autorizada. No copie estos archivos a una carpeta seguida por Git.

## LanguageTool local

Instale Java 17 y LanguageTool 6.6. Las rutas se pasan como parámetros, porque las predeterminadas corresponden al equipo de desarrollo:

```powershell
.\scripts\start_languagetool.ps1 `
  -JavaExe "C:\ruta\a\java.exe" `
  -LanguageToolDir "C:\ruta\a\LanguageTool"
```

LanguageTool sólo admite loopback, permanece experimental y marca sus propuestas para revisión humana.

## Ollama

Ollama sigue integrado pero desactivado por defecto. `qwen3.5:4b` y `qwen3:8b` están rechazados para revisión ordinaria. Un modelo nuevo debe superar el banco contextual antes de aprobarse.

## Regenerar los artefactos principales

```powershell
$env:PYTHONPATH = "src;scripts"
$crfRoot = "C:\ruta\institucional\CRF-ejemplos"

python scripts\pilot_editorial_crf.py $crfRoot `
  --output results\editorial_pilot `
  --sample-size 5 --language-tool --resume

python scripts\build_coherence_validation_handoff.py $crfRoot `
  --output results\paquete_validacion_coherencia --cases 40

python scripts\build_revision_evidence_handoff.py $crfRoot `
  --corpus results\editorial_revision_corpus `
  --output results\paquete_validacion_cambios_editoriales --cases 40
```

El último generador reconstruye el corpus local de comentarios y control de cambios. El corpus contiene texto institucional y no debe subirse a GitHub ni compartirse fuera de medios autorizados.

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

`validacion_cambios_editoriales.xlsx` se recibió el 9 de octubre de 2026. Sus etiquetas se importan localmente con `scripts/import_revision_validation.py`; 31 de 40 casos quedaron elegibles como referencias de evaluación. El libro contiene una edición adicional en una columna fija, registrada con trazabilidad y sin reemplazar la evidencia canónica. La siguiente fase consiste en convertir las referencias aprobadas en casos de evaluación reproducibles y probar un modelo contextual candidato sobre diez casos difíciles antes de ejecutar la batería completa.
