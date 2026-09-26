"""Exportación interoperable de alertas y hallazgos al estándar SARIF 2.1.0."""
from __future__ import annotations

import json
from pathlib import Path


SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _level(item: dict) -> str:
    severity = str(item.get("severity") or "").lower()
    if severity in {"error", "high"}:
        return "error"
    if severity in {"warning", "medium"}:
        return "warning"
    return "note"


def _location(item: dict, source_name: str) -> dict:
    editorial = item.get("location") or {}
    paragraph_id = editorial.get("paragraph_id")
    if paragraph_id:
        name = paragraph_id
    else:
        where = item.get("where_to_review") or {}
        name = where.get("ruta") or item.get("id") or "documento"
    return {
        "physicalLocation": {"artifactLocation": {"uri": source_name}},
        "logicalLocations": [{"name": str(name), "kind": "paragraph"}],
    }


def render_sarif(report: dict) -> dict:
    editorial = (report.get("editorial_review") or {}).get("findings") or []
    items = [*report.get("alerts", []), *editorial]
    rules = {}
    for item in items:
        rule_id = str(item.get("rule_id") or "UNKNOWN")
        rules.setdefault(rule_id, {
            "id": rule_id,
            "name": rule_id,
            "shortDescription": {"text": str(item.get("message") or rule_id)},
            "properties": {
                "category": item.get("category"),
                "sourceSection": item.get("source_section"),
                "sourcePage": item.get("source_page"),
            },
        })
    source_name = str((report.get("source") or {}).get("file") or "document.docx")
    results = []
    for item in items:
        result = {
            "ruleId": str(item.get("rule_id") or "UNKNOWN"),
            "level": _level(item),
            "message": {"text": str(item.get("message") or "Hallazgo sin descripción.")},
            "locations": [_location(item, source_name)],
            "properties": {
                "findingId": item.get("id"),
                "method": item.get("detection_method") or item.get("origin"),
                "evaluationStatus": item.get("evaluation_status") or item.get("status"),
                "requiresHumanReview": bool(item.get("requires_human_review")),
                "problemSpan": item.get("problem_span"),
            },
        }
        results.append(result)
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "revisor-crf",
                "version": str((report.get("engine") or {}).get("version") or "unknown"),
                "informationUri": "https://github.com/oasis-tcs/sarif-spec",
                "rules": list(rules.values()),
            }},
            "artifacts": [{"location": {"uri": source_name},
                           "hashes": {"sha-256": str((report.get("source") or {}).get("sha256") or "")}}],
            "results": results,
            "properties": {"readingMode": report.get("reading_mode"),
                           "sourceUnchanged": (report.get("source") or {}).get("unchanged")},
        }],
    }


def export_sarif(report: dict, path: str | Path) -> None:
    target = Path(path)
    if target.suffix.lower() != ".sarif":
        raise ValueError("El reporte SARIF debe tener extensión .sarif.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(render_sarif(report), ensure_ascii=False, indent=2), encoding="utf-8")
