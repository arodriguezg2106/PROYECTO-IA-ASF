import json

import pytest

from build_ollama_profile import build_profile
from revisor_crf.ollama_profile import load_ollama_profile
from revisor_web.config import WebConfig


def _evaluation(path, *, status="synthetic_screen_passed", model="qwen3.5:9b"):
    payload = {
        "evaluation_scope": "synthetic_screening_only",
        "status": status,
        "screened_model": model if status == "synthetic_screen_passed" else None,
        "selected_model": None,
        "source_commit": "a" * 40,
        "results": [{
            "model": model,
            "status": "passed" if status == "synthetic_screen_passed" else "failed",
            "stages": [{"stage": "final", "metrics": {
                "cases": 30, "repetitions": 3, "precision": 1.0, "recall": 0.9,
                "accuracy": 0.95, "prediction_agreement": 1.0,
                "invalid_responses": 0, "unsafe_suggestions": 0,
                "duration_seconds": 10.0,
            }}],
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_profile_is_built_from_passing_evaluation_and_is_strict(tmp_path):
    evaluation = _evaluation(tmp_path / "evaluation.json")
    profile_path = tmp_path / "profile.json"
    build_profile(evaluation, profile_path, digest="sha256:" + "b" * 64)
    profile = load_ollama_profile(profile_path)
    assert profile.synthetic_only and profile.model_id == "qwen3.5:9b"
    assert profile.source_commit == "a" * 40

    data = json.loads(profile_path.read_text(encoding="utf-8"))
    data["model"]["id"] = "qwen3.5:4b"
    profile_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="identificador"):
        load_ollama_profile(profile_path)


def test_failed_evaluation_cannot_create_profile(tmp_path):
    evaluation = _evaluation(tmp_path / "failed.json", status="no_model_met_criteria")
    with pytest.raises(ValueError, match="no superó"):
        build_profile(evaluation, tmp_path / "profile.json", digest="sha256:" + "b" * 64)


def test_conditioned_27b_model_can_create_profile_only_after_passing(tmp_path):
    evaluation = _evaluation(tmp_path / "evaluation-27b.json", model="qwen3.5:27b")
    profile_path = tmp_path / "profile-27b.json"
    build_profile(evaluation, profile_path, digest="sha256:" + "c" * 64)
    assert load_ollama_profile(profile_path).model_id == "qwen3.5:27b"


def test_profile_rejects_abbreviated_source_commit(tmp_path):
    evaluation = _evaluation(tmp_path / "evaluation.json")
    payload = json.loads(evaluation.read_text(encoding="utf-8"))
    payload["source_commit"] = "abc123"
    evaluation.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="commit Git completo"):
        build_profile(evaluation, tmp_path / "profile.json", digest="sha256:" + "b" * 64)


def test_web_ollama_requires_demo_single_worker_and_matching_model(tmp_path):
    profile_path = tmp_path / "profile.json"
    build_profile(
        _evaluation(tmp_path / "evaluation.json"),
        profile_path,
        digest="sha256:" + "b" * 64,
    )
    with pytest.raises(ValueError, match="revisión editorial"):
        WebConfig(
            jobs_dir=tmp_path / "a", ollama_enabled=True, ollama_profile=profile_path,
            max_concurrent_jobs=1,
        )
    with pytest.raises(ValueError, match="modo demostración"):
        WebConfig(
            jobs_dir=tmp_path / "b", editorial_enabled=True, ollama_enabled=True,
            ollama_profile=profile_path, max_concurrent_jobs=1,
        )
    with pytest.raises(ValueError, match="no coincide"):
        WebConfig(
            jobs_dir=tmp_path / "c", demo_mode=True, editorial_enabled=True,
            ollama_enabled=True, ollama_profile=profile_path,
            ollama_model="gemma3:12b", max_concurrent_jobs=1,
        )
    config = WebConfig(
        jobs_dir=tmp_path / "d", demo_mode=True, editorial_enabled=True,
        ollama_enabled=True, ollama_profile=profile_path,
        ollama_model="qwen3.5:9b", max_concurrent_jobs=1,
    )
    assert config.ollama_enabled
