# Continuidad del proyecto en casa

Respaldo: **13 de noviembre de 2026**. Rama: `respaldo/casa-2026-11-13`.
Base anterior: `7e3e59b`, del 6 de noviembre de 2026 (rama `respaldo/casa-2026-11-06`).

El respaldo contiene código, pruebas, catálogos sintéticos, configuraciones de
ejemplo y documentación. Los documentos reales, libros, resultados y claves
permanecen fuera de GitHub. No es una versión institucional aprobada.

## Recuperar el respaldo en Windows

Para una instalación nueva, desde la carpeta donde se quiera guardar el proyecto:

```powershell
git clone --branch respaldo/casa-2026-11-13 https://github.com/arodriguezg2106/PROYECTO-IA-ASF.git
cd PROYECTO-IA-ASF
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt -r requirements-reporting.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest -q
git log -1 --oneline
git status --short
```

Se puede usar Python 3.14 en lugar de 3.11. La comprobación local del 6 de
noviembre se realizó con Python 3.14.0: **323 pruebas aprobadas en 122.80 s**.
La ejecución actual en Python 3.11 está pendiente. No se necesita activar el
entorno ni cambiar la política de ejecución de PowerShell.

Si ya existe un clon, guardar primero sus cambios propios y después ejecutar:

```powershell
git fetch origin
git switch respaldo/casa-2026-11-13
git pull --ff-only
```

No usar `reset --hard`, `clean` ni sobrescribir cambios del equipo doméstico.
Para continuar sobre una rama de trabajo nueva:

```powershell
git switch -c trabajo/casa-2026-11
```

En Linux se puede utilizar `python3 -m venv .venv` y sustituir
`.\.venv\Scripts\python.exe` por `.venv/bin/python` en los comandos Python.

## Estado que debe conservarse

- Motor determinista, lector DOCX, reglas editoriales parciales, reportes y
  controles web implementados. El original se conserva y no hay autocorrección.
- Cuatro casos sintéticos de demostración comprobados nuevamente.
- Banco editorial determinista: 35 casos, 23 detecciones correctas, cero falsos
  positivos y cero omisiones sobre ese banco. No acredita cobertura general.
- Flujo CLI comprobado con JSON, HTML, Markdown, SARIF y copia DOCX comentada.
- Banco real: 16 pares/32 ejemplos y 15 exclusiones. La adjudicación anterior de
  26 casos ya está importada en el entorno institucional; no hay que repetirla.
- LanguageTool permanece rechazado y apagado: evaluación histórica de 90 casos,
  precisión 1.0, exhaustividad 0.4419 y cuatro propuestas inseguras.
- Los modelos editoriales locales evaluados siguen rechazados o experimentales.
  No reiniciar como candidatos Qwen 9B o Gemma 12B por seguir una guía antigua.
- Gemma 4 31B, `consistency-v1`: 120 de 180 intentos; validación B no ejecutada.
  La evaluación fue cerrada incompleta por vencimiento de su ventana. Conclusión:
  no validado. No reanudar B ni reiniciar el diario desde este clon.
- La preservación y el cierre de v1 del 5 de noviembre están completados. La
  adjudicación humana de sus penalizaciones sigue pendiente; es un trabajo
  distinto de la adjudicación del banco real anterior.
- SQL Server y cola durable aplazados a una fase posterior al piloto y a las
  decisiones de TI. No hay modelo de aprendizaje entrenado activo.

## Siguiente trabajo útil

El frente de primera entrega puede avanzar separado de la investigación de IA:

1. Acordar alcance y aceptación de una entrega local determinista.
2. Revisar instalación limpia, rendimiento, aislamiento, purga y seguridad
   dinámica sobre una versión identificada. Las 323 pruebas no sustituyen esas
   comprobaciones ni una inspección visual en Microsoft Word.
3. Mejorar instrucciones de uso y preparar un paquete reproducible.
4. Para investigación, preparar metodología y pruebas locales del evaluador
   nuevo. Los casos conocidos sirven para desarrollo; no son banco reservado.

La revisión de 30 registros numéricos, la adjudicación de C11/C13/C17/C20 y
Sonora, y cualquier validación de documentos reales requieren los materiales y
el contexto autorizados del entorno institucional. La muestra numérica revisada
el 6 de noviembre conserva sus campos humanos vacíos.

Referencias actuales:

- [Plan de validación editorial](plan_trabajo_validacion_editorial_2026-11.md).
- [Cierre de consistency-v1](cierre_consistencia_v1_2026-11-05.md).
- [Expediente de entrega](entrega_demo_2026-11-02.md).
- [Condiciones del piloto institucional](piloto_web_operacion.md).
- [Revisión editorial y límites](revision_editorial_asf.md).

Las guías antiguas de laboratorio conservan antecedentes. Su orden de trabajo y
sus métricas anteriores no sustituyen este estado actualizado.

## Prueba sintética sin servicios externos

```powershell
$env:PYTHONPATH = 'src;scripts'
.\.venv\Scripts\python.exe scripts/verify_direction_demo.py
.\.venv\Scripts\python.exe scripts/evaluate_editorial.py --regenerate
```

Los generadores crean documentos inventados y resultados locales excluidos de
Git. Para iniciar la demostración web determinista:

```powershell
.\scripts\start_local_demo.ps1
```

No se requieren Ollama, LanguageTool, GPU, SQL Server ni claves para estos pasos.
La investigación Cloud no se inicia automáticamente. El nuevo presupuesto de
inferencia del plan de noviembre está pendiente de autorización.

## Materiales que no forman parte del respaldo

- CRF reales, documentos de entrada y PDF normativo.
- Libros de validación humana, corpus y bancos con texto institucional.
- `results/`, incluida la preservación local completa de v1 y la evidencia del
  diagnóstico del 6 de noviembre. Las notas y métricas resumidas sí están en docs.
- Cachés, bases SQLite, entornos virtuales y dependencias instaladas.
- Java, LanguageTool, modelos de Ollama y claves o configuraciones locales.

En casa se trabaja con código y datos sintéticos. Los materiales institucionales
se conservan y respaldan por los medios autorizados correspondientes.
