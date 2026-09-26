"""Preparación segura de decisiones editoriales para aprendizaje supervisado.

Este módulo no entrena modelos. Convierte decisiones humanas verificadas en
registros anonimizados y separados por documento para evitar fuga de datos.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Protocol, Sequence

from .editorial import protected_elements


DECISION_SCHEMAS = {"review-decisions-1.0", "review-decisions-1.1", "review-decisions-1.2"}
LABELS = {"confirmed": "valid", "rejected": "false_positive"}


def redact_text(text: str) -> str:
    """Sustituye elementos protegidos por su tipo sin conservar su valor."""
    text = text or ""
    intervals = sorted(protected_elements(text), key=lambda item: (item["start"], -item["end"]))
    selected = []
    cursor = -1
    for item in intervals:
        if item["start"] < cursor:
            continue
        selected.append(item)
        cursor = item["end"]
    parts=[]; cursor=0
    for item in selected:
        parts.append(text[cursor:item["start"]])
        parts.append(f"<{str(item['type']).upper()}>")
        cursor=item["end"]
    parts.append(text[cursor:])
    return " ".join("".join(parts).split())


def document_split(source_sha256: str, salt: str = "asf-editorial-1") -> str:
    bucket = int(hashlib.sha256(f"{salt}|{source_sha256}".encode()).hexdigest()[:8], 16) % 100
    return "training" if bucket < 70 else "calibration" if bucket < 85 else "test"


def _text_shape(text: str, prefix: str) -> dict:
    text=text or ""
    letters=[char for char in text if char.isalpha()]
    protected=Counter(item["type"] for item in protected_elements(text))
    return {
        f"{prefix}_character_count":len(text),
        f"{prefix}_word_count":len(re.findall(r"\w+",text,re.UNICODE)),
        f"{prefix}_digit_count":sum(char.isdigit() for char in text),
        f"{prefix}_punctuation_count":sum(not char.isalnum() and not char.isspace() for char in text),
        f"{prefix}_uppercase_ratio":round(sum(char.isupper() for char in letters)/len(letters),6) if letters else 0.0,
        f"{prefix}_contains_parentheses":"(" in text or ")" in text,
        f"{prefix}_protected_type_counts":dict(protected),
    }


def learning_records(report: dict, decisions: dict) -> list[dict]:
    if decisions.get("schema_version") not in DECISION_SCHEMAS:
        raise ValueError("Esquema de decisiones no compatible.")
    source_hash = str((report.get("source") or {}).get("sha256") or "")
    if not source_hash or decisions.get("source_sha256") != source_hash:
        raise ValueError("Las decisiones no corresponden al reporte.")
    findings = {item.get("id"): item for item in
                (report.get("editorial_review") or {}).get("findings", []) if item.get("id")}
    decision_index = {item.get("item_id") or item.get("alert_id"): item
                      for item in decisions.get("decisions", [])}
    records=[]
    for finding_id, finding in findings.items():
        decision = decision_index.get(finding_id) or {}
        if decision.get("status") not in LABELS:
            continue
        location=finding.get("location") or {}
        original=str(finding.get("original_text") or "")
        span=str(finding.get("problem_span") or "")
        record_id=hashlib.sha256(f"{source_hash}|{finding_id}".encode()).hexdigest()
        records.append({
            "record_id": record_id,
            "source_group": source_hash,
            "split": document_split(source_hash),
            "label": LABELS[decision["status"]],
            "features": {
                "rule_id": finding.get("rule_id"),
                "category": finding.get("category"),
                "method": finding.get("detection_method"),
                "severity": finding.get("severity"),
                "evaluation_status": finding.get("evaluation_status"),
                "requires_human_review": bool(finding.get("requires_human_review")),
                "in_table": bool(location.get("table_id") or location.get("cell_reference")),
                "has_suggestion": bool(finding.get("suggested_text")),
                "value_source": finding.get("value_source"),
                "review_comment_present": bool(str(decision.get("comment") or "").strip()),
                **_text_shape(original,"context"),
                **_text_shape(span,"problem"),
            },
        })
    return records


def build_dataset(pairs: Sequence[tuple[dict, dict]]) -> dict:
    records=[]
    for report, decisions in pairs:
        records.extend(learning_records(report, decisions))
    record_ids=[record["record_id"] for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("El conjunto contiene decisiones editoriales duplicadas.")
    by_label=Counter(record["label"] for record in records)
    by_split=Counter(record["split"] for record in records)
    documents_by_split={split:len({r["source_group"] for r in records if r["split"]==split})
                        for split in ("training","calibration","test")}
    readiness_reasons=[]
    document_count=len({record["source_group"] for record in records})
    if len(records)<300: readiness_reasons.append("Se requieren al menos 300 decisiones utilizables.")
    if document_count<30: readiness_reasons.append("Se requieren decisiones de al menos 30 documentos.")
    for label in ("valid","false_positive"):
        if by_label[label]<50: readiness_reasons.append(f"La etiqueta {label} requiere al menos 50 ejemplos.")
    for split in ("training","calibration","test"):
        if not by_split[split]: readiness_reasons.append(f"La partición {split} está vacía.")
    return {
        "schema_version":"editorial-learning-dataset-1.0",
        "contains_raw_document_text":False,
        "label_policy":{"confirmed":"valid","rejected":"false_positive",
                        "excluded":["pending","not_evaluable","audit_team_review"]},
        "split_policy":"sha256 documental: 70% entrenamiento, 15% calibración, 15% prueba",
        "summary":{"records":len(records),"by_label":dict(by_label),"by_split":dict(by_split),
                   "documents":document_count,"documents_by_split":documents_by_split,
                   "training_readiness":{"ready":not readiness_reasons,"reasons":readiness_reasons}},
        "records":records,
    }


class FindingPrioritizer(Protocol):
    model_id: str
    model_version: str
    def predict_valid_probability(self, feature_rows: Sequence[dict]) -> Sequence[float]: ...


def apply_priorities(findings: Sequence[dict], prioritizer: FindingPrioritizer) -> list[dict]:
    """Añade puntajes sin permitir que el modelo cambie estado, texto o severidad."""
    feature_rows=[]
    for finding in findings:
        location=finding.get("location") or {}
        original=str(finding.get("original_text") or "")
        feature_rows.append({
            "rule_id":finding.get("rule_id"), "category":finding.get("category"),
            "method":finding.get("detection_method"), "severity":finding.get("severity"),
            "in_table":bool(location.get("table_id") or location.get("cell_reference")),
            **_text_shape(original,"context"),
        })
    probabilities=list(prioritizer.predict_valid_probability(feature_rows))
    if len(probabilities) != len(findings) or any(not isinstance(p,(int,float)) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError("El priorizador devolvió probabilidades inválidas.")
    output=[]
    for finding, probability in zip(findings, probabilities):
        item=deepcopy(finding)
        item["ml_priority"]={"model_id":prioritizer.model_id,"model_version":prioritizer.model_version,
                             "probability_valid":round(float(probability),6),
                             "status":"experimental","requires_human_review":True}
        output.append(item)
    return output


def load_json(path: str | Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON inválido: {path}") from exc
