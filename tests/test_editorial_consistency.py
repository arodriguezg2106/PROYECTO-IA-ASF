import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from revisor_crf import editorial_consistency as p


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
METADATA = {"model": p.MODEL, "digest": "test-model-digest", "capabilities": ["completion"]}


def experiment(tmp_path, *, fast=False):
    bank = p.load_bank()
    p.freeze_bank(tmp_path, bank, "Revisor de pruebas", p.digest(bank), START)
    result = p.ConsistencyExperiment(tmp_path, bank, "test-commit", "test-implementation")
    if fast:
        result.save = lambda: None
    return result


def finding(case, **updates):
    return {"rule_id": "ASF-ED-I-CONTEXT", "category": "grammar", "severity": "warning",
            "problem_span": (case["acceptable_spans"] or [case["fragment"]])[0],
            "message": "Evidencia de prueba", "suggested_text": None, "confidence": .95, **updates}


def oracle(exp, *, behavior=None, calls=None):
    cases = {row["case_id"]: row for row in exp.bank["cases"]}

    def send(task, request, prompt, attempt):
        if calls is not None:
            calls.append(task["task_id"])
        assert "expected_finding" not in request and "rationale" not in request
        assert "acceptable_spans" not in request and "focus" not in request
        assert set(request) == {"fragment", "location", "rules", "criteria", "protected_elements"}
        case = cases[task["case_id"]]
        rows = [finding(case)] if case["expected_finding"] else []
        if behavior:
            rows = behavior(task, case, rows)
        attempt.update(status="received", returned_model=p.MODEL, done_reason="stop",
                       prompt_eval_count=100, prompt_eval_cached_count=40, eval_count=20,
                       duration_seconds=.1)
        return json.dumps({"findings": rows}, ensure_ascii=False)

    return send


def run_final(exp, send):
    exp.run("selection", METADATA, send, START)
    exp.run("validation-a", METADATA, send, START + timedelta(hours=1))
    return exp.run("validation-b", METADATA, send, START + timedelta(hours=25))


def test_bank_is_balanced_distinct_and_does_not_reuse_prompt_examples():
    bank = p.load_bank()
    for case in bank["cases"]:
        assert all(case["fragment"] not in prompt for prompt in p.PROMPTS.values())
    assert sum(case["expected_finding"] for case in bank["cases"]) == 15
    assert len({case["fragment"] for case in bank["cases"]}) == 30
    assert "pending_human_review" == bank["review_status"]
    from pathlib import Path
    review_path = Path(__file__).resolve().parents[1] / "docs/banco_consistencia_gemma4.md"
    assert review_path.read_text("utf-8") == p.review_markdown(bank)


def test_review_is_explicit_bound_to_hash_and_immutable(tmp_path):
    bank = p.load_bank()
    with pytest.raises(p.ProtocolError, match="pending_human_review"):
        p.ConsistencyExperiment(tmp_path, bank, "x", "x")
    with pytest.raises(p.ProtocolError, match="review_required"):
        p.freeze_bank(tmp_path, bank, "reviewer", "wrong")
    p.freeze_bank(tmp_path, bank, "reviewer", p.digest(bank))
    changed = copy.deepcopy(bank)
    changed["cases"][0]["rationale"] += " Cambio"
    with pytest.raises(p.ProtocolError, match="reviewed_bank_changed"):
        p.reviewed_bank(tmp_path, changed)
    with pytest.raises(p.ProtocolError, match="already_frozen"):
        p.freeze_bank(tmp_path, bank, "another", p.digest(bank))


def test_complete_protocol_persists_180_calls_and_reports(tmp_path):
    exp = experiment(tmp_path)
    calls = []
    report = run_final(exp, oracle(exp, calls=calls))
    assert len(calls) == len(set(calls)) == 180
    assert report["conclusion"] == "candidato consistente para piloto sintético"
    assert report["selected_model"] is None
    assert report["final_stability"]["decision_rule"] == 1
    assert report["usage"]["reported_input_tokens"] == 18000
    assert report["usage"]["reported_cached_input_tokens"] == 7200
    assert p.read_json(tmp_path / "report.json") == report
    assert "candidato consistente" in (tmp_path / "report.md").read_text("utf-8")
    assert all(row["parameters"] == p.PARAMETERS and row["response_text"] for row in exp.state["attempts"])
    assert "private-token" not in (tmp_path / "experiment.json").read_text("utf-8")
    exp.run("validation-b", METADATA, oracle(exp, calls=calls), START + timedelta(hours=25))
    assert len(calls) == 180


