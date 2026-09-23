"""Evalúa modelos locales y selecciona el más preciso dentro del límite de tiempo."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from revisor_crf.semantic import OllamaProvider, SemanticConfig
from revisor_crf.semantic_evaluation import evaluate_provider, select_model


def load_records(path: Path) -> list[dict]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("split") != "validation":
            continue
        if not record.get("approved_by") or "case" not in record or "expected_relation" not in record:
            raise ValueError(f"Registro semántico inválido en la línea {line_number}.")
        records.append(record)
    if not records:
        raise ValueError("El dataset no contiene registros de validación aprobados.")
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compara modelos semánticos locales.")
    parser.add_argument("dataset")
    parser.add_argument("--config", required=True)
    parser.add_argument("--models", default="qwen3.5:4b,qwen3:4b-instruct")
    parser.add_argument("--output", default="results/semantic_eval/model-selection.json")
    args = parser.parse_args(argv)
    try:
        records = load_records(Path(args.dataset))
        base = SemanticConfig.load(args.config)
        results = []
        for model in [value.strip() for value in args.models.split(",") if value.strip()]:
            config = replace(base, model=model)
            provider = OllamaProvider(config)
            results.append({"model": model, "metadata": provider.metadata(),
                            "metrics": evaluate_provider(provider, records, config.batch_size)})
        selected = select_model(results)
        payload = {
            "schema_version": "semantic-model-selection-1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "criteria": {"minimum_precision": 0.98, "minimum_accuracy": 0.95,
                         "maximum_duration_seconds": 600},
            "results": results, "selected_model": selected["model"] if selected else None,
            "status": "approved" if selected else "no_model_met_criteria",
        }
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Evaluación guardada en {target}; modelo: {payload['selected_model'] or 'ninguno'}")
        return 0 if selected else 2
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
