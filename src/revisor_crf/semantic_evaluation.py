"""Métricas reproducibles para seleccionar un modelo semántico aprobado."""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict

from .semantic import validate_decision


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentage * len(ordered)) - 1)
    return ordered[index]


def evaluate_provider(provider, records: list[dict], batch_size: int = 8) -> dict:
    predicted = {}
    document_durations = []
    batch_durations = []
    invalid = 0
    by_document = defaultdict(list)
    for record in records:
        by_document[record["document_sha256"]].append(record)
    for document_hash, document_records in sorted(by_document.items()):
        document_started = time.perf_counter()
        for offset in range(0, len(document_records), batch_size):
            batch = document_records[offset:offset + batch_size]
            cases = [record["case"] for record in batch]
            started = time.perf_counter()
            decisions = provider.analyze(cases, "associate")
            batch_durations.append(time.perf_counter() - started)
            by_id = {item.get("case_id"): item for item in decisions if isinstance(item, dict)}
            for record in batch:
                case = record["case"]
                try:
                    predicted[(document_hash, case["case_id"])] = validate_decision(
                        by_id.get(case["case_id"]), case
                    )
                except (TypeError, ValueError):
                    invalid += 1
        document_durations.append(time.perf_counter() - document_started)
    counts = Counter()
    correct = 0
    for record in records:
        expected = record["expected_relation"]
        decision = predicted.get((record["document_sha256"], record["case"]["case_id"]))
        actual = decision["relation"] if decision else "invalid"
        if actual == expected:
            correct += 1
        expected_positive = expected == "same_measure"
        actual_positive = actual == "same_measure"
        counts[(expected_positive, actual_positive)] += 1
    true_positive = counts[(True, True)]
    false_positive = counts[(False, True)]
    false_negative = counts[(True, False)]
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return {
        "records": len(records), "correct": correct,
        "accuracy": correct / len(records) if records else 0.0,
        "precision_same_measure": precision, "recall_same_measure": recall,
        "false_positives": false_positive, "invalid_responses": invalid,
        "duration_seconds": sum(document_durations),
        "document_p95_seconds": percentile(document_durations, 0.95),
        "batch_p95_seconds": percentile(batch_durations, 0.95),
    }


def select_model(results: list[dict], *, minimum_precision: float = 0.98,
                 minimum_accuracy: float = 0.95, maximum_duration_seconds: float = 600.0) -> dict | None:
    eligible = [result for result in results
                if result["metrics"]["precision_same_measure"] >= minimum_precision
                and result["metrics"]["accuracy"] >= minimum_accuracy
                and result["metrics"].get("document_p95_seconds",
                                          result["metrics"]["duration_seconds"]) <= maximum_duration_seconds
                and result["metrics"]["invalid_responses"] == 0]
    if not eligible:
        return None
    return max(eligible, key=lambda result: (
        result["metrics"]["precision_same_measure"], result["metrics"]["accuracy"],
        -result["metrics"].get("document_p95_seconds", result["metrics"]["duration_seconds"]),
        -result["metrics"]["duration_seconds"], result["model"],
    ))