def test_always_empty_is_stable_but_insufficient_and_blocks_holdout(tmp_path):
    exp = experiment(tmp_path, fast=True)
    report = exp.run("selection", METADATA, oracle(exp, behavior=lambda *args: []), START)
    assert report["selected_prompt"] is None
    assert report["conclusion"] == "estable pero insuficiente"
    for profile in report["phases"]["selection"]["profiles"].values():
        assert profile["metrics"]["precision"] is None
        assert profile["metrics"]["recall"] == 0
        assert profile["stability"]["decision_rule"] == 1
    with pytest.raises(p.ProtocolError, match="no_prompt_passed"):
        exp.run("validation-a", METADATA, oracle(exp), START)
    assert len(exp.state["attempts"]) == 60


def test_constant_false_alarms_fail_quality(tmp_path):
    exp = experiment(tmp_path, fast=True)
    report = exp.run("selection", METADATA, oracle(exp, behavior=lambda task, case, rows: [finding(case)]), START)
    assert report["selected_prompt"] is None
    assert report["phases"]["selection"]["profiles"]["research"]["metrics"]["fp"] == 15


def test_alternating_decisions_can_be_useful_but_unstable(tmp_path):
    exp = experiment(tmp_path, fast=True)

    def alternate(task, case, rows):
        if task["phase"] != "selection":
            missed = "C11" if task["repetition"] % 2 else "C12"
            if case["case_id"] == missed:
                return []
        return rows

    report = run_final(exp, oracle(exp, behavior=alternate))
    assert report["conclusion"] == "útil pero inestable"
    assert report["final_stability"]["decision_rule"] == .9


def test_explanation_wording_does_not_affect_consistency(tmp_path):
    exp = experiment(tmp_path, fast=True)

    def change_message(task, case, rows):
        for row in rows:
            row["message"] = f"Explicación alternativa {task['repetition']} {task['phase']}"
        return rows

    report = run_final(exp, oracle(exp, behavior=change_message))
    assert report["final_stability"]["decision_rule"] == 1
    assert report["conclusion"] == "candidato consistente para piloto sintético"


@pytest.mark.parametrize("raw", ["no es JSON", '{"findings":true}', '{"findings":[{}]}', "[]"])
def test_invalid_json_or_schema_never_passes(raw):
    case = p.load_bank()["cases"][0]
    result = p.grade(case, raw)
    assert result["invalid_responses"] == 1
    assert result["signature"] is None
    assert not p.quality_passes(p.metrics([result]))


def test_literal_but_irrelevant_evidence_and_protected_changes_are_rejected():
    case = next(row for row in p.load_bank()["cases"] if row["case_id"] == "C12")
    row = finding(case, problem_span="El inventario", suggested_text=case["fragment"].replace("18", "19"))
    result = p.grade(case, json.dumps({"findings": [row]}))
    assert result["fn"] == result["fp"] == result["unsafe_suggestions"] == 1
    assert not p.quality_passes(p.metrics([result]))


def test_nonliteral_and_truncated_responses_are_invalid():
    case = p.load_bank()["cases"][0]
    result = p.grade(case, json.dumps({"findings": [finding(case, problem_span="inventado")]}))
    assert result["invalid_responses"] == 1
    assert p.grade(case, '{"findings":[]}', done_reason="length")["invalid_responses"] == 1


def test_transport_stop_and_resume_do_not_duplicate_attempts(tmp_path):
    exp = experiment(tmp_path)
    calls = []

    def stopped(task, request, prompt, attempt):
        calls.append(task["task_id"])
        attempt["status"] = "error"
        raise RuntimeError("cloud_http_429")

    with pytest.raises(p.ProtocolError, match="cloud_http_429"):
        exp.run("selection", METADATA, stopped, START)
    stored = p.read_json(tmp_path / "experiment.json")
    assert len(stored["attempts"]) == 1
    assert stored["phases"]["selection"]["status"] == "stopped"
    resumed = p.ConsistencyExperiment(tmp_path, p.load_bank(), "test-commit", "test-implementation")
    resumed.run("selection", METADATA, oracle(resumed, calls=calls), START)
    assert len(calls) == len(set(calls)) == 60
    assert resumed.state["attempts"][0]["grade"]["invalid_responses"] == 1


