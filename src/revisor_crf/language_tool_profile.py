"""Perfil auditable de reglas de LanguageTool aprobadas para Revisor-CRF."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


SCHEMA_VERSION = "languagetool-profile-1.0"
APPROVED_STATUSES = {"approved_for_demo", "approved_for_pilot"}


@dataclass(frozen=True)
class LanguageToolProfile:
    profile_version: str
    status: str
    provider_version: str
    language: str
    approved_rule_ids: tuple[str, ...]
    accepted_terms: tuple[str, ...]
    excluded_categories: tuple[str, ...]
    source: dict
    metrics: dict
    sha256: str

    @property
    def approved(self) -> bool:
        return self.status in APPROVED_STATUSES


def _strings(data: dict, name: str) -> tuple[str, ...]:
    value = data.get(name, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"El perfil de LanguageTool contiene {name} inválido.")
    if len(value) != len(set(value)):
        raise ValueError(f"El perfil de LanguageTool contiene duplicados en {name}.")
    return tuple(value)


def load_language_tool_profile(path: str | Path, *, require_approved: bool = True) -> LanguageToolProfile:
    source_path = Path(path)
    try:
        raw = source_path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer el perfil de LanguageTool: {source_path}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("El esquema del perfil de LanguageTool no es compatible.")
    required = {
        "schema_version", "profile_version", "status", "provider", "approved_rule_ids",
        "accepted_terms", "excluded_categories", "source", "metrics", "privacy",
    }
    if set(data) != required:
        raise ValueError("El perfil de LanguageTool contiene campos faltantes o desconocidos.")
    provider = data.get("provider")
    if not isinstance(provider, dict) or set(provider) != {"name", "version", "language"}:
        raise ValueError("El proveedor del perfil de LanguageTool es inválido.")
    if provider.get("name") != "LanguageTool" or provider.get("version") != "6.6" or provider.get("language") != "es":
        raise ValueError("El perfil requiere LanguageTool 6.6 con idioma es.")
    privacy = data.get("privacy")
    if privacy != {"contains_raw_text": False, "safe_for_version_control": True}:
        raise ValueError("El perfil de LanguageTool no acredita minimización de datos.")
    status = str(data.get("status") or "")
    if status not in {*APPROVED_STATUSES, "candidate", "rejected", "insufficient_evidence"}:
        raise ValueError("El estado del perfil de LanguageTool es inválido.")
    rules = _strings(data, "approved_rule_ids")
    if require_approved and (status not in APPROVED_STATUSES or not rules):
        raise ValueError("LanguageTool requiere un perfil aprobado con reglas en lista blanca.")
    if not isinstance(data.get("source"), dict) or not isinstance(data.get("metrics"), dict):
        raise ValueError("Las métricas o fuentes del perfil de LanguageTool son inválidas.")
    return LanguageToolProfile(
        profile_version=str(data.get("profile_version") or ""),
        status=status,
        provider_version="6.6",
        language="es",
        approved_rule_ids=rules,
        accepted_terms=_strings(data, "accepted_terms"),
        excluded_categories=_strings(data, "excluded_categories"),
        source=data["source"],
        metrics=data["metrics"],
        sha256=hashlib.sha256(raw).hexdigest(),
    )
