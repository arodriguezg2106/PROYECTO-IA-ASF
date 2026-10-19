"""Compuerta secuencial y reproducible para modelos editoriales contextuales."""
from __future__ import annotations

import json
from pathlib import Path

from .editorial_context_evaluation import evaluate_context_provider
from .editorial_models import evaluation_passes


SYNTHETIC_STAGE_ORDER = ("smoke", "hard", "final")
STAGE_ORDER = (*SYNTHETIC_STAGE_ORDER, "real_paired")
DEFAULT_REAL_CATEGORIES = ("Ortografía o gramática", "Coherencia o claridad")


def load_real_paired_bank(path):
    """Carga un banco local pareado sin copiar su texto al repositorio.

    Admite el esquema expandido (``cases``) y una representación compacta
    (``pairs``). En ambos casos cada par debe aportar una versión anterior
    positiva y una versión final negativa.
    """
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Banco real pareado inválido o inaccesible: {source}") from exc
    privacy = data.get("privacy", {})
    if privacy.get("contains_raw_institutional_text") is not True:
        raise ValueError("El banco real debe declarar contains_raw_institutional_text=true.")
    if "cases" in data:
        cases = [dict(item) for item in data["cases"]]
    elif "pairs" in data:
        cases = []
        for pair in data["pairs"]:
            pair_id = str(pair.get("pair_id") or "").strip()
            if not pair_id:
                raise ValueError("Cada par real debe tener pair_id.")
            spans = pair.get("acceptable_spans") or []
            cases.extend((
                {"case_id": f"{pair_id}:before", "fragment": pair.get("before"),
                 "expected_finding": True, "acceptable_spans": spans,
                 "source_pair_id": pair_id, "variant": "before",
                 "category": pair.get("category")},
                {"case_id": f"{pair_id}:after", "fragment": pair.get("after"),
                 "expected_finding": False, "acceptable_spans": [],
                 "source_pair_id": pair_id, "variant": "after",
                 "category": pair.get("category")},
            ))
    else:
        raise ValueError("El banco real debe contener cases o pairs.")
    _validate_real_cases(cases)
    return {**data, "cases": cases}


def _validate_real_cases(cases):
    if not cases:
        raise ValueError("El banco real pareado está vacío.")
    ids = set()
    variants = {}
    for item in cases:
        required = ("case_id", "fragment", "expected_finding", "acceptable_spans",
                    "source_pair_id", "variant")
        if any(key not in item for key in required):
            raise ValueError("Caso real incompleto; faltan campos obligatorios.")
        if not isinstance(item["fragment"], str) or not item["fragment"].strip():
            raise ValueError("Todo caso real debe contener un fragmento no vacío.")
        if item["case_id"] in ids:
            raise ValueError(f"case_id real duplicado: {item['case_id']}")
        ids.add(item["case_id"])
        variant = item["variant"]
        if variant not in {"before", "after"}:
            raise ValueError("variant debe ser before o after.")
        expected = variant == "before"
        if item["expected_finding"] is not expected:
            raise ValueError("before debe ser positivo y after debe ser negativo.")
        if expected and not item["acceptable_spans"]:
            # En evidencia real la validación humana puede cubrir el fragmento
            # completo sin haber anotado un span exacto. El evaluador todavía
            # exige que el proveedor devuelva un problem_span literal.
            item["accept_any_literal_span"] = True
        variants.setdefault(item["source_pair_id"], set()).add(variant)
    incomplete = sorted(key for key, value in variants.items() if value != {"before", "after"})
    if incomplete:
        raise ValueError("Pares reales incompletos: " + ", ".join(incomplete))


def build_stage_cases(synthetic_cases, real_cases=None, *, include_real=True,
                      real_categories=DEFAULT_REAL_CATEGORIES):
    hard = [item for item in synthetic_cases if item.get("difficulty") == "hard"]
    final = [item for item in synthetic_cases if item.get("split") == "test"]
    positives = [item for item in synthetic_cases if item.get("expected_finding")]
    negatives = [item for item in synthetic_cases if not item.get("expected_finding")]
    if len(hard) != 10:
        raise ValueError(f"La compuerta difícil requiere 10 casos; encontró {len(hard)}.")
    if len(final) != 30:
        raise ValueError(f"La partición final requiere 30 casos; encontró {len(final)}.")
    if not positives or not negatives:
        raise ValueError("El banco sintético requiere casos positivos y negativos.")
    stages = {
        "smoke": [positives[0], negatives[0]],
        "hard": hard,
        "final": final,
    }
    if not include_real:
        return stages
    _validate_real_cases(real_cases)
    supported = set(real_categories)
    evaluated_real = [item for item in real_cases if item.get("category") in supported]
    if not evaluated_real:
        raise ValueError("El banco real no contiene pares de las categorías configuradas.")
    stages["real_paired"] = evaluated_real
    return stages


def aggregate_runs(runs, case_count):
    signatures = [
        [(item["predicted"], item["span_accepted"]) for item in run["details"]]
        for run in runs
    ]
    agreement = (
        sum(all(signature[index] == signatures[0][index] for signature in signatures)
            for index in range(case_count)) / case_count
        if case_count else 1.0
    )
    metrics = {
        key: round(sum(run[key] for run in runs) / len(runs), 4)
        for key in ("precision", "recall", "accuracy", "invalid_responses",
                    "unsafe_suggestions", "duration_seconds")
    }
    metrics.update({
        "cases": case_count,
        "repetitions": len(runs),
        "prediction_agreement": round(agreement, 4),
        "runs": runs,
    })
    return metrics


def evaluate_model_sequence(provider, synthetic_cases, real_cases, rule, criteria, *, repetitions=3,
                            real_categories=DEFAULT_REAL_CATEGORIES, include_real=True,
                            stage_callback=None):
    """Ejecuta las compuertas solicitadas y se detiene en el primer fallo."""
    minimum = criteria["minimum_repetitions"]
    if repetitions < minimum:
        raise ValueError(f"La evaluación exige al menos {minimum} repeticiones.")
    stage_cases = build_stage_cases(
        synthetic_cases,
        real_cases,
        include_real=include_real,
        real_categories=real_categories,
    )
    stage_order = STAGE_ORDER if include_real else SYNTHETIC_STAGE_ORDER
    stages = []
    stopped = False
    for name in stage_order:
        cases = stage_cases[name]
        if stopped:
            stages.append({"stage": name, "status": "not_run", "cases": len(cases)})
            continue
        runs = [evaluate_context_provider(provider, cases, rule) for _ in range(repetitions)]
        metrics = aggregate_runs(runs, len(cases))
        passed = evaluation_passes(metrics, criteria, repetitions=repetitions)
        stages.append({"stage": name, "status": "passed" if passed else "failed", "metrics": metrics})
        if stage_callback is not None:
            stage_callback(name, list(stages))
        stopped = not passed
    result = {
        "status": "passed" if not stopped else "failed",
        "repetitions": repetitions,
        "stage_order": list(stage_order),
        "stages": stages,
        "evaluation_scope": "full_institutional" if include_real else "synthetic_screening_only",
        "real_bank_coverage": None,
    }
    if include_real:
        result["real_bank_coverage"] = {
            "total_cases": len(real_cases),
            "evaluated_cases": len(stage_cases["real_paired"]),
            "unsupported_cases": len(real_cases) - len(stage_cases["real_paired"]),
            "evaluated_categories": list(real_categories),
        }
    return result
