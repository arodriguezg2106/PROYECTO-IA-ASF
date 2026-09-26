"""Evaluación reproducible del revisor editorial con expectativas sintéticas."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal


def finding_key(item: dict) -> tuple[str, str]:
    return item["rule_id"], str(item.get("problem_span") or "")


def evaluate_cases(cases: list[dict], reports: dict[str, dict]) -> dict:
    """Compara multiconjuntos (regla, fragmento); conserva duplicados esperados."""
    per_rule = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "cases": set()})
    case_results = []
    for case in cases:
        case_id = case["case_id"]
        editorial = reports[case_id].get("editorial_review", reports[case_id])
        expected = Counter((x["rule_id"], x.get("problem_span", "")) for x in case.get("expected_findings", []))
        actual = Counter(finding_key(x) for x in editorial.get("findings", []))
        matched = expected & actual
        missing = expected - actual
        unexpected = actual - expected
        for (rule_id, _), count in matched.items():
            per_rule[rule_id]["tp"] += count; per_rule[rule_id]["cases"].add(case_id)
        for (rule_id, _), count in missing.items():
            per_rule[rule_id]["fn"] += count; per_rule[rule_id]["cases"].add(case_id)
        for (rule_id, _), count in unexpected.items():
            per_rule[rule_id]["fp"] += count; per_rule[rule_id]["cases"].add(case_id)
        case_results.append({
            "case_id": case_id, "description": case.get("description"),
            "expected": sum(expected.values()), "detected": sum(actual.values()),
            "true_positives": sum(matched.values()), "false_positives": sum(unexpected.values()),
            "false_negatives": sum(missing.values()),
            "missing": [{"rule_id": key[0], "problem_span": key[1], "count": count} for key,count in sorted(missing.items())],
            "unexpected": [{"rule_id": key[0], "problem_span": key[1], "count": count} for key,count in sorted(unexpected.items())],
        })
    rows=[]
    for rule_id, counts in sorted(per_rule.items()):
        tp,fp,fn=counts["tp"],counts["fp"],counts["fn"]
        rows.append({"rule_id":rule_id,"cases":len(counts["cases"]),"true_positives":tp,"false_positives":fp,"false_negatives":fn,
                     "precision":None if tp+fp==0 else round(tp/(tp+fp),4),
                     "recall":None if tp+fn==0 else round(tp/(tp+fn),4),
                     "f1":None if tp==0 else round(2*tp/(2*tp+fp+fn),4)})
    tp=sum(x["true_positives"] for x in rows); fp=sum(x["false_positives"] for x in rows); fn=sum(x["false_negatives"] for x in rows)
    return {"schema_version":"editorial-evaluation-1.0","generated_at":datetime.now(timezone.utc).isoformat(),
            "summary":{"cases":len(cases),"true_positives":tp,"false_positives":fp,"false_negatives":fn,
                       "precision":None if tp+fp==0 else round(tp/(tp+fp),4),
                       "recall":None if tp+fn==0 else round(tp/(tp+fn),4),
                       "f1":None if tp==0 else round(2*tp/(2*tp+fp+fn),4)},
            "rules":rows,"cases":case_results}


def render_evaluation_markdown(result: dict) -> str:
    s=result["summary"]
    lines=["# Evaluación editorial sintética","",f"Casos: {s['cases']} · TP: {s['true_positives']} · FP: {s['false_positives']} · FN: {s['false_negatives']}",
           f"Precisión: {s['precision']} · Exhaustividad: {s['recall']} · F1: {s['f1']}","",
           "| Regla | Casos | TP | FP | FN | Precisión | Exhaustividad | F1 |","|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in result["rules"]:lines.append(f"| {r['rule_id']} | {r['cases']} | {r['true_positives']} | {r['false_positives']} | {r['false_negatives']} | {r['precision'] if r['precision'] is not None else '—'} | {r['recall'] if r['recall'] is not None else '—'} | {r['f1'] if r['f1'] is not None else '—'} |")
    lines += ["","## Casos con diferencias",""]
    differences=[c for c in result["cases"] if c["false_positives"] or c["false_negatives"]]
    if not differences:lines.append("Ninguno.")
    for c in differences:lines.append(f"- `{c['case_id']}`: {c['false_positives']} FP, {c['false_negatives']} FN.")
    return "\n".join(lines)+"\n"
