"""Salida Markdown local con la revisión editorial independiente."""
from pathlib import Path

def _cell(value): return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")

def render_markdown(report):
    ed=report.get("editorial_review")
    lines=["# Revisión CRF", "", f"Documento: `{_cell(report.get('source',{}).get('file'))}`", ""]
    if not ed: return "\n".join(lines+["La revisión editorial ASF no fue activada.",""])
    model=ed.get("ollama",{}).get("model") or {}
    model_label=f"{model.get('model_id')} ({model.get('status')})" if model else "desactivado"
    lt=ed.get("language_tool",{})
    lt_label=lt.get("status", "desactivado") if lt.get("enabled") else "desactivado"
    summary=ed["summary"]
    lines += ["## Revisión editorial ASF", "", f"Catálogo: `{ed['catalog_version']}` · Modelo contextual: `{model_label}` · LanguageTool: `{lt_label}` · Tiempo: {ed['duration_seconds']:.3f} s", "", f"Observaciones sustantivas: {summary.get('substantive_findings', summary['findings'])} · Formato: {summary.get('format_occurrences', 0)} ocurrencias en {summary.get('groups_by_focus', {}).get('format', 0)} grupos · Propuestas rechazadas: {summary['rejected_suggestions']}", "", "> Prioridad: tablas, cifras, concordancia, claridad y ortografía. El formato se reporta agrupado y en segundo plano.", "", "| Severidad | Conteo |", "|---|---:|"]
    lines += [f"| {_cell(k)} | {v} |" for k,v in sorted(ed["summary"]["by_severity"].items())]
    lines += ["", "### Concordancia, claridad, ortografía y consistencia", "", "| Regla | Severidad | Método | Ubicación | Mensaje | Fundamento |", "|---|---|---|---|---|---|"]
    for f in ed["findings"]:
        if f.get("review_focus") != "format": lines.append(f"| {_cell(f['rule_id'])} | {_cell(f['severity'])} | {_cell(f['detection_method'])} | {_cell(f['location']['paragraph_id'])} | {_cell(f['message'])} | {_cell(f['source_section'])}, p. {f['source_page']} |")
    format_groups={}
    for f in ed["findings"]:
        if f.get("review_focus") == "format":
            key=(f["rule_id"],f["message"],f["evaluation_status"])
            format_groups.setdefault(key,[]).append(f)
    lines += ["", "### Formato agrupado", "", "| Regla | Estado | Ocurrencias | Mensaje | Ejemplos de ubicación |", "|---|---|---:|---|---|"]
    for (rule,message,status),items in sorted(format_groups.items()):
        locations=", ".join(str(item["location"]["paragraph_id"]) for item in items[:3])
        lines.append(f"| {_cell(rule)} | {_cell(status)} | {len(items)} | {_cell(message)} | {_cell(locations)} |")
    lines += ["", "### Cobertura por regla", "", "| Regla | Estado | Hallazgos | Fundamento |", "|---|---|---:|---|"]
    for rid,item in sorted(ed.get("coverage",{}).items()): lines.append(f"| {_cell(rid)} | {_cell(item['status'])} | {item['findings']} | {_cell(item['source_section'])}, p. {item['source_page']} |")
    lines += ["", "### Glosario de siglas", "", "| Sigla | Denominación | Primera ubicación | Estado |", "|---|---|---|---|"]
    for item in ed.get("acronym_glossary",[]): lines.append(f"| {_cell(item['acronym'])} | {_cell(item.get('denomination'))} | {_cell(item['first_location'])} | {_cell(item['status'])} |")
    lines += ["", "### Reglas no evaluables", ""]
    lines += [f"- `{x['rule_id']}` ({x['source_section']}, p. {x['source_page']}): {x['reason']}" for x in ed["rules_not_evaluable"]] or ["- Ninguna."]
    lines += ["", "### Reglas y ubicaciones excluidas", ""]
    excluded_lines=[]
    for x in ed.get("rules_excluded",[]):
        place=f" en `{_cell(x.get('location'))}`" if x.get("location") else ""
        excluded_lines.append(f"- `{x['rule_id']}`{place}: {x['reason']}")
    lines += excluded_lines or ["- Ninguna."]
    lines += ["", "### Propuestas rechazadas", ""]
    lines += [f"- `{x['rule_id']}` en `{x['location']['paragraph_id']}`: {x.get('rejection_reason') or 'No superó la validación.'}" for x in ed.get("rejected_suggestions",[])] or ["- Ninguna."]
    lines += ["", "### Tiempo por método", "", "| Método | Segundos |", "|---|---:|"]
    lines += [f"| {_cell(k)} | {float(v):.3f} |" for k,v in sorted(ed.get("summary",{}).get("duration_by_method",{}).items())]
    lines += ["", "### Limitaciones OOXML y verificación visual", ""]
    lines += [f"- {x}" for x in ed.get("visual_verification",{}).get("limitations",[])] or ["- Ninguna registrada."]
    return "\n".join(lines)+"\n"

def export_markdown(report,path):
    target=Path(path)
    if target.suffix.lower() not in {".md",".markdown"}: raise ValueError("El reporte debe tener extensión .md o .markdown.")
    target.parent.mkdir(parents=True,exist_ok=True); target.write_text(render_markdown(report),encoding="utf-8")
