# Evaluación controlada de LanguageTool

LanguageTool 6.6 complementa las reglas ASF únicamente si una lista blanca
reproducible supera la compuerta. Ollama queda fuera del MVP y LanguageTool no
se conecta a la API pública: el endpoint debe estar en loopback.

## Estado actual

La evaluación sintética del 16 de octubre de 2026 utilizó 80 casos y dos
repeticiones. El descubrimiento obtuvo precisión 1.0, exhaustividad 0.6053,
cero falsos positivos, acuerdo 1.0, cero respuestas inválidas y cero propuestas
inseguras. Sólo quedaron como candidatas:

- `MORFOLOGIK_RULE_ES`;
- `COMMA_PARENTHESIS_WHITESPACE`.

Al limitar la ejecución a esas dos reglas, la compuerta sintética obtuvo
precisión 1.0 y exhaustividad 0.4737. No alcanzó el mínimo de 0.75.

La evaluación se repitió el 22 de octubre con el banco real adjudicado: 90
casos totales, incluidas 10 observaciones reales compatibles (5 pares). En modo
`gate` obtuvo 19 verdaderos positivos, 0 falsos positivos, 24 falsos negativos
y 47 verdaderos negativos: precisión 1.0, exhaustividad 0.4419, tasa de falsos
positivos 0, acuerdo 1.0, cero respuestas inválidas y 4 propuestas inseguras.
Por tanto, **LanguageTool permanece desactivado en la web**. El perfil es
`rejected` y no se redujeron los umbrales.

## Bancos y privacidad

- `tests/data/languagetool_synthetic.json`: 30 pares inventados y versionables.
- Banco editorial sintético existente: se incluyen únicamente casos compatibles.
- Banco real pareado: 16 pares/32 ejemplos, conservado bajo `results/`. Sólo 5
  pares corresponden a ortografía o gramática y son compatibles con esta
  evaluación.

Los reportes guardan identificadores, reglas, hashes y métricas, pero no el
texto de los casos. Un mínimo de 10 pares reales de ortografía o gramática es
obligatorio para aprobar el proveedor para piloto institucional.

## Ejecución

Iniciar LanguageTool y preparar el banco editorial sintético existente:

```powershell
.\scripts\start_languagetool.ps1 `
  -JavaExe "C:\ruta\a\java.exe" `
  -LanguageToolDir "C:\ruta\a\LanguageTool"

$env:PYTHONPATH = "src;scripts"
python scripts\evaluate_editorial.py --regenerate
```

Descubrimiento:

```powershell
python scripts\evaluate_languagetool.py `
  --mode discovery `
  --bank tests\data\languagetool_synthetic.json `
  --bank results\editorial_validation\bank\manifest.json `
  --output results\languagetool\discovery.json `
  --profile-output results\languagetool\candidate-profile.json
```

Compuerta con el perfil candidato versionado:

```powershell
python scripts\evaluate_languagetool.py `
  --mode gate `
  --bank tests\data\languagetool_synthetic.json `
  --bank results\editorial_validation\bank\manifest.json `
  --profile tests\data\languagetool_candidate_profile.json `
  --output results\languagetool\gate.json `
  --profile-output results\languagetool\gate-profile.json
```

Para repetir la evaluación local con el banco real se añade otro argumento:

```powershell
--bank results\editorial_revision_validation\paired_evaluation_bank.json
```

Detener el servidor:

```powershell
.\scripts\stop_languagetool.ps1
```

## Activación

El modo experimental de descubrimiento conserva
`--editorial-experimental-provider`. La ejecución normal exige
`language_tool_profile_path` apuntando a un perfil `approved_for_demo` o
`approved_for_pilot`; un perfil `candidate` o `rejected` se rechaza.

La web usa las variables `REVISOR_WEB_EDITORIAL_ENABLED`,
`REVISOR_WEB_LANGUAGETOOL_ENABLED`, `REVISOR_WEB_LANGUAGETOOL_PROFILE` y
`REVISOR_WEB_LANGUAGETOOL_URL`. LanguageTool exige además un único trabajo
concurrente. Mientras no haya perfil aprobado, sólo puede habilitarse la
revisión editorial determinística:

```powershell
.\scripts\start_local_demo.ps1 -Editorial
```

Las sugerencias lingüísticas siempre requieren decisión humana, aparecen en
una sección independiente del HTML y nunca generan comentarios de Word.
