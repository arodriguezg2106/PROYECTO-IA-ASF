"""Compara modelos Ollama locales en un banco editorial contextual sintético."""
from __future__ import annotations
import argparse,json
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from revisor_crf.editorial import EditorialConfig,OllamaEditorialProvider,load_editorial_catalog
from revisor_crf.editorial_context_evaluation import evaluate_context_provider
from revisor_crf.editorial_models import evaluation_passes,load_model_registry
from revisor_crf.editorial_context_bank import load_context_bank

def main(argv=None):
    parser=argparse.ArgumentParser(description="Evalúa modelos Ollama para revisión editorial contextual.")
    parser.add_argument("--dataset",default="tests/data/editorial_context_cases.json")
    parser.add_argument("--config",default="editorial-config.example.toml")
    parser.add_argument("--models",default="qwen3.5:4b")
    parser.add_argument("--repetitions",type=int,default=1)
    parser.add_argument("--max-cases",type=int,help="Limita casos para una prueba rápida reproducible")
    parser.add_argument("--case-ids",help="Lista separada por comas para una evaluación focalizada")
    parser.add_argument("--split",choices=("development","calibration","test"),help="Evalúa únicamente la partición indicada")
    parser.add_argument("--focused-first",action="store_true",help="Exige aprobar primero los casos marcados como difíciles")
    parser.add_argument("--output",default="results/editorial_context/model-evaluation.json")
    args=parser.parse_args(argv)
    try:
        dataset=load_context_bank(args.dataset); cases=dataset["cases"]
        if args.split:cases=[x for x in cases if x.get("split")==args.split]
        if args.focused_first:cases=[x for x in cases if x.get("difficulty")=="hard"][:10]
        if args.max_cases:cases=cases[:args.max_cases]
        if args.case_ids:
            requested={x.strip() for x in args.case_ids.split(",") if x.strip()}; cases=[x for x in dataset["cases"] if x["case_id"] in requested]
            missing=requested-{x["case_id"] for x in cases}
            if missing:raise ValueError("Casos desconocidos: "+", ".join(sorted(missing)))
        if args.repetitions<1:raise ValueError("--repetitions debe ser positivo.")
        catalog=load_editorial_catalog(); rule=next(x for x in catalog["rules"] if x["rule_id"]=="ASF-ED-I-CONTEXT")
        registry=load_model_registry(); criteria=registry["approval_criteria"]
        base=EditorialConfig.load(args.config); results=[]
        for model in [x.strip() for x in args.models.split(",") if x.strip()]:
            config=replace(base,ollama_enabled=True,experimental_model=True,model=model,temperature=0.0)
            runs=[evaluate_context_provider(OllamaEditorialProvider(config),cases,rule) for _ in range(args.repetitions)]
            signatures=[[d["predicted"] for d in run["details"]] for run in runs]
            agreement=sum(all(sig[i]==signatures[0][i] for sig in signatures) for i in range(len(cases)))/len(cases) if cases else 1.0
            metrics={key:round(sum(run[key] for run in runs)/len(runs),4) for key in ("precision","recall","accuracy","invalid_responses","unsafe_suggestions","duration_seconds")}
            metrics.update({"cases":len(cases),"repetitions":args.repetitions,"prediction_agreement":round(agreement,4),"runs":runs})
            results.append({"model":model,"metrics":metrics})
        eligible=[x for x in results if evaluation_passes(x["metrics"],criteria,repetitions=args.repetitions)]
        selected=max(eligible,key=lambda x:(x["metrics"]["precision"],x["metrics"]["recall"],x["metrics"]["prediction_agreement"],-x["metrics"]["duration_seconds"])) if eligible else None
        payload={"schema_version":"editorial-context-model-evaluation-1.1","generated_at":datetime.now(timezone.utc).isoformat(),"dataset":dataset["schema_version"],"evaluated_cases":len(cases),"split":args.split,"focused_first":args.focused_first,"criteria":criteria,"results":results,"selected_model":selected["model"] if selected else None,"status":"approved" if selected else "no_model_met_criteria"}
        target=Path(args.output); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"Evaluación contextual guardada en {target}; modelo: {payload['selected_model'] or 'ninguno'}")
        return 0 if selected else 2
    except (OSError,ValueError,RuntimeError,json.JSONDecodeError,StopIteration) as exc:print(f"Error: {exc}"); return 1

if __name__=="__main__":raise SystemExit(main())
