import json

import pytest

from evaluate_editorial_context import _model_preflight, main
from revisor_crf.editorial import load_editorial_catalog
from revisor_crf.editorial_context_bank import load_context_bank
from revisor_crf.editorial_model_evaluation import (
    evaluate_model_sequence,
    load_real_paired_bank,
)
from revisor_crf.editorial_models import load_model_registry


class OracleProvider:
    def __init__(self, cases, *, always_negative=False):
        self.cases = {item["case_id"]: item for item in cases}
        self.always_negative = always_negative
        self.calls = 0

    def review(self, request, schema):
        self.calls += 1
        case = self.cases[request["location"]["case_id"]]
        findings = []
        if case["expected_finding"] and not self.always_negative:
            findings.append({
                "rule_id": "ASF-ED-I-CONTEXT",
                "category": "grammar",
                "severity": "warning",
                "problem_span": (case["acceptable_spans"] or [case["fragment"]])[0],
                "message": "Hallazgo de prueba.",
                "suggested_text": case["fragment"],
                "confidence": 0.99,
            })
        return json.dumps({"findings": findings}, ensure_ascii=False)


def _real_cases():
    return [
        {"case_id": "p1:before", "fragment": "La unidad volvió a repetir el acto.",
         "expected_finding": True, "acceptable_spans": [],
         "source_pair_id": "p1", "variant": "before", "category": "Coherencia o claridad"},
        {"case_id": "p1:after", "fragment": "La unidad repitió el acto.",
         "expected_finding": False, "acceptable_spans": [],
         "source_pair_id": "p1", "variant": "after", "category": "Coherencia o claridad"},
        {"case_id": "p2:before", "fragment": "Se informó a la entidad debía responder.",
         "expected_finding": True, "acceptable_spans": ["entidad debía"],
         "source_pair_id": "p2", "variant": "before", "category": "Ortografía o gramática"},
        {"case_id": "p2:after", "fragment": "Se informó a la entidad que debía responder.",
         "expected_finding": False, "acceptable_spans": [],
         "source_pair_id": "p2", "variant": "after", "category": "Ortografía o gramática"},
    ]


def _inputs():
    synthetic = load_context_bank("tests/data/editorial_context_cases.json")["cases"]
    real = _real_cases()
    rule = next(item for item in load_editorial_catalog()["rules"]
                if item["rule_id"] == "ASF-ED-I-CONTEXT")
    criteria = load_model_registry()["approval_criteria"]
    return synthetic, real, rule, criteria


def test_four_gates_run_in_order_with_three_repetitions():
    synthetic, real, rule, criteria = _inputs()
    provider = OracleProvider(synthetic + real)
    result = evaluate_model_sequence(provider, synthetic, real, rule, criteria, repetitions=3)
    assert result["status"] == "passed"
    assert [(item["stage"], item["status"], item["metrics"]["cases"])
            for item in result["stages"]] == [
                ("smoke", "passed", 2), ("hard", "passed", 10),
                ("final", "passed", 30), ("real_paired", "passed", 4),
            ]
    assert provider.calls == (2 + 10 + 30 + 4) * 3


def test_gate_failure_stops_later_provider_calls():
    synthetic, real, rule, criteria = _inputs()
    provider = OracleProvider(synthetic + real, always_negative=True)
    result = evaluate_model_sequence(provider, synthetic, real, rule, criteria, repetitions=3)
    assert [item["status"] for item in result["stages"]] == [
        "failed", "not_run", "not_run", "not_run"
    ]
    assert provider.calls == 6


def test_synthetic_screen_never_runs_or_reports_real_gate():
    synthetic, real, rule, criteria = _inputs()
    provider = OracleProvider(synthetic)
    result = evaluate_model_sequence(
        provider, synthetic, None, rule, criteria, repetitions=3, include_real=False
    )
    assert result["status"] == "passed"
    assert result["evaluation_scope"] == "synthetic_screening_only"
    assert result["real_bank_coverage"] is None
    assert [(item["stage"], item["metrics"]["cases"]) for item in result["stages"]] == [
        ("smoke", 2), ("hard", 10), ("final", 30),
    ]
    assert provider.calls == (2 + 10 + 30) * 3


def test_stage_callback_receives_incremental_checkpoints():
    synthetic, _, rule, criteria = _inputs()
    provider = OracleProvider(synthetic)
    checkpoints = []
    result = evaluate_model_sequence(
        provider, synthetic, None, rule, criteria, repetitions=3, include_real=False,
        stage_callback=lambda name, stages: checkpoints.append((name, len(stages))),
    )
    assert result["status"] == "passed"
    assert checkpoints == [("smoke", 1), ("hard", 2), ("final", 3)]