def test_crash_after_journaling_never_retries_uncertain_call(tmp_path):
    exp = experiment(tmp_path)
    calls = []

    def crash(task, request, prompt, attempt):
        calls.append(task["task_id"])
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        exp.run("selection", METADATA, crash, START)
    resumed = p.ConsistencyExperiment(tmp_path, p.load_bank(), "test-commit", "test-implementation")
    resumed.run("selection", METADATA, oracle(resumed, calls=calls), START)
    assert len(calls) == len(set(calls)) == 60
    assert resumed.state["attempts"][0]["status"] == "uncertain"


def test_temporal_window_and_model_change_block_requests(tmp_path):
    exp = experiment(tmp_path, fast=True)
    send = oracle(exp)
    exp.run("selection", METADATA, send, START)
    exp.run("validation-a", METADATA, send, START)
    with pytest.raises(p.ProtocolError, match="too_early"):
        exp.run("validation-b", METADATA, send, START + timedelta(hours=23))
    with pytest.raises(p.ProtocolError, match="window_expired"):
        exp.run("validation-b", METADATA, send, START + timedelta(hours=73))
    assert len(exp.state["attempts"]) == 120
    with pytest.raises(p.ProtocolError, match="metadata_changed"):
        exp.run("validation-b", {**METADATA, "digest": "another"}, send, START + timedelta(hours=24))
    assert exp.state["comparability"] == "not_comparable"
    assert len(exp.state["attempts"]) == 120


def test_configuration_changes_cannot_pool_results(tmp_path):
    exp = experiment(tmp_path)
    exp.save()
    with pytest.raises(p.ProtocolError, match="configuration_changed"):
        p.ConsistencyExperiment(tmp_path, p.load_bank(), "different-commit", "test-implementation")
    report = p.read_json(tmp_path / "report.json")
    assert report["comparability"] == "not_comparable"
    assert report["conclusion"] == "no validado"


def test_order_is_reproducible_and_budget_is_60_per_phase():
    bank = p.load_bank()
    first = p.schedule(bank, "selection")
    assert first == p.schedule(bank, "selection")
    assert len(first) == len({row["task_id"] for row in first}) == 60
    assert [row["case_id"] for row in first[:10]] != [row["case_id"] for row in first[10:20]]
    assert len(p.schedule(bank, "validation-a", "research")) == 60
    assert len(p.schedule(bank, "validation-b", "research")) == 60


def test_prompt_ranking_uses_recall_precision_then_tokens():
    def row(recall, precision, tokens):
        return {"quality_passed": True, "metrics": {"recall": recall, "precision": precision}, "reported_tokens": tokens}
    assert p.select_prompt({"profiles": {"conservative": row(.9, 1, 10), "research": row(1, .9, 100)}}) == "research"
    assert p.select_prompt({"profiles": {"conservative": row(1, 1, 10), "research": row(1, 1, 100)}}) == "conservative"


def test_lock_prevents_concurrent_execution(tmp_path):
    with p.experiment_lock(tmp_path):
        with pytest.raises(p.ProtocolError, match="locked"):
            with p.experiment_lock(tmp_path):
                pytest.fail("No debe abrir otro experimento")
    assert not (tmp_path / "experiment.lock").exists()


def test_preflight_is_offline_and_does_not_approve_bank(tmp_path, monkeypatch):
    import evaluate_editorial_consistency as cli
    import evaluate_ollama_cloud as cloud

    monkeypatch.setattr(cli, "DIRECTORY", tmp_path)
    monkeypatch.setattr(cli, "model_metadata", lambda: pytest.fail("No debe consultar red"))
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    assert cloud.main(["--protocol", "consistency-v1", "--preflight"]) == 0
    assert p.read_json(tmp_path / "preflight.json")["status"] == "pending_review"
    assert "C30" in (tmp_path / "bank_review.md").read_text("utf-8")
    assert not (tmp_path / "review.json").exists()
    assert cloud.main(["--protocol", "consistency-v1", "--phase", "selection"]) == 1
    assert not (tmp_path / "experiment.json").exists()


