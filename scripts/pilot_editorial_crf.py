"""Piloto editorial por lote: no modifica entradas y continúa ante fallos."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from revisor_crf.editorial import EditorialConfig
from revisor_crf.editorial_report import export_markdown
from revisor_crf.html_report import export_html
from revisor_crf.reader import export_json, read_docx
from revisor_crf.review import review_document
from revisor_crf.sarif_report import export_sarif

PILOT_ANALYSIS_VERSION = "2.2-substantive-priority"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_key(path, sha256):
    slug=re.sub(r"[^0-9A-Za-zÁÉÍÓÚÑáéíóúñ_-]+","-",path.stem).strip("-")[:80] or "documento"
    return f"{slug}-{sha256[:12]}"


def _compact_error(exc):
    return {"type":type(exc).__name__,"message":str(exc)[:500]}


def inspect_document(path, input_root, output_root, *, use_language_tool=False,
                     cache_path=None, resume=False):
    before=digest(path); started=time.perf_counter(); key=output_key(path,before)
    target=output_root/"documents"/key; target.mkdir(parents=True,exist_ok=True)
    item_path=target/"pilot-item.json"
    if resume and item_path.exists():
        previous=json.loads(item_path.read_text(encoding="utf-8"))
        output_files=[output_root/value for value in previous.get("outputs",{}).values()]
        if (previous.get("status")=="complete" and previous.get("sha256_before")==before
                and previous.get("analysis_version")==PILOT_ANALYSIS_VERSION
                and all(file.exists() for file in output_files)):
            previous["resumed"]=True
            return previous
    item={"file":path.relative_to(input_root).as_posix(),"sha256_before":before,"output_key":key,
          "analysis_version":PILOT_ANALYSIS_VERSION,
          "status":"failed","error":None,"outputs":{},"hash_unchanged":False,"resumed":False}
    try:
        config=EditorialConfig(language_tool_enabled=use_language_tool,
            language_tool_experimental=use_language_tool,
            language_tool_cache_path=str(cache_path) if cache_path else None)
        report=review_document(path,mode="final",editorial=True,
            editorial_config_override=config)
        paths={"json":target/"review.json","html":target/"review.html",
               "markdown":target/"review.md","sarif":target/"review.sarif"}
        export_json(report,paths["json"]); export_html(report,paths["html"])
        export_markdown(report,paths["markdown"]); export_sarif(report,paths["sarif"])
        editorial=report["editorial_review"]
        item.update(status="complete",outputs={k:v.relative_to(output_root).as_posix() for k,v in paths.items()},
                    data_alerts=len(report.get("alerts",[])),
                    findings=editorial["summary"]["findings"],by_severity=editorial["summary"]["by_severity"],
                    substantive_findings=editorial["summary"].get("substantive_findings",editorial["summary"]["findings"]),
                    format_occurrences=editorial["summary"].get("format_occurrences",0),
                    by_focus=editorial["summary"].get("by_focus",{}),
                    by_method=editorial["summary"]["by_method"],by_evaluation_status=editorial["summary"]["by_evaluation_status"],
                    distinct_groups=editorial["summary"].get("distinct_groups"),
                    distinct_rules=editorial["summary"].get("distinct_rules"),
                    language_tool=editorial.get("language_tool",{}),
                    rejected_suggestions=editorial["summary"]["rejected_suggestions"],coverage=editorial["coverage"],
                    rules_not_evaluable=editorial["rules_not_evaluable"],rules_excluded=editorial["rules_excluded"],
                    glossary_entries=len(editorial["acronym_glossary"]),duration_seconds=editorial["duration_seconds"])
        item["sample_candidates"]=[{"finding_id":x["id"],"rule_id":x["rule_id"],"severity":x["severity"],
            "evaluation_status":x["evaluation_status"],"detection_method":x["detection_method"],
            "review_focus":x.get("review_focus"),
            "paragraph_id":x["location"]["paragraph_id"],"message":x["message"]}
            for x in editorial["findings"]]
    except (OSError,RuntimeError,ValueError,KeyError) as exc:
        item["error"]=_compact_error(exc)
    after=digest(path); item["sha256_after"]=after; item["hash_unchanged"]=before==after
    item["elapsed_seconds"]=round(time.perf_counter()-started,6)
    item_path.write_text(json.dumps(item,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return item


def _structural_metrics(path):
    document=read_docx(path,mode="final")
    metrics={"paragraphs":0,"tables":0,"characters":0,"acronyms":0,"revisions":0}
    def walk(blocks):
        for block in blocks:
            if block.get("type")=="paragraph":
                text=block.get("text",""); metrics["paragraphs"]+=1; metrics["characters"]+=len(text)
                metrics["acronyms"]+=len(re.findall(r"\b[A-ZÁÉÍÓÚÑ]{2,}\b",text))
                metrics["revisions"]+=len(block.get("revisions",[]))
                for fragment in block.get("content",[]):metrics["revisions"]+=len(fragment.get("revisions",[]))
                walk(block.get("blocks",[]))
            else:
                metrics["tables"]+=1
                for row in block.get("rows",[]):
                    for cell in row.get("cells",[]):walk(cell.get("blocks",[]))
    walk(document.get("blocks",[]))
    return metrics


def select_representative(files, maximum=5):
    inspected=[]
    for path in files:
        inspected.append({"path":path,"metrics":_structural_metrics(path)})
    roles=[("corto","characters",False),("extenso","characters",True),
           ("con_mas_cuadros","tables",True),("con_mas_siglas","acronyms",True),
           ("con_mas_control_de_cambios","revisions",True)]
    selected=[]; used=set()
    for role,metric,descending in roles:
        candidates=sorted(inspected,key=lambda item:(item["metrics"][metric],item["path"].name.casefold()),
                          reverse=descending)
        chosen=next((item for item in candidates if item["path"] not in used),None)
        if chosen:
            used.add(chosen["path"]); selected.append({"role":role,**chosen})
        if len(selected)>=maximum:break
    if len(selected)<maximum:
        for item in sorted(inspected,key=lambda value:value["path"].name.casefold()):
            if item["path"] not in used:
                selected.append({"role":"diversidad_adicional",**item}); used.add(item["path"])
                if len(selected)>=maximum:break
    return selected


def stratified_sample(documents, maximum=40):
    buckets=defaultdict(list)
    for document in documents:
        for finding in document.pop("sample_candidates",[]):
            row={**finding,"file":document["file"],"output_key":document["output_key"],
                 "report":document.get("outputs",{}).get("html")}
            buckets[(finding["rule_id"],finding["evaluation_status"])].append(row)
    selected=[]
    for key in sorted(buckets):
        selected.extend(buckets[key][:2])
    return selected[:maximum]


def build_summary(documents, input_root, *, selection=None, use_language_tool=False):
    complete=[x for x in documents if x["status"]=="complete"]
    coverage=defaultdict(Counter); by_rule=Counter(); by_rule_format=Counter(); by_severity=Counter(); by_method=Counter(); by_status=Counter()
    for document in complete:
        by_severity.update(document["by_severity"]); by_method.update(document["by_method"]); by_status.update(document["by_evaluation_status"])
        for rule_id,item in document["coverage"].items():coverage[rule_id][item["status"]]+=1
        for finding in document.get("sample_candidates",[]):
            (by_rule_format if finding.get("review_focus")=="format" else by_rule)[finding["rule_id"]]+=1
    sample=stratified_sample(documents)
    return {"schema_version":"editorial-pilot-1.0","generated_at":datetime.now(timezone.utc).isoformat(),
      "input_directory":str(input_root),"mode":"final","ollama_enabled":False,
      "language_tool_enabled":use_language_tool,"autofix":False,
      "summary":{"documents":len(documents),"completed":len(complete),"failed":len(documents)-len(complete),
        "hashes_unchanged":sum(x["hash_unchanged"] for x in documents),"findings":sum(x.get("findings",0) for x in complete),
        "substantive_findings":sum(x.get("substantive_findings",x.get("findings",0)) for x in complete),
        "format_occurrences":sum(x.get("format_occurrences",0) for x in complete),
        "data_alerts":sum(x.get("data_alerts",0) for x in complete),
        "by_rule":dict(by_rule),"by_rule_format":dict(by_rule_format),"by_severity":dict(by_severity),"by_method":dict(by_method),"by_evaluation_status":dict(by_status),
        "duration_seconds":round(sum(x["elapsed_seconds"] for x in documents),3)},
      "coverage_by_rule":{rule:dict(counts) for rule,counts in sorted(coverage.items())},
      "selection":[{"role":item["role"],"file":item["path"].relative_to(input_root).as_posix(),
                    "metrics":item["metrics"]} for item in (selection or [])],
      "documents":documents,"validation_sample":sample,
      "limitations":["La muestra requiere validación humana; los hallazgos possible no demuestran por sí solos un incumplimiento.",
        "La paginación, los bordes renderizados y la alineación decimal visual no se evaluaron.",
        "No se utilizó Ollama ni se modificaron los DOCX."]}


def render_summary(report):
    s=report["summary"]
    lines=["# Piloto editorial de CRF reales","",f"Fecha UTC: {report['generated_at']}",
      f"Documentos: {s['documents']} · Completados: {s['completed']} · Fallidos: {s['failed']} · Hashes sin cambio: {s['hashes_unchanged']}",
      f"Alertas de datos/tablas: {s['data_alerts']} · Observaciones de lenguaje y estructura: {s['substantive_findings']} · Formato agrupado: {s['format_occurrences']} ocurrencias · Tiempo acumulado: {s['duration_seconds']:.3f} s","",
      "## Conteos por estado","","| Estado | Hallazgos |","|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in sorted(s["by_evaluation_status"].items())]
    lines += ["","## Conteos por regla","","| Regla | Hallazgos |","|---|---:|"]
    lines += [f"| {k} | {v} |" for k,v in sorted(s["by_rule"].items())]
    lines += ["","## Documentos","","| Documento | Estado | Hallazgos | Sin cambios | Reporte |","|---|---|---:|---|---|"]
    for item in report["documents"]:
        link=item.get("outputs",{}).get("html"); rendered=f"[{item['output_key']}]({link})" if link else "—"
        lines.append(f"| {item['file'].replace('|','\\|')} | {item['status']} | {item.get('findings','—')} | {item['hash_unchanged']} | {rendered} |")
    lines += ["","## Muestra estratificada para validación humana","","| Documento | Regla | Estado | Método | Ubicación | Reporte |","|---|---|---|---|---|---|"]
    for item in report["validation_sample"]:
        lines.append(f"| {item['file'].replace('|','\\|')} | {item['rule_id']} | {item['evaluation_status']} | {item['detection_method']} | {item['paragraph_id']} | [abrir]({item['report']}) |")
    lines += ["","## Limitaciones",""]+[f"- {x}" for x in report["limitations"]]
    return "\n".join(lines)+"\n"


def render_dashboard(report):
    summary=report["summary"]
    document_rows="".join(
        f'<tr><td>{escape(item["file"])}</td><td>{escape(item["status"])}</td>'
        f'<td>{item.get("data_alerts","—")}</td><td>{item.get("substantive_findings","—")}</td><td>{item.get("format_occurrences","—")}</td>'
        f'<td>{item.get("elapsed_seconds",0):.2f} s</td><td>{item.get("hash_unchanged")}</td>'
        f'<td><a href="{escape(item.get("outputs",{}).get("html","#"),quote=True)}">abrir</a></td></tr>'
        for item in report["documents"])
    rule_rows="".join(f'<tr><td>{escape(rule)}</td><td>{count}</td></tr>'
                      for rule,count in sorted(summary["by_rule"].items(),key=lambda row:(-row[1],row[0])))
    selection_rows="".join(
        f'<tr><td>{escape(item["role"])}</td><td>{escape(item["file"])}</td>'
        f'<td><code>{escape(json.dumps(item["metrics"],ensure_ascii=False))}</code></td></tr>'
        for item in report.get("selection",[]))
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Piloto editorial ASF</title><style>body{{font:15px/1.45 system-ui;margin:auto;max-width:1200px;padding:24px;color:#17232d}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}.metric{{padding:14px;border:1px solid #d6dfe5;border-radius:8px}}.metric strong{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;margin:15px 0}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #d6dfe5;vertical-align:top}}th{{background:#eef2f4}}code{{white-space:normal}}a{{color:#075f73}}</style></head><body><h1>Piloto editorial ASF</h1><p>Prioridad: datos, tablas, concordancia, claridad y ortografía. El formato se contabiliza aparte.</p><div class="metrics"><div class="metric"><strong>{summary['documents']}</strong>documentos</div><div class="metric"><strong>{summary['data_alerts']}</strong>alertas de datos/tablas</div><div class="metric"><strong>{summary['substantive_findings']}</strong>lenguaje y estructura</div><div class="metric"><strong>{summary['format_occurrences']}</strong>ocurrencias de formato</div><div class="metric"><strong>{summary['hashes_unchanged']}</strong>hashes intactos</div><div class="metric"><strong>{summary['duration_seconds']:.2f} s</strong>tiempo acumulado</div></div><h2>Selección representativa</h2><table><thead><tr><th>Perfil</th><th>Documento</th><th>Métricas</th></tr></thead><tbody>{selection_rows}</tbody></table><h2>Documentos</h2><table><thead><tr><th>Documento</th><th>Estado</th><th>Datos/tablas</th><th>Lenguaje/estructura</th><th>Formato</th><th>Tiempo</th><th>Sin cambio</th><th>Reporte</th></tr></thead><tbody>{document_rows}</tbody></table><h2>Reglas sustantivas más frecuentes</h2><table><thead><tr><th>Regla</th><th>Ocurrencias</th></tr></thead><tbody>{rule_rows}</tbody></table></body></html>'''


def run_pilot(input_root,output_root,*,sample_size=None,use_language_tool=False,resume=False):
    input_root=Path(input_root).resolve(); output_root=Path(output_root).resolve()
    files=sorted(input_root.rglob("*.docx"),key=lambda x:x.as_posix().casefold())
    if not files:raise ValueError(f"No se encontraron DOCX en {input_root}")
    selection=select_representative(files,sample_size) if sample_size else None
    if selection:files=[item["path"] for item in selection]
    output_root.mkdir(parents=True,exist_ok=True); documents=[]
    cache_path=output_root/"cache"/"languagetool.sqlite3" if use_language_tool else None
    for index,path in enumerate(files,1):
        item=inspect_document(path,input_root,output_root,use_language_tool=use_language_tool,
                              cache_path=cache_path,resume=resume); documents.append(item)
        print(json.dumps({"index":index,"total":len(files),"file":item["file"],"status":item["status"],"findings":item.get("findings"),"hash_unchanged":item["hash_unchanged"]},ensure_ascii=True),flush=True)
    report=build_summary(documents,input_root,selection=selection,use_language_tool=use_language_tool)
    (output_root/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (output_root/"summary.md").write_text(render_summary(report),encoding="utf-8")
    (output_root/"dashboard.html").write_text(render_dashboard(report),encoding="utf-8")
    (output_root/"validation_sample.json").write_text(json.dumps({"schema_version":"editorial-validation-sample-1.0","items":report["validation_sample"]},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description="Ejecuta el piloto editorial determinista sobre una carpeta de DOCX.")
    parser.add_argument("input"); parser.add_argument("--output",default="results/editorial_pilot")
    parser.add_argument("--sample-size",type=int,help="Selecciona automáticamente una muestra estructural")
    parser.add_argument("--language-tool",action="store_true",help="Activa LanguageTool local experimental")
    parser.add_argument("--resume",action="store_true",help="Reutiliza resultados completos con el mismo hash")
    args=parser.parse_args(argv)
    try:report=run_pilot(args.input,args.output,sample_size=args.sample_size,
                         use_language_tool=args.language_tool,resume=args.resume)
    except (OSError,ValueError) as exc:print(f"Error: {exc}"); return 1
    s=report["summary"]; print(f"Piloto terminado: {s['completed']}/{s['documents']} documentos; {s['findings']} hallazgos; {s['hashes_unchanged']} hashes sin cambio.")
    return 0 if s["failed"]==0 and s["hashes_unchanged"]==s["documents"] else 2


if __name__=="__main__":raise SystemExit(main())
