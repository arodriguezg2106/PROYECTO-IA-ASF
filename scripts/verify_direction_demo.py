"""Prepara y verifica los casos sintéticos de la demostración para Dirección."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from revisor_crf.review import review_document
from revisor_crf.sample import DEMO_CASES, create_demo_cases


def _rule_count(items, rule_id):
    return sum(item.get("rule_id") == rule_id for item in items)


def verify(output_dir: Path) -> dict:
    paths = create_demo_cases(output_dir)
    results = []

    report = review_document(paths["01_suma_incorrecta.docx"])
    results.append({
        "case": "01_suma_incorrecta.docx",
        "expected": "exactly_one_total_alert",
        "passed": (
            _rule_count(report["alerts"], "NUM-TOTAL-001") == 1
            and _rule_count(report["limitations"], "NUM-TOTAL-001") == 0
        ),
        "alerts": len(report["alerts"]),
        "limitations": len(report["limitations"]),
    })

    report = review_document(paths["02_suma_correcta_compleja.docx"])
    results.append({
        "case": "02_suma_correcta_compleja.docx",
        "expected": "two_totals_evaluated_without_alerts",
        "passed": (
            _rule_count(report["alerts"], "NUM-TOTAL-001") == 0
            and _rule_count(report["limitations"], "NUM-TOTAL-001") == 0
            and report["coverage"]["NUM-TOTAL-001"]["evaluated"] == 2
        ),
        "alerts": len(report["alerts"]),
        "limitations": len(report["limitations"]),
    })

    report = review_document(paths["03_operacion_no_evaluable.docx"])
    results.append({
        "case": "03_operacion_no_evaluable.docx",
        "expected": "one_neutral_limitation_without_alert",
        "passed": (
            _rule_count(report["alerts"], "NUM-TOTAL-001") == 0
            and _rule_count(report["limitations"], "NUM-TOTAL-001") == 1
        ),
        "alerts": len(report["alerts"]),
        "limitations": len(report["limitations"]),
    })

    report = review_document(paths["04_revision_editorial.docx"], editorial=True)
    findings = report["editorial_review"]["findings"]
    expected_rules = {
        "ASF-ED-I-05-YO",
        "ASF-ED-II-07-10",
        "ASF-ED-I-06-06",
    }
    detected_rules = {item.get("rule_id") for item in findings}
    results.append({
        "case": "04_revision_editorial.docx",
        "expected": "three_editorial_rule_families_detected",
        "passed": expected_rules <= detected_rules,
        "editorial_findings": len(findings),
        "expected_rules_detected": sorted(expected_rules & detected_rules),
    })

    return {
        "schema_version": "direction-demo-preflight-1.0",
        "synthetic_only": True,
        "cases": results,
        "case_count": len(DEMO_CASES),
        "passed": all(item["passed"] for item in results),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/demo_direccion")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("results/demo/direction-preflight.json")
    )
    args = parser.parse_args(argv)
    result = verify(args.output_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