def test_completed_response_is_recovered_if_crash_precedes_grading(tmp_path):
    exp = experiment(tmp_path)
    first_id = p.schedule(exp.bank, "selection")[0]["case_id"]
    case = next(row for row in exp.bank["cases"] if row["case_id"] == first_id)

    def received_then_crashed(task, request, prompt, attempt):
        attempt.update(status="received", returned_model=p.MODEL, done_reason="stop",
                       response_text=json.dumps({"findings": [finding(case)] if case["expected_finding"] else []}))
        exp.save()
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        exp.run("selection", METADATA, received_then_crashed, START)
    resumed = p.ConsistencyExperiment(tmp_path, p.load_bank(), "test-commit", "test-implementation")
    calls = []
    report = resumed.run("selection", METADATA, oracle(resumed, calls=calls), START)
    assert len(calls) == 59
    assert resumed.state["attempts"][0]["grade"]["invalid_responses"] == 0
    assert report["selected_prompt"] is not None


def test_durable_file_replace_recovers_transient_windows_sharing_error(tmp_path, monkeypatch):
    original = p.os.replace
    attempts = []

    def sharing_error_once(source, target):
        attempts.append(target)
        if len(attempts) == 1:
            raise PermissionError("sharing violation")
        return original(source, target)

    monkeypatch.setattr(p.os, "replace", sharing_error_once)
    monkeypatch.setattr(p.time, "sleep", lambda _: None)
    p.write_json(tmp_path / "checkpoint.json", {"attempts": 1})
    assert p.read_json(tmp_path / "checkpoint.json") == {"attempts": 1}
    assert len(attempts) == 2


def test_cloud_sender_fixes_parameters_and_journals_response(tmp_path, monkeypatch):
    import evaluate_editorial_consistency as cli
    import evaluate_ollama_cloud as cloud

    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"model": p.MODEL, "message": {"content": '{"findings":[]}'},
                               "done_reason": "stop", "prompt_eval_count": 123, "eval_count": 6}).encode()

    class Opener:
        def open(self, request, timeout):
            seen.append(json.loads(request.data))
            return Response()

    monkeypatch.setattr(cloud.urllib.request, "build_opener", lambda *args: Opener())
    exp = experiment(tmp_path, fast=True)
    exp.run("selection", METADATA, cli.sender("private-token", exp), START)
    assert len(seen) == 60
    assert all(row["think"] is False and "format" not in row for row in seen)
    assert all(row["options"] == {"temperature": 0, "seed": 20260923, "num_predict": 2048} for row in seen)
    assert all(row["response_text"] == '{"findings":[]}' for row in exp.state["attempts"])
    assert "private-token" not in json.dumps(exp.state)


def test_oversized_or_duplicate_journal_is_rejected(tmp_path):
    exp = experiment(tmp_path)
    exp.state["attempts"] = [{"task_id": "same", "phase": "selection"}] * 61
    p.write_json(tmp_path / "experiment.json", exp.state)
    with pytest.raises(p.ProtocolError, match="invalid_attempt_journal"):
        p.ConsistencyExperiment(tmp_path, p.load_bank(), "test-commit", "test-implementation")


def test_cli_freeze_requires_matching_review_and_does_not_contact_api(tmp_path, monkeypatch):
    import evaluate_editorial_consistency as cli
    import evaluate_ollama_cloud as cloud

    monkeypatch.setattr(cli, "DIRECTORY", tmp_path)
    monkeypatch.setattr(cli, "model_metadata", lambda: pytest.fail("No debe consultar red"))
    arguments = ["--protocol", "consistency-v1", "--freeze-bank", "--reviewer", "Revisor"]
    assert cloud.main(arguments + ["--reviewed-bank-sha256", "incorrect"]) == 1
    assert not (tmp_path / "review.json").exists()
    assert cloud.main(arguments + ["--reviewed-bank-sha256", p.digest(p.load_bank())]) == 0
    assert p.read_json(tmp_path / "review.json")["reviewer"] == "Revisor"
    assert not (tmp_path / "experiment.json").exists()
