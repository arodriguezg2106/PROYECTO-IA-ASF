"""Construye un dataset anonimizado a partir de reportes y decisiones exportadas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from revisor_crf.editorial_learning import build_dataset, load_json


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", required=True, help="Carpeta con reportes JSON de revisión")
    parser.add_argument("--decisions", required=True, help="Carpeta con decisiones JSON exportadas del HTML")
    parser.add_argument("--output", required=True, help="Salida JSON del dataset")
    args=parser.parse_args(argv)
    reports=[]
    for path in sorted(Path(args.reports).rglob("*.json")):
        data=load_json(path)
        if data.get("schema_version")=="review-1.1" and data.get("editorial_review"):
            reports.append(data)
    decisions={}
    for path in sorted(Path(args.decisions).rglob("*.json")):
        data=load_json(path)
        if str(data.get("schema_version","")).startswith("review-decisions-"):
            source_hash=data.get("source_sha256")
            if source_hash in decisions:
                raise ValueError(f"Hay más de un archivo de decisiones para {source_hash}.")
            decisions[source_hash]=data
    pairs=[(report,decisions[report["source"]["sha256"]]) for report in reports
           if report["source"]["sha256"] in decisions]
    dataset=build_dataset(pairs)
    dataset["summary"].update({"reports_found":len(reports),"reports_with_decisions":len(pairs)})
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(dataset,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Dataset guardado en {target}: {dataset['summary']['records']} registros de {len(pairs)} documentos.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
