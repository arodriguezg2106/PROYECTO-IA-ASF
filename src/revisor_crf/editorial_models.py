"""Registro y compuerta de aprobación de proveedores editoriales."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name("editorial_models.json")
VALID_STATUSES = {"experimental", "approved", "rejected", "unavailable"}


@dataclass(frozen=True)
class ModelDescriptor:
    model_id: str
    provider: str
    status: str
    capabilities: tuple[str, ...]
    context_limit: int | None
    timeout_seconds: float | None
    reason: str | None = None
    evaluated_at: str | None = None


def load_model_registry(path=None):
    source = Path(path) if path else REGISTRY_PATH
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Registro de modelos editoriales inválido: {source}") from exc
    seen = set()
    for item in data.get("models", []):
        if item.get("status") not in VALID_STATUSES or not item.get("model_id"):
            raise ValueError("Registro de modelos editoriales incompleto.")
        if item["model_id"] in seen:
            raise ValueError("Registro de modelos editoriales duplicado.")
        seen.add(item["model_id"])
    return data


def model_descriptor(model_id, registry=None):
    data = registry or load_model_registry()
    item = next((row for row in data.get("models", []) if row["model_id"] == model_id), None)
    if item is None:
        return ModelDescriptor(model_id, "ollama", "unavailable", (), None, None,
                               "El modelo no figura en el registro aprobado.")
    return ModelDescriptor(
        model_id=item["model_id"], provider=item.get("provider", "ollama"),
        status=item["status"], capabilities=tuple(item.get("capabilities", ())),
        context_limit=item.get("context_limit"), timeout_seconds=item.get("timeout_seconds"),
        reason=item.get("reason"), evaluated_at=item.get("evaluated_at"),
    )


def authorize_model(model_id, *, experimental=False, registry=None):
    descriptor = model_descriptor(model_id, registry)
    if descriptor.status == "approved":
        return descriptor
    if experimental:
        return descriptor
    raise ValueError(
        f"El modelo editorial {model_id!r} tiene estado {descriptor.status!r}; "
        "use el modo experimental explícito para evaluarlo."
    )


def evaluation_passes(metrics, criteria, *, repetitions):
    return (
        metrics.get("precision", 0) >= criteria["minimum_precision"]
        and metrics.get("recall", 0) >= criteria["minimum_recall"]
        and metrics.get("accuracy", 0) >= criteria["minimum_accuracy"]
        and metrics.get("prediction_agreement", 0) >= criteria["minimum_prediction_agreement"]
        and repetitions >= criteria["minimum_repetitions"]
        and metrics.get("invalid_responses", 1) == criteria["invalid_responses"]
        and metrics.get("unsafe_suggestions", 1) == criteria["unsafe_suggestions"]
    )
