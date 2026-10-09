"""Evalúa modelos contextuales mediante cuatro compuertas consecutivas."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from revisor_crf.editorial import EditorialConfig, OllamaEditorialProvider, load_editorial_catalog
from revisor_crf.editorial_context_bank import load_context_bank
from revisor_crf.editorial_model_evaluation import (
    build_stage_cases,
    evaluate_model_sequence,
    load_real_paired_bank,
)
from revisor_crf.editorial_models import load_model_registry, model_descriptor


DEFAULT_MODELS = "qwen3.5:9b,gemma3:12b"
DEFAULT_REAL_BANK = "results/editorial_revision_validation/paired_evaluation_bank.json"


def _model_preflight(model_id, registry, accelerator_memory_gb, available_models=None):
    descriptor = model_descriptor(model_id, registry)
    item = next((row for row in registry["models"] if row["model_id"] == model_id), {})
    required = item.get("hardware_requirements", {}).get("minimum_accelerator_memory_gb")
    reasons = []
    if descriptor.status == "unavailable":
        reasons.append("model_not_registered")
    if descriptor.status == "rejected":
        reasons.append("model_rejected")
    if available_models is not None and model_id not in available_models:
        reasons.append("model_not_available_locally")
    if required is not None and (accelerator_memory_gb is None or accelerator_memory_gb < required):
        reasons.append("insufficient_or_unreported_accelerator_memory")
    return {
        "model": model_id,
        "registry_status": descriptor.status,
        "minimum_accelerator_memory_gb": required,
        "reported_accelerator_memory_gb": accelerator_memory_gb,
        "eligible_to_run": not reasons,
        "reasons": reasons,
    }


def main(argv=None, *, provider_factory=None):
    parser = argparse.ArgumentParser(
        description=("Ejecuta en orden smoke (2), difícil (10), final sintético (30) "
                     "y banco real pareado; se detiene al fallar una compuerta."))
    parser.add_argument("--dataset", default="tests/data/editorial_context_cases.json")
    parser.add_argument("--real-bank", default=DEFAULT_REAL_BANK,
                        help="JSON local con texto institucional; debe permanecer fuera de Git")
    parser.add_argument("--config", default="editorial-config.example.toml")
    parser.add_argument("--models", default=DEFAULT_MODELS,
                        help="Modelos registrados, separados por comas")
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Mínimo 3; se aplica a cada compuerta")
    parser.add_argument("--accelerator-memory-gb", type=float,
                        help="Memoria de acelerador acreditada; obligatoria para modelos condicionados")
    parser.add_argument("--available-models",
                        help="Inventario local conocido, separado por comas; no consulta Ollama")
    parser.add_argument("--real-categories",
                        default="Ortografía o gramática,Coherencia o claridad",
                        help="Categorías reales que el proveedor declara cubrir")
    parser.add_argument("--preflight", action="store_true",
                        help="Valida registro, bancos y hardware sin contactar Ollama")
    parser.add_argument("--output", default="results/editorial_context/staged-model-evaluation.json")
    args = parser.parse_args(argv)
    try:
        registry = load_model_registry()
        minimum = registry["approval_criteria"]["minimum_repetitions"]
        if args.repetitions < minimum:
            raise ValueError(f"--repetitions debe ser al menos {minimum}.")
        models = [item.strip() for item in args.models.split(",") if item.strip()]
        if not models:
            raise ValueError("Debe indicar al menos un modelo.")
        dataset = load_context_bank(args.dataset)
        real_bank = load_real_paired_bank(args.real_bank)
        available = ({item.strip() for item in args.available_models.split(",") if item.strip()}
                     if args.available_models is not None else None)
        real_categories = tuple(item.strip() for item in args.real_categories.split(",") if item.strip())
        if not real_categories:
            raise ValueError("--real-categories no puede quedar vacío.")
        stage_cases = build_stage_cases(dataset["cases"], real_bank["cases"],
                                        real_categories=real_categories)
        preflight = [_model_preflight(item, registry, args.accelerator_memory_gb, available)
                     for item in models]
        payload = {
            "schema_version": "editorial-context-model-gates-1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "synthetic_dataset": dataset["schema_version"],
            "real_dataset": real_bank.get("schema_version"),
            "real_dataset_path_in_output": False,
            "criteria": registry["approval_criteria"],
            "stage_case_counts": {name: len(cases) for name, cases in stage_cases.items()},
            "real_categories": list(real_categories),
            "preflight": preflight,
            "results": [],
            "selected_model": None,
            "status": "preflight_complete" if args.preflight else "no_model_met_criteria",
        }
        if not args.preflight:
            base = EditorialConfig.load(args.config)
            factory = provider_factory or (lambda config: OllamaEditorialProvider(config))
            rule = next(item for item in load_editorial_catalog()["rules"]
                        if item["rule_id"] == "ASF-ED-I-CONTEXT")
            for check in preflight:
                if not check["eligible_to_run"]:
                    payload["results"].append({
                        "model": check["model"], "status": "preflight_failed",
                        "reasons": check["reasons"],
                    })
                    continue
                config = replace(base, ollama_enabled=True, experimental_model=True,
                                 model=check["model"], temperature=0.0)
                result = evaluate_model_sequence(
                    factory(config), dataset["cases"], real_bank["cases"], rule,
                    registry["approval_criteria"], repetitions=args.repetitions,
                    real_categories=real_categories,
                )
                payload["results"].append({"model": check["model"], **result})
            passed = [item for item in payload["results"] if item.get("status") == "passed"]
            if passed:
                payload["selected_model"] = passed[0]["model"]
                payload["status"] = "approved"
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Evaluación por compuertas guardada en {target}; estado: {payload['status']}")
        if args.preflight:
            return 0 if all(item["eligible_to_run"] for item in preflight) else 2
        return 0 if payload["selected_model"] else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, StopIteration) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
