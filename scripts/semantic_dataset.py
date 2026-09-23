"""Convierte decisiones humanas aprobadas en un dataset JSONL local y versionado."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def split_for(document_hash: str) -> str:
    bucket = int(hashlib.sha256(document_hash.encode("ascii")).hexdigest()[:8], 16) % 10
    return "development" if bucket < 6 else "validation" if bucket < 8 else "test"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Genera ejemplos semánticos aprobados.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--approved-by", required=True)
    args = parser.parse_args(argv)
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
        source_hash = report["source"]["sha256"]
        if decisions.get("source_sha256") != source_hash:
            raise ValueError("Las decisiones no corresponden al reporte.")
        semantic = report.get("semantic_review") or {}
        cases = {item["case_id"]: item for item in semantic.get("suggestions", [])}
        for item in semantic.get("accepted_relations", []):
            cases[item["case"]["case_id"]] = item
        records = []
        for decision in decisions.get("decisions", []):
            item_id = decision.get("item_id") or decision.get("alert_id")
            source = next((item for item in semantic.get("suggestions", []) if item["id"] == item_id), None)
            if source is None:
                alert = next((item for item in report.get("alerts", []) if item["id"] == item_id
                              and item.get("rule_id") == "NUM-CROSS-ML-001"), None)
                case_id = (alert or {}).get("semantic", {}).get("case_id")
                accepted = next((item for item in semantic.get("accepted_relations", [])
                                 if item["case"]["case_id"] == case_id), None)
                case = (accepted or {}).get("case")
                proposed = "same_measure"
            else:
                case = {
                    "case_id": source["case_id"], "table": source["table"],
                    "narrative": source["narrative"],
                    "deterministic": {"table_measure": source["table_measure"],
                                      "narrative_measure": source["narrative_measure"]},
                }
                proposed = source["relation"]
            if not case or decision.get("status") not in {"confirmed", "rejected", "not_evaluable"}:
                continue
            expected = proposed if decision["status"] == "confirmed" else (
                "unrelated" if decision["status"] == "rejected" else "uncertain"
            )
            records.append({
                "schema_version": "semantic-dataset-1.0", "document_sha256": source_hash,
                "split": split_for(source_hash), "case": case, "expected_relation": expected,
                "reviewer": args.reviewer, "approved_by": args.approved_by,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "engine_version": report.get("engine", {}).get("version"),
                "prompt_version": semantic.get("prompt_version"),
            })
        if not records:
            raise ValueError("No hay decisiones semánticas aprobables en el archivo.")
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        known = {
            (stored["document_sha256"], stored["case"]["case_id"])
            for line in existing.splitlines() if line.strip()
            for stored in [json.loads(line)]
        }
        new_records = [
            record for record in records
            if (record["document_sha256"], record["case"]["case_id"]) not in known
        ]
        content = existing + "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in new_records)
        target.write_text(content, encoding="utf-8")
        print(f"Dataset actualizado en {target}: {len(new_records)} ejemplos nuevos")
        return 0
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
