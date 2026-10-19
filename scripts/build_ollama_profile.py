"""Convierte una evaluación aprobada en un perfil mínimo y versionable de Ollama."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from revisor_crf.editorial import EDITORIAL_PROMPT_VERSION
from revisor_crf.ollama_profile import SCHEMA_VERSION, load_ollama_profile


def build_profile(evaluation_path: Path, output_path: Path, *, digest: str) -> dict:
    raw = evaluation_path.read_bytes()
    evaluation = json.loads(raw.decode("utf-8-sig"))
    scope = evaluation.get("evaluation_scope")
    if scope == "synthetic_screening_only":
        model_id = evaluation.get("screened_model")
        status = "synthetic_screen_passed"
        if evaluation.get("status") != status or evaluation.get("selected_model") is not None:
            raise ValueError("La evaluación sintética no superó todas las compuertas.")
    elif scope == "full_institutional":
        model_id = evaluation.get("selected_model")
        status = "approved_institutional"
        if evaluation.get("status") != "approved":
            raise ValueError("La evaluación institucional no aprobó un modelo.")
    else:
        raise ValueError("El alcance de la evaluación no es compatible.")
    result = next(
        (item for item in evaluation.get("results", []) if item.get("model") == model_id), None
    )
    if not result or result.get("status") != "passed":
        raise ValueError("No existe evidencia aprobatoria para el modelo seleccionado.")
    final_stage = result.get("stages", [])[-1]
    metrics = final_stage.get("metrics") or {}
    aggregate = {
        key: metrics.get(key)
        for key in (
            "cases", "repetitions", "precision", "recall", "accuracy",
            "prediction_agreement", "invalid_responses", "unsafe_suggestions",
            "duration_seconds",
        )
    }
    evidence_sha = hashlib.sha256(raw).hexdigest()
    version_material = f"{model_id}|{digest}|{evidence_sha}|{EDITORIAL_PROMPT_VERSION}"
    source_commit = str(evaluation.get("source_commit") or "")
    if len(source_commit) != 40 or any(char not in "0123456789abcdef" for char in source_commit):
        raise ValueError("La evaluación no registra un commit Git completo y válido.")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "profile_version": "ollama-" + hashlib.sha256(version_material.encode()).hexdigest()[:12],
        "status": status,
        "provider": "ollama",
        "model": {"id": model_id, "digest": digest},
        "prompt_version": EDITORIAL_PROMPT_VERSION,
        "evaluation": {
            "sha256": evidence_sha,
            "source_commit": source_commit,
            "scope": scope,
        },
        "metrics": aggregate,
        "privacy": {"contains_raw_text": False, "safe_for_version_control": True},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_ollama_profile(output_path)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation")
    parser.add_argument("--digest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        payload = build_profile(Path(args.evaluation), Path(args.output), digest=args.digest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Perfil {payload['status']} creado para {payload['model']['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
