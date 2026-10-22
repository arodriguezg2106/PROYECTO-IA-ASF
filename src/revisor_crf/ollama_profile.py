"""Perfil inmutable para habilitar Ollama después de una evaluación reproducible."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


SCHEMA_VERSION = "ollama-evaluation-profile-1.0"
VALID_STATUSES = {"synthetic_screen_passed", "approved_institutional"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


@dataclass(frozen=True)
class OllamaProfile:
    profile_version: str
    status: str
    model_id: str
    model_digest: str
    prompt_version: str
    evaluation_sha256: str
    source_commit: str
    metrics: dict
    sha256: str

    @property
    def synthetic_only(self) -> bool:
        return self.status == "synthetic_screen_passed"


def load_ollama_profile(path: str | Path) -> OllamaProfile:
    source = Path(path)
    try:
        raw = source.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer el perfil de Ollama: {source}") from exc
    required = {
        "schema_version", "profile_version", "status", "provider", "model",
        "prompt_version", "evaluation", "metrics", "privacy",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError("El perfil de Ollama contiene campos faltantes o desconocidos.")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("status") not in VALID_STATUSES:
        raise ValueError("El esquema o estado del perfil de Ollama no es válido.")
    if data.get("provider") != "ollama":
        raise ValueError("El perfil no corresponde al proveedor Ollama.")
    model = data.get("model")
    if not isinstance(model, dict) or set(model) != {"id", "digest"}:
        raise ValueError("El modelo del perfil de Ollama es inválido.")
    model_id = str(model.get("id") or "").strip()
    digest = str(model.get("digest") or "").strip()
    if model_id not in {"qwen3.5:9b", "gemma3:12b", "qwen3.5:27b"} or not _DIGEST_RE.fullmatch(digest):
        raise ValueError("El identificador o digest del modelo de Ollama no es válido.")
    evaluation = data.get("evaluation")
    if not isinstance(evaluation, dict) or set(evaluation) != {"sha256", "source_commit", "scope"}:
        raise ValueError("La evidencia de evaluación del perfil es inválida.")
    expected_scope = (
        "synthetic_screening_only"
        if data["status"] == "synthetic_screen_passed"
        else "full_institutional"
    )
    if evaluation.get("scope") != expected_scope:
        raise ValueError("El alcance del perfil no coincide con su estado de aprobación.")
    if not _SHA256_RE.fullmatch(str(evaluation.get("sha256") or "")):
        raise ValueError("El hash de la evaluación no es un SHA-256 válido.")
    if not _COMMIT_RE.fullmatch(str(evaluation.get("source_commit") or "")):
        raise ValueError("El commit de origen no es un SHA-1 completo válido.")
    if data.get("privacy") != {
        "contains_raw_text": False,
        "safe_for_version_control": True,
    }:
        raise ValueError("El perfil de Ollama no acredita minimización de datos.")
    for value, label in (
        (data.get("profile_version"), "profile_version"),
        (data.get("prompt_version"), "prompt_version"),
        (evaluation.get("sha256"), "evaluation.sha256"),
        (evaluation.get("source_commit"), "evaluation.source_commit"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"El campo {label} del perfil de Ollama es obligatorio.")
    if not isinstance(data.get("metrics"), dict):
        raise ValueError("Las métricas del perfil de Ollama son inválidas.")
    return OllamaProfile(
        profile_version=data["profile_version"],
        status=data["status"],
        model_id=model_id,
        model_digest=digest,
        prompt_version=data["prompt_version"],
        evaluation_sha256=evaluation["sha256"],
        source_commit=evaluation["source_commit"],
        metrics=data["metrics"],
        sha256=hashlib.sha256(raw).hexdigest(),
    )
