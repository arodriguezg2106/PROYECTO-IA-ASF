"""Reporte HTML autónomo para localizar, revisar y decidir alertas."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from html import escape
from pathlib import Path


def _serialize(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Tipo no serializable: {type(value).__name__}")


def _json(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_serialize)
    return (payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _semantic_status_html(report: dict) -> str:
    semantic = report.get("semantic_review")
    if not semantic:
        return ""
    status = semantic.get("status", "unknown")
    candidates = int(semantic.get("candidate_cases") or 0)
    accepted = len(semantic.get("accepted_relations") or [])
    suggestions = len(semantic.get("suggestions") or [])
    duration = float(semantic.get("duration_seconds") or 0)
    cache = semantic.get("cache") or {}
    if status == "complete" and candidates == 0:
        title = "Revisión semántica completada sin casos elegibles"
        explanation = (
            "No se enviaron casos al modelo porque el filtro determinístico no encontró pares "
            "tabla–narrativa que pudieran superar todos los controles."
        )
    elif status == "complete":
        title = "Revisión semántica completada"
        explanation = (
            f"Se analizaron {candidates} candidatos; {accepted} superaron ambos dictámenes "
            f"y {suggestions} quedaron únicamente para revisión humana."
        )
    else:
        title = "Revisión semántica no disponible"
        explanation = (
            "La revisión determinística sí concluyó. Motivo semántico: "
            f"{semantic.get('error_code') or 'no especificado'}."
        )
    fields = (
        ("Estado", status), ("Proveedor", semantic.get("provider")),
        ("Modelo", semantic.get("model")), ("Candidatos", candidates),
        ("Relaciones aceptadas", accepted), ("Sugerencias HTML", suggestions),
        ("Duración", f"{duration:.3f} s"),
        ("Caché", f"{cache.get('hits', 0)} aciertos / {cache.get('misses', 0)} consultas"),
    )
    values = "".join(
        f'<div><span class="label">{escape(str(label))}</span><div>'
        f'{escape(str("—" if value is None or value == "" else value))}</div></div>'
        for label, value in fields
    )
    status_class = "status-ok" if status == "complete" else "status-warn"
    return (
        f'<section id="semantic-status" class="card semantic-status {status_class}">'
        f'<h2>{escape(title)}</h2><p>{escape(explanation)}</p>'
        f'<div class="where-grid">{values}</div></section>'
    )

def _editorial_html(report: dict) -> str:
    ed = report.get("editorial_review")
    if not ed:
        return ""
    summary = ed.get("summary", {})
    grouped = defaultdict(list)
    for item in ed.get("findings", []):
        grouped[(item.get("rule_id", ""), item.get("severity", ""),
                 item.get("detection_method", ""), item.get("evaluation_status", ""),
                 item.get("message", ""))].append(item)
    substantive_rows = []
    format_rows = []
    language_tool_rows = []
    ollama_rows = []
    decision_options = "".join(
        f'<option value="{value}">{label}</option>' for value, label in (
            ("pending", "Pendiente"), ("confirmed", "Confirmada"),
            ("rejected", "Falso positivo"), ("not_evaluable", "No evaluable"),
            ("audit_team_review", "Requiere equipo auditor"),
        )
    )
    for (rule_id, severity, method, status, message), items in sorted(grouped.items()):
        occurrences = "".join(
            '<li class="editorial-occurrence" data-editorial-id="{}"><code>{}</code> — '
            '<strong>{}</strong>{}<div class="editorial-decision">'
            '<label>Decisión humana<select class="editorial-decision-status">{}</select></label>'
            '<label>Comentario<textarea class="editorial-decision-comment" '
            'placeholder="Motivo de la decisión"></textarea></label></div></li>'.format(
                escape(str(item.get("id") or ""), quote=True),
                escape(str(item.get("location", {}).get("paragraph_id") or "sin ubicación")),
                escape(str(item.get("problem_span") or "fragmento no disponible")),
                (f'<div class="meta">{escape(str(item.get("original_text") or ""))}</div>'
                 if item.get("original_text") else ""), decision_options)
            for item in items
        )
        source = items[0].get("source_section", "")
        page = items[0].get("source_page")
        foundation = f"{source}, p. {page}" if page is not None else str(source)
        row_html = (
            '<tr class="editorial-group" data-rule="{}" data-severity="{}" '
            'data-method="{}" data-status="{}"><td>{}</td><td>{}</td><td>{}</td>'
            '<td>{}</td><td><details><summary>{} ocurrencia{}</summary><ol>{}</ol></details></td>'
            '<td>{}</td></tr>'.format(
                escape(str(rule_id), quote=True), escape(str(severity), quote=True),
                escape(str(method), quote=True), escape(str(status), quote=True),
                escape(str(rule_id)), escape(str(severity)), escape(str(method)),
                escape(str(message)), len(items), "s" if len(items) != 1 else "",
                occurrences, escape(foundation)))
        if method == "language_tool":
            language_tool_rows.append(row_html)
        elif method == "ollama":
            ollama_rows.append(row_html)
        elif items[0].get("review_focus") == "format":
            format_rows.append(row_html)
        else:
            substantive_rows.append(row_html)
    substantive_html = "".join(substantive_rows) or '<tr><td colspan="6">Sin observaciones sustantivas adicionales.</td></tr>'
    format_html = "".join(format_rows) or '<tr><td colspan="6">Sin observaciones de formato.</td></tr>'
    language_tool_html = "".join(language_tool_rows) or '<tr><td colspan="6">Sin sugerencias lingüísticas.</td></tr>'
    ollama_html = "".join(ollama_rows) or '<tr><td colspan="6">Sin propuestas experimentales.</td></tr>'
    def options(values):
        return "".join(f'<option value="{escape(str(value), quote=True)}">{escape(str(value))}</option>'
                       for value in sorted(values))
    rule_options = options({key[0] for key in grouped})
    severity_options = options({key[1] for key in grouped})
    method_options = options({key[2] for key in grouped})
    status_options = options({key[3] for key in grouped})
    coverage = ed.get("coverage", {})
    coverage_rows = "".join(f'<tr><td>{escape(rid)}</td><td>{escape(str(value.get("status")))}</td><td>{value.get("findings",0)}</td><td>{escape(str(value.get("source_section")))}, p. {escape(str(value.get("source_page")))}</td></tr>' for rid,value in sorted(coverage.items()))
    glossary_rows = "".join(f'<tr><td>{escape(str(x.get("acronym")))}</td><td>{escape(str(x.get("denomination") or "—"))}</td><td>{escape(str(x.get("first_location")))}</td><td>{escape(str(x.get("status")))}</td></tr>' for x in ed.get("acronym_glossary",[]))
    limitations = "".join(f'<li>{escape(str(x))}</li>' for x in ed.get("visual_verification",{}).get("limitations",[]))
    exclusions = "".join(f'<li><code>{escape(str(x.get("rule_id")))}</code>: {escape(str(x.get("reason")))}</li>' for x in ed.get("rules_excluded",[])) or "<li>Ninguna.</li>"
    rejected = "".join(f'<li><code>{escape(str(x.get("rule_id")))}</code>: {escape(str(x.get("rejection_reason") or "No superó la validación."))}</li>' for x in ed.get("rejected_suggestions",[])) or "<li>Ninguna.</li>"
    model=ed.get("ollama",{}).get("model") or {}
    model_text=f'{model.get("model_id")} ({model.get("status")})' if model else "desactivado"
    lt=ed.get("language_tool",{})
    if lt.get("enabled"):
        lt_profile = lt.get("profile") or {}
        lt_text = (
            f'{lt.get("status", "desconocido")} · LanguageTool 6.6 · '
            f'perfil {lt_profile.get("profile_version") or "—"} · '
            f'{float(lt.get("duration_seconds") or 0):.3f} s · '
            f'{len(lt.get("errors") or [])} errores técnicos'
        )
    else:
        lt_text = "desactivado"
    return (f'<section id="editorial-review" class="card"><h2>Revisión editorial ASF</h2>'
            f'<p>Catálogo {escape(str(ed.get("catalog_version")))} · '
            f'<strong>{summary.get("substantive_findings", summary.get("findings", 0))} observaciones sustantivas</strong> · '
            f'{summary.get("format_occurrences", 0)} ocurrencias de formato agrupadas en '
            f'{summary.get("groups_by_focus", {}).get("format", 0)} tipos · '
            f'{summary.get("distinct_rules", len({key[0] for key in grouped}))} reglas · '
            f'{summary.get("rejected_suggestions", 0)} sugerencias rechazadas · '
            f'{float(ed.get("duration_seconds") or 0):.3f} s · Modelo contextual: {escape(model_text)} · '
            f'LanguageTool: {escape(str(lt_text))}</p>'
            '<p class="meta">Prioridad: cifras, tablas, concordancia, claridad y ortografía. El formato se conserva para control, pero aparece agrupado y en segundo plano. Una ocurrencia no equivale necesariamente a un error confirmado.</p>'
            '<div class="editorial-filters where-grid">'
            f'<label>Regla<select id="editorial-rule"><option value="">Todas</option>{rule_options}</select></label>'
            f'<label>Severidad<select id="editorial-severity"><option value="">Todas</option>{severity_options}</select></label>'
            f'<label>Método<select id="editorial-method"><option value="">Todos</option>{method_options}</select></label>'
            f'<label>Evaluación<select id="editorial-status"><option value="">Todas</option>{status_options}</select></label></div>'
            '<p id="editorial-filter-summary" class="meta"></p>'
            '<h3>Concordancia, claridad, ortografía y consistencia editorial</h3><table class="calc-table"><thead><tr><th>Regla</th><th>Severidad</th><th>Método</th><th>Hallazgo</th><th>Ubicaciones</th><th>Fundamento</th></tr></thead>'
            f'<tbody>{substantive_html}</tbody></table>'
            '<details class="card"><summary><strong>Sugerencias lingüísticas de LanguageTool</strong> — '
            f'{len(language_tool_rows)} grupos posibles; siempre requieren decisión humana</summary>'
            '<p class="meta">Estas sugerencias provienen exclusivamente de reglas incluidas en el perfil aprobado. No son errores confirmados y no generan comentarios de Word.</p>'
            '<table class="calc-table"><thead><tr><th>Regla</th><th>Severidad</th><th>Método</th><th>Sugerencia</th><th>Ubicaciones</th><th>Fundamento</th></tr></thead>'
            f'<tbody>{language_tool_html}</tbody></table></details>'
            '<details class="card"><summary><strong>Propuestas experimentales de Ollama</strong> — '
            f'{len(ollama_rows)} grupos posibles; siempre requieren decisión humana</summary>'
            '<p class="meta">El modelo es opcional y puede quedar parcial sin interrumpir el motor determinístico. Sus propuestas no son errores confirmados, no autocorrigen y no generan comentarios de Word.</p>'
            '<table class="calc-table"><thead><tr><th>Regla</th><th>Severidad</th><th>Método</th><th>Propuesta</th><th>Ubicaciones</th><th>Fundamento</th></tr></thead>'
            f'<tbody>{ollama_html}</tbody></table></details>'
            f'<details class="card"><summary><strong>Observaciones de formato agrupadas</strong> — {summary.get("format_occurrences", 0)} ocurrencias en {summary.get("groups_by_focus", {}).get("format", 0)} tipos</summary><table class="calc-table"><thead><tr><th>Regla</th><th>Severidad</th><th>Método</th><th>Hallazgo</th><th>Ubicaciones</th><th>Fundamento</th></tr></thead><tbody>{format_html}</tbody></table></details>'
            f'<h3>Cobertura por regla</h3><table class="calc-table"><thead><tr><th>Regla</th><th>Estado</th><th>Hallazgos</th><th>Fundamento</th></tr></thead><tbody>{coverage_rows}</tbody></table>'
            f'<h3>Glosario de siglas</h3><table class="calc-table"><thead><tr><th>Sigla</th><th>Denominación</th><th>Primera ubicación</th><th>Estado</th></tr></thead><tbody>{glossary_rows}</tbody></table>'
            f'<h3>Reglas y ubicaciones excluidas</h3><ul>{exclusions}</ul><h3>Propuestas rechazadas</h3><ul>{rejected}</ul>'
            f'<h3>Limitaciones OOXML</h3><ul>{limitations}</ul>'
            '<script>(function(){const ids=["editorial-rule","editorial-severity","editorial-method","editorial-status"];'
            'const rows=[...document.querySelectorAll(".editorial-group")];function apply(){const v=Object.fromEntries(ids.map(id=>[id,document.getElementById(id).value]));let shown=0;rows.forEach(row=>{const ok=(!v["editorial-rule"]||row.dataset.rule===v["editorial-rule"])&&(!v["editorial-severity"]||row.dataset.severity===v["editorial-severity"])&&(!v["editorial-method"]||row.dataset.method===v["editorial-method"])&&(!v["editorial-status"]||row.dataset.status===v["editorial-status"]);row.hidden=!ok;if(ok)shown++;});document.getElementById("editorial-filter-summary").textContent=shown+" de "+rows.length+" grupos visibles";}ids.forEach(id=>document.getElementById(id).addEventListener("change",apply));apply();})();</script>'
            '</section>')


def render_html(report: dict) -> str:
    """Devuelve un solo archivo HTML, sin URL ni dependencia externa."""
    template = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; object-src 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión CRF</title><style>
:root{--ink:#17232d;--muted:#607080;--line:#d6dfe5;--paper:#fff;--bg:#f2f5f6;--high:#a52a2a;--medium:#8a5b00;--accent:#075f73;--accent-soft:#e4f3f5;--warn:#fff8e6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.48 system-ui,sans-serif}header,main{max-width:1180px;margin:auto;padding:24px}header{background:#123047;color:white;max-width:none}header>div{max-width:1132px;margin:auto}
h1{margin:0 0 6px;font-size:24px}h2{font-size:19px;margin:10px 0}.meta{opacity:.8}.toolbar,.card{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}.toolbar{display:flex;gap:12px;flex-wrap:wrap;align-items:end;position:sticky;top:0;z-index:2;box-shadow:0 2px 8px #15253212}label{display:grid;gap:4px;font-weight:600}
select,input,textarea,button{font:inherit;padding:8px;border:1px solid #aeb8c2;border-radius:6px}button{background:var(--accent);color:white;border:0;cursor:pointer}button.secondary{background:#536575}button.copy{background:white;color:var(--accent);border:1px solid var(--accent);font-size:13px}.spacer{flex:1}.alert-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.badge{padding:3px 8px;border-radius:99px;background:#e8edf1;font-size:12px;font-weight:700}.high{color:var(--high)}.medium{color:var(--medium)}
.where{background:var(--accent-soft);border-left:5px solid var(--accent);border-radius:7px;padding:14px;margin:14px 0}.where h3,.verify h3{margin:0 0 7px;font-size:15px}.route{font-size:17px;font-weight:750;margin-bottom:8px}.where-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:7px 16px}.label{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:700}.search-text{display:block;background:white;border:1px solid #cbd8dd;padding:9px;border-radius:6px;margin:9px 0;overflow-wrap:anywhere}.actions{display:flex;gap:8px;flex-wrap:wrap}.editorial-occurrence{margin:10px 0}.editorial-decision{display:grid;grid-template-columns:minmax(180px,1fr) 2fr;gap:8px;margin:8px 0;padding:8px;background:#f6f8fa;border-radius:6px}.editorial-decision textarea{min-height:48px}
.verify{background:var(--warn);border:1px solid #ead9aa;border-radius:7px;padding:12px;margin:12px 0}.limitations{border-left:5px solid #788995;background:#f7f9fa}.limitation{border-top:1px solid var(--line);padding:12px 0}.limitation:first-child{border-top:0}.limitations summary{cursor:pointer}.numbers{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:8px;margin:12px 0}.number{border:1px solid var(--line);border-radius:7px;padding:10px}.number strong{display:block;font-size:18px;overflow-wrap:anywhere}.difference{border-color:#dca7a7;background:#fff6f6}.calc-table{width:100%;border-collapse:collapse;margin:12px 0}.calc-table th,.calc-table td{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.calc-table th{background:#eef2f4}.calc-table td.value{text-align:right;font-variant-numeric:tabular-nums;font-weight:650}
details{margin:10px 0}pre{white-space:pre-wrap;word-break:break-word;background:#f6f8fa;padding:10px;border-radius:6px}.decision{display:grid;grid-template-columns:minmax(220px,1fr) 2fr;gap:12px;border-top:1px solid var(--line);padding-top:14px;margin-top:14px}textarea{min-height:70px;width:100%}.empty{text-align:center;color:var(--muted)}.semantic-status{border-left:5px solid var(--accent)}.semantic-status.status-ok{background:#f3fbf7;border-left-color:#278553}.semantic-status.status-warn{background:var(--warn);border-left-color:#b07900}.semantic-status p{margin:6px 0 14px}.toast{position:fixed;right:20px;bottom:20px;background:#173b46;color:white;padding:10px 14px;border-radius:7px;display:none;z-index:5}@media(max-width:700px){.decision{grid-template-columns:1fr}.toolbar{position:static}.where-grid{grid-template-columns:1fr}.calc-table{font-size:13px}}
</style></head><body><header><div><h1>Revisión CRF</h1><div class="meta" id="document-meta"></div></div></header><main>
<section class="toolbar" aria-label="Filtros y acciones"><label>Regla<select id="rule-filter"><option value="">Todas</option></select></label><label>Severidad<select id="severity-filter"><option value="">Todas</option><option>high</option><option>medium</option></select></label><label>Estado<select id="status-filter"><option value="">Todos</option><option value="pending">Pendiente</option><option value="confirmed">Confirmada</option><option value="rejected">Rechazada</option><option value="not_evaluable">No evaluable</option><option value="audit_team_review">Requiere equipo auditor</option></select></label><span class="spacer"></span><button id="export">Descargar decisiones</button><button class="secondary" id="import-button">Importar decisiones</button><input hidden type="file" id="import" accept="application/json,.json"></section>
<section id="data-validation" class="card"><h2>Validación prioritaria de tablas y cifras</h2><p class="meta">Revise primero diferencias numéricas, porcentajes, unidades, totales y concordancia entre cuadros y texto.</p><div id="summary" class="meta"></div><section id="alerts"></section></section><details id="limitations-section" class="card limitations"><summary><strong>Operaciones no evaluadas</strong> · <span id="limitations-count">0</span></summary><p class="meta">Limitaciones técnicas de cobertura; no son errores del documento ni requieren una decisión.</p><section id="limitations"></section></details>__EDITORIAL_REVIEW____SEMANTIC_STATUS__<section id="semantic-suggestions"></section></main><div class="toast" id="toast" role="status"></div><script type="application/json" id="review-data">__REVIEW_DATA__</script><script>
"use strict";const report=JSON.parse(document.getElementById("review-data").textContent);const limitations=report.limitations||[];const limitationsById=new Map(limitations.map(item=>[item.id,item]));const suggestions=report.semantic_review?.suggestions||[];const editorialFindings=report.editorial_review?.findings||[];const editorialIds=new Set(editorialFindings.map(item=>item.id));const suggestionIds=new Set(suggestions.map(item=>item.id));const reviewItems=[...report.alerts,...suggestions,...editorialFindings];const itemsById=new Map(reviewItems.map(item=>[item.id,item]));const statuses={pending:"Pendiente",confirmed:"Confirmada",rejected:"Falso positivo",not_evaluable:"No evaluable",audit_team_review:"Requiere equipo auditor"};const labels={high:"Alta",medium:"Media"};const storageKey="revisor-crf:"+report.source.sha256;let decisions={};try{decisions=JSON.parse(localStorage.getItem(storageKey)||"{}")}catch(_e){decisions={}}
const esc=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));const valueText=value=>value===null||value===undefined||value===""?"No disponible":String(value);function save(){try{localStorage.setItem(storageKey,JSON.stringify(decisions))}catch(_e){}}function current(alert){return decisions[alert.id]||{status:alert.reviewer?.status||"pending",comment:alert.reviewer?.comment||""}}
function locationText(alert){const w=alert.where_to_review||{};return [w.ruta,w.encabezado_fila&&`Concepto/fila: ${w.encabezado_fila}`,w.encabezado_columna&&`Columna: ${w.encabezado_columna}`].filter(Boolean).join("\\n")}
function whereHtml(alert){const w=alert.where_to_review||{};const fields=[["Resultado",w.resultado],["Tabla",w.tabla_ordinal],["Fila",w.fila],["Columna",w.columna],["Concepto o fila",w.encabezado_fila],["Encabezado",w.encabezado_columna]].filter(([,v])=>v!==null&&v!==undefined&&v!=="");return `<section class="where"><h3>Dónde revisar</h3><div class="route">${esc(w.ruta||"Consulte la evidencia estructural")}</div><div class="where-grid">${fields.map(([k,v])=>`<div><span class="label">${esc(k)}</span><div>${esc(v)}</div></div>`).join("")}</div>${w.texto_busqueda?`<span class="label">Texto para buscar en Word</span><code class="search-text">${esc(w.texto_busqueda)}</code>`:""}<div class="actions"><button class="copy copy-location" type="button">Copiar ubicación</button>${w.texto_busqueda?'<button class="copy copy-search" type="button">Copiar texto para buscar</button>':""}</div></section>`}
function numbersHtml(alert){const o=alert.operation||{};if(o.type==="manual_review"||o.type==="not_evaluable")return "";return `<div class="numbers"><div class="number"><span class="label">Declarado</span><strong>${esc(valueText(o.declarado))}</strong></div><div class="number"><span class="label">Calculado o relacionado</span><strong>${esc(valueText(o.calculado))}</strong></div><div class="number difference"><span class="label">Diferencia</span><strong>${esc(valueText(o.diferencia))}</strong></div><div class="number"><span class="label">Unidad / escala</span><strong>${esc(valueText(o.unidad))} × ${esc(valueText(o.escala))}</strong></div></div>`}
function calculationHtml(alert){const o=alert.operation||{};if(o.type!=="sum"&&o.type!=="comparison")return "";const rows=alert.evidence.map(e=>{const l=e.ubicacion||{};const concept=l.encabezado_fila||e.rol;const place=[l.fila&&`fila ${l.fila}`,l.columna&&`col. ${l.columna}`].filter(Boolean).join(", ");return `<tr><td>${esc(e.rol)}</td><td>${esc(concept||"")}${place?`<div class="meta">${esc(place)}</div>`:""}</td><td class="value">${esc(valueText(e.valor))}</td></tr>`}).join("");return `<table class="calc-table"><thead><tr><th>Participación</th><th>Fila o concepto</th><th>Valor normalizado</th></tr></thead><tbody>${rows}</tbody></table>`}
function evidenceHtml(alert){return `<details><summary>Evidencia técnica completa (${alert.evidence.length})</summary><pre>${esc(JSON.stringify({operation:alert.operation,evidence:alert.evidence,reason:alert.not_evaluable_reason},null,2))}</pre></details>`}
function decisionHtml(item){const d=current(item);return `<div class="decision"><label>Decisión<select class="decision-status">${Object.entries(statuses).map(([v,l])=>`<option value="${v}"${d.status===v?" selected":""}>${l}</option>`).join("")}</select></label><label>Comentario<textarea class="decision-comment" placeholder="Justificación o seguimiento">${esc(d.comment)}</textarea></label></div>`}
function cardHtml(alert){return `<article class="card" data-id="${esc(alert.id)}"><div class="alert-head"><strong>${esc(alert.rule_id)}</strong><span class="badge ${esc(alert.severity)}">${esc(labels[alert.severity]||alert.severity)}</span><span class="badge">${esc(alert.category)}</span><span class="badge">${esc(alert.origin||"deterministic")}</span><span class="meta">${esc(alert.id)}</span></div><h2>${esc(alert.message)}</h2>${whereHtml(alert)}${numbersHtml(alert)}${calculationHtml(alert)}<section class="verify"><h3>Qué debe verificar</h3>${esc(alert.review_instruction||"")}${alert.not_evaluable_reason?`<div class="meta">Motivo: ${esc(alert.not_evaluable_reason)}</div>`:""}</section>${evidenceHtml(alert)}${decisionHtml(alert)}</article>`}
function limitationHtml(item){return `<article class="limitation" data-limitation-id="${esc(item.id)}"><div class="alert-head"><strong>${esc(item.rule_id)}</strong><span class="badge">Limitación técnica</span><span class="meta">${esc(item.id)}</span></div><h2>${esc(item.message)}</h2>${whereHtml(item)}<p>${esc(item.not_evaluable_reason||item.review_instruction||"La operación no pudo evaluarse con seguridad.")}</p>${evidenceHtml(item)}</article>`}
function suggestionHtml(item){const t=item.table||{},n=item.narrative||{};return `<article class="card" data-id="${esc(item.id)}"><div class="alert-head"><strong>Relación semántica por revisar</strong><span class="badge">${esc(item.relation)}</span><span class="badge">confianza ${esc(item.confidence)}</span></div><h2>${esc(item.reason)}</h2><div class="where-grid"><div><span class="label">Fila o concepto</span><div>${esc(t.row)}</div></div><div><span class="label">Columna</span><div>${esc(t.column)}</div></div><div><span class="label">Valor tabular</span><div>${esc(t.value)}</div></div><div><span class="label">Valor narrativo</span><div>${esc(n.value)}</div></div><div><span class="label">Magnitud tabla</span><div>${esc(item.table_measure)}</div></div><div><span class="label">Magnitud narrativa</span><div>${esc(item.narrative_measure)}</div></div></div><details><summary>Evidencia semántica</summary><pre>${esc(JSON.stringify(item.evidence,null,2))}</pre></details>${decisionHtml(item)}</article>`}
function showToast(text){const toast=document.getElementById("toast");toast.textContent=text;toast.style.display="block";setTimeout(()=>toast.style.display="none",1600)}async function copyText(text){try{await navigator.clipboard.writeText(text)}catch(_e){const area=document.createElement("textarea");area.value=text;area.style.position="fixed";area.style.opacity="0";document.body.append(area);area.select();document.execCommand("copy");area.remove()}showToast("Copiado al portapapeles")}
function bindCards(){document.querySelectorAll("article[data-id]").forEach(card=>{const id=card.dataset.id,a=itemsById.get(id);card.querySelector(".decision-status").addEventListener("change",e=>{decisions[id]={...current(a),status:e.target.value};save();render()});card.querySelector(".decision-comment").addEventListener("input",e=>{decisions[id]={...current(a),comment:e.target.value};save()});card.querySelector(".copy-location")?.addEventListener("click",()=>copyText(locationText(a)));card.querySelector(".copy-search")?.addEventListener("click",()=>copyText(a.where_to_review?.texto_busqueda||""))})}
function bindLimitations(){document.querySelectorAll("article[data-limitation-id]").forEach(card=>{const item=limitationsById.get(card.dataset.limitationId);card.querySelector(".copy-location")?.addEventListener("click",()=>copyText(locationText(item)));card.querySelector(".copy-search")?.addEventListener("click",()=>copyText(item.where_to_review?.texto_busqueda||""))})}
function bindEditorial(){document.querySelectorAll(".editorial-occurrence[data-editorial-id]").forEach(row=>{const id=row.dataset.editorialId,item=itemsById.get(id),d=current(item);const status=row.querySelector(".editorial-decision-status"),comment=row.querySelector(".editorial-decision-comment");status.value=d.status;comment.value=d.comment;status.addEventListener("change",e=>{decisions[id]={...current(item),status:e.target.value};save();updateEditorialDecisionSummary()});comment.addEventListener("input",e=>{decisions[id]={...current(item),comment:e.target.value};save()})})}
function updateEditorialDecisionSummary(){const decided=editorialFindings.filter(item=>current(item).status!=="pending").length;const target=document.getElementById("editorial-filter-summary");if(target){const visible=[...document.querySelectorAll(".editorial-group")].filter(row=>!row.hidden).length;target.textContent=`${visible} grupos visibles · ${decided} de ${editorialFindings.length} ocurrencias decididas`;}}
function render(){const rf=document.getElementById("rule-filter").value,sf=document.getElementById("severity-filter").value,stf=document.getElementById("status-filter").value;const shown=report.alerts.filter(a=>(!rf||a.rule_id===rf)&&(!sf||a.severity===sf)&&(!stf||current(a).status===stf));const shownSuggestions=suggestions.filter(s=>!stf||current(s).status===stf);document.getElementById("summary").textContent=`${shown.length} de ${report.alerts.length} alertas · ${limitations.length} operaciones no evaluadas · ${shownSuggestions.length} relaciones semánticas por revisar`;document.getElementById("alerts").innerHTML=shown.length?shown.map(cardHtml).join(""):"<p class='card empty'>No hay alertas para estos filtros.</p>";document.getElementById("limitations-count").textContent=limitations.length;document.getElementById("limitations").innerHTML=limitations.map(limitationHtml).join("");document.getElementById("limitations-section").hidden=limitations.length===0;document.getElementById("semantic-suggestions").innerHTML=shownSuggestions.length?`<h2>Relaciones semánticas que requieren revisión humana</h2>${shownSuggestions.map(suggestionHtml).join("")}`:"";bindCards();bindLimitations();updateEditorialDecisionSummary()}
document.getElementById("document-meta").textContent=`${report.source.file} · modo ${report.reading_mode} · SHA-256 ${report.source.sha256}`;[...new Set(report.alerts.map(a=>a.rule_id))].sort().forEach(rule=>{const option=document.createElement("option");option.value=option.textContent=rule;document.getElementById("rule-filter").append(option)});["rule-filter","severity-filter","status-filter"].forEach(id=>document.getElementById(id).addEventListener("change",render));
document.getElementById("export").addEventListener("click",()=>{const itemType=a=>editorialIds.has(a.id)?"editorial_finding":suggestionIds.has(a.id)?"semantic_suggestion":"alert";const payload={schema_version:"review-decisions-1.2",source_sha256:report.source.sha256,review_schema_version:report.schema_version,exported_at:new Date().toISOString(),decisions:reviewItems.map(a=>({item_id:a.id,item_type:itemType(a),rule_id:a.rule_id||null,...current(a)}))};const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json"});const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download="decisiones-"+report.source.sha256.slice(0,12)+".json";link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)});document.getElementById("import-button").addEventListener("click",()=>document.getElementById("import").click());document.getElementById("import").addEventListener("change",async e=>{try{const payload=JSON.parse(await e.target.files[0].text());if(!["review-decisions-1.0","review-decisions-1.1","review-decisions-1.2"].includes(payload.schema_version)||payload.source_sha256!==report.source.sha256||!Array.isArray(payload.decisions))throw new Error("Archivo incompatible");const valid=new Set(reviewItems.map(a=>a.id));payload.decisions.forEach(d=>{const id=d.item_id||d.alert_id;if(valid.has(id)&&statuses[d.status]!==undefined)decisions[id]={status:d.status,comment:String(d.comment||"")}});save();render();bindEditorial()}catch(error){alert("No se pudieron importar las decisiones: "+error.message)}e.target.value=""});bindEditorial();render();
</script></body></html>"""
    return (template.replace("__SEMANTIC_STATUS__", _semantic_status_html(report))
            .replace("__EDITORIAL_REVIEW__", _editorial_html(report))
            .replace("__REVIEW_DATA__", _json(report)))


def export_html(report: dict, path: str | Path) -> None:
    target = Path(path)
    if target.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("El reporte debe tener extensión .html o .htm.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(report), encoding="utf-8")