def test_real_bank_accepts_expanded_and_compact_pairs(tmp_path):
    expanded = tmp_path / "expanded.json"
    expanded.write_text(json.dumps({
        "schema_version": "editorial-paired-evaluation-bank-1.0",
        "privacy": {"contains_raw_institutional_text": True},
        "cases": _real_cases(),
    }), encoding="utf-8")
    assert len(load_real_paired_bank(expanded)["cases"]) == 4

    compact = tmp_path / "compact.json"
    compact.write_text(json.dumps({
        "privacy": {"contains_raw_institutional_text": True},
        "pairs": [{"pair_id": "x", "before": "volvió a repetir", "after": "repitió",
                   "acceptable_spans": ["volvió a repetir"], "category": "claridad"}],
    }), encoding="utf-8")
    assert [item["variant"] for item in load_real_paired_bank(compact)["cases"]] == ["before", "after"]


def test_real_bank_rejects_privacy_or_incomplete_pair(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"privacy": {}, "cases": _real_cases()}), encoding="utf-8")
    with pytest.raises(ValueError, match="contains_raw"):
        load_real_paired_bank(path)
    path.write_text(json.dumps({
        "privacy": {"contains_raw_institutional_text": True},
        "cases": _real_cases()[:1],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="incompletos"):
        load_real_paired_bank(path)


def test_registry_candidates_and_hardware_preflight():
    registry = load_model_registry()
    statuses = {item["model_id"]: item["status"] for item in registry["models"]}
    assert statuses["qwen3.5:9b"] == statuses["gemma3:12b"] == "rejected"
    assert statuses["qwen3.5:27b"] == "experimental"
    assert statuses["qwen3.5:4b"] == statuses["qwen3:8b"] == "rejected"
    assert not _model_preflight("qwen3.5:27b", registry, 16)["eligible_to_run"]
    assert _model_preflight("qwen3.5:27b", registry, 24)["eligible_to_run"]
    assert not _model_preflight("qwen3.5:9b", registry, None, {"qwen3:8b"})["eligible_to_run"]


def test_cli_preflight_never_constructs_provider(tmp_path):
    real = tmp_path / "real.json"
    real.write_text(json.dumps({
        "schema_version": "editorial-paired-evaluation-bank-1.0",
        "privacy": {"contains_raw_institutional_text": True},
        "cases": _real_cases(),
    }), encoding="utf-8")
    output = tmp_path / "preflight.json"

    def forbidden_factory(config):
        raise AssertionError("El preflight no debe contactar al proveedor")

    assert main(["--preflight", "--real-bank", str(real), "--models", "qwen3.5:27b",
                 "--available-models", "qwen3.5:27b", "--accelerator-memory-gb", "24",
                 "--output", str(output)], provider_factory=forbidden_factory) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "preflight_complete"
    assert payload["results"] == []


def test_cli_synthetic_preflight_does_not_require_real_bank(tmp_path):
    output = tmp_path / "synthetic-preflight.json"

    def forbidden_factory(config):
        raise AssertionError("El preflight no debe contactar al proveedor")

    assert main([
        "--preflight", "--synthetic-only", "--models", "qwen3.5:27b",
        "--available-models", "qwen3.5:27b", "--accelerator-memory-gb", "24",
        "--real-bank", str(tmp_path / "does-not-exist.json"), "--output", str(output),
    ], provider_factory=forbidden_factory) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evaluation_scope"] == "synthetic_screening_only"
    assert payload["prompt_version"] == "editorial-context-2.1"
    assert len(payload["prompt_sha256"]) == 64
    assert payload["real_dataset"] is None
    assert payload["selected_model"] is None
    assert payload["stage_case_counts"] == {"smoke": 2, "hard": 10, "final": 30}


def test_cli_synthetic_pass_is_screening_not_approval(tmp_path):
    synthetic = load_context_bank("tests/data/editorial_context_cases.json")["cases"]
    output = tmp_path / "synthetic-result.json"

    assert main([
        "--synthetic-only", "--models", "qwen3.5:27b",
        "--available-models", "qwen3.5:27b", "--accelerator-memory-gb", "24",
        "--output", str(output),
    ], provider_factory=lambda config: OracleProvider(synthetic)) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "synthetic_screen_passed"
    assert payload["screened_model"] == "qwen3.5:27b"
    assert payload["selected_model"] is None
