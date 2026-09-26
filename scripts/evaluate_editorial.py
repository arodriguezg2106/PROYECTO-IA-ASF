"""Ejecuta el banco editorial y exporta métricas JSON y Markdown."""
from __future__ import annotations
import argparse, hashlib, json
from dataclasses import replace
from pathlib import Path
from revisor_crf.editorial import EditorialConfig, review_editorial
from revisor_crf.editorial_evaluation import evaluate_cases, render_evaluation_markdown
from revisor_crf.reader import read_docx
from revisor_crf.numbers import extract_numbers
from editorial_validation_bank import generate

def main(argv=None):
    parser=argparse.ArgumentParser(description="Evalúa reglas editoriales con DOCX sintéticos.")
    parser.add_argument("--bank",default="results/editorial_validation/bank")
    parser.add_argument("--output",default="results/editorial_validation/evaluation.json")
    parser.add_argument("--markdown",default="results/editorial_validation/evaluation.md")
    parser.add_argument("--config",help="Configuración editorial JSON o TOML")
    parser.add_argument("--regenerate",action="store_true",help="Regenera el banco sintético incorporado")
    args=parser.parse_args(argv)
    try:
        bank=Path(args.bank); manifest_path=bank/"manifest.json"
        if args.regenerate or not manifest_path.exists():payload=generate(bank)
        else:payload=json.loads(manifest_path.read_text(encoding="utf-8"))
        base_config=EditorialConfig.load(args.config)
        # La línea base mide reglas deterministas; Ollama se evalúa en un banco contextual separado.
        if base_config.ollama_enabled:raise ValueError("Este banco determinista requiere ollama_enabled=false.")
        reports={}
        hashes_before={case["document"]:hashlib.sha256((bank/case["document"]).read_bytes()).hexdigest() for case in payload["cases"]}
        for case in payload["cases"]:
            path=bank/case["document"]; document=read_docx(path,mode="final"); inventory=extract_numbers(document)
            config=replace(base_config,check_format=bool(case.get("check_format")))
            reports[case["case_id"]]=review_editorial(path,document,config,inventory=inventory)
        result=evaluate_cases(payload["cases"],reports)
        hashes_after={case["document"]:hashlib.sha256((bank/case["document"]).read_bytes()).hexdigest() for case in payload["cases"]}
        if hashes_before!=hashes_after:raise ValueError("La evaluación modificó uno o más DOCX sintéticos.")
        result["bank_schema_version"]=payload["schema_version"]
        result["document_hashes"]=hashes_after
        result["input_documents_unchanged"]=True
        result["catalog_version"]=next(iter(reports.values()))["catalog_version"] if reports else None
        result["coverage"]={rid:item for report in reports.values() for rid,item in report.get("coverage",{}).items()}
        result["acceptance_criteria"]={"minimum_precision":.95,"minimum_recall":.80,"input_documents_unchanged":True}
        result["status"]="approved" if result["summary"]["precision"] is not None and result["summary"]["precision"]>=.95 and result["summary"]["recall"] is not None and result["summary"]["recall"]>=.80 else "rejected"
        output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        markdown=Path(args.markdown); markdown.parent.mkdir(parents=True,exist_ok=True); markdown.write_text(render_evaluation_markdown(result),encoding="utf-8")
        print(f"Evaluación guardada en {output} y {markdown}: precisión={result['summary']['precision']}, exhaustividad={result['summary']['recall']}")
        return 0 if result["status"]=="approved" and result["summary"]["false_positives"]==0 and result["summary"]["false_negatives"]==0 else 2
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        print(f"Error: {exc}"); return 1

if __name__=="__main__":raise SystemExit(main())
