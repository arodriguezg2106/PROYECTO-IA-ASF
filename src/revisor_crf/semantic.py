"""Capa semántica local para relacionar cifras sin delegar cálculos al modelo."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import sqlite3
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Protocol, TypedDict


PROMPT_VERSION = "semantic-link-1.3"
SCHEMA_VERSION = "semantic-1.0"
CALIBRATION_VERSION = "conservative-min-1"


class SemanticRelation(str, Enum):
    SAME_CONCEPT = "same_concept"
    SAME_MEASURE = "same_measure"
    DIFFERENT_MEASURE = "different_measure"
    UNRELATED = "unrelated"
    UNCERTAIN = "uncertain"


class AmountType(str, Enum):
    BUDGET = "presupuestal"
    PAID = "pagado"
    SPENT = "ejercido"
    CONTRACTED = "contratado"
    OBSERVED = "observado"
    DIFFERENCE = "diferencia"
    UNSPECIFIED = "unspecified"


class SemanticCase(TypedDict):
    case_id: str
    table: dict
    narrative: dict
    deterministic: dict


class SemanticDecision(TypedDict):
    case_id: str
    relation: str
    table_measure: str
    narrative_measure: str
    confidence: float
    table_evidence: str
    narrative_evidence: str


RELATIONS = {relation.value for relation in SemanticRelation}
MEASURES = {measure.value for measure in AmountType}
MEASURE_PATTERNS = {
    "presupuestal": re.compile(r"\bpresupuest(?:o|al|ado|ada)s?\b", re.I),
    "pagado": re.compile(r"\bpagad[oa]s?\b", re.I),
    "ejercido": re.compile(r"\bejercid[oa]s?\b", re.I),
    "contratado": re.compile(r"\bcontratad[oa]s?\b", re.I),
    "observado": re.compile(r"\bobservad[oa]s?\b", re.I),
    "diferencia": re.compile(r"\bdiferencias?\b", re.I),
}
MONETARY_HEADER = re.compile(
    r"\b(?:importe|monto|pagad[oa]s?|ejercid[oa]s?|contratad[oa]s?|observad[oa]s?|"
    r"presupuest(?:o|al|ado|ada)s?|subtotal|total|diferencias?|precio|costo)\b", re.I,
)
STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "en", "y", "a", "por", "para", "un", "una",
    "importe", "monto", "total", "subtotal", "pesos", "peso", "fondo", "aportaciones",
}
NON_CONCEPT_TOKENS = {"uma", "umas", "pesos", "peso", "miles", "millones"}


@dataclass(frozen=True)
class SemanticConfig:
    profile: str = "local"
    provider: str = "ollama"
    base_url: str = "http://localhost:11434/api"
    model: str = "qwen3.5:4b"
    timeout_seconds: float = 120.0
    batch_size: int = 4
    max_candidates_per_table_value: int = 6
    confidence_threshold: float = 0.95
    cache_path: str = "results/semantic_cache.sqlite3"
    max_suggestions: int = 200
    bearer_token_env: str | None = None
    expected_model_digest: str | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> "SemanticConfig":
        if path is None:
            config = cls()
        else:
            source = Path(path)
            try:
                if source.suffix.lower() == ".toml":
                    values = tomllib.loads(source.read_text(encoding="utf-8"))
                    values = values.get("semantic", values)
                else:
                    values = json.loads(source.read_text(encoding="utf-8"))
                    values = values.get("semantic", values)
            except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
                raise ValueError(f"No se pudo leer la configuración semántica: {source}") from exc
            if not isinstance(values, dict):
                raise ValueError("La configuración semántica debe ser un objeto.")
            allowed = set(cls.__dataclass_fields__)
            unknown = set(values) - allowed
            if unknown:
                raise ValueError(f"Campos semánticos desconocidos: {', '.join(sorted(unknown))}")
            config = cls(**values)
        config.validate()
        return config

    def validate(self) -> None:
        if self.profile not in {"local", "institutional"}:
            raise ValueError("El perfil semántico debe ser local o institutional.")
        if self.provider not in {"ollama", "institutional"}:
            raise ValueError("El proveedor semántico debe ser ollama o institutional.")
        if not self.model.strip():
            raise ValueError("El modelo semántico no puede estar vacío.")
        if self.timeout_seconds <= 0 or self.batch_size < 1 or self.max_candidates_per_table_value < 1:
            raise ValueError("Los límites semánticos deben ser positivos.")
        if not 0.5 <= self.confidence_threshold <= 1:
            raise ValueError("El umbral semántico debe estar entre 0.5 y 1.")
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("La URL semántica debe ser HTTP(S) válida.")
        if self.profile == "local":
            try:
                local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                local = False
            if not local:
                raise ValueError("El perfil local solo permite localhost o una dirección loopback.")
        if self.profile == "institutional" and parsed.scheme != "https":
            raise ValueError("El perfil institucional requiere HTTPS.")


class SemanticProvider(Protocol):
    def analyze(self, cases: list[SemanticCase], phase: str) -> list[SemanticDecision]: ...

    def metadata(self) -> dict: ...


class StaticSemanticProvider:
    """Proveedor reproducible para pruebas e integración sin un modelo instalado."""

    def __init__(self, responses: dict[str, list[dict]] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, list[str]]] = []

    def analyze(self, cases: list[dict], phase: str) -> list[dict]:
        self.calls.append((phase, [case["case_id"] for case in cases]))
        configured = self.responses.get(phase, [])
        by_id = {item["case_id"]: item for item in configured}
        return [by_id.get(case["case_id"], {
            "case_id": case["case_id"], "relation": "uncertain",
            "table_measure": "unspecified", "narrative_measure": "unspecified",
            "confidence": 0.0, "table_evidence": "", "narrative_evidence": "",
        }) for case in cases]

    def metadata(self) -> dict:
        return {"provider": "static", "model": "test-double", "digest": "test"}


class OllamaProvider:
    def __init__(self, config: SemanticConfig):
        self.config = config

    def _request(self, path: str, payload: dict | None = None, method: str = "POST") -> dict:
        import os

        url = self.config.base_url.rstrip("/") + "/" + path.lstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.config.bearer_token_env:
            token = os.environ.get(self.config.bearer_token_env)
            if not token:
                raise RuntimeError("Falta el token del servicio semántico institucional.")
            headers["Authorization"] = f"Bearer {token}"
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"semantic_http_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("semantic_unavailable") from exc
        except (TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("semantic_invalid_transport") from exc

    def analyze(self, cases: list[dict], phase: str) -> list[dict]:
        if self.config.provider == "institutional":
            response = self._request("v1/semantic-relations", {
                "schema_version": SCHEMA_VERSION, "phase": phase,
                "model": self.config.model, "cases": cases,
            })
            return response.get("decisions", [])
        schema = response_schema([case["case_id"] for case in cases])
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt(phase)},
                {"role": "user", "content": json.dumps({"cases": cases}, ensure_ascii=False)},
            ],
            "stream": False,
            "think": False,
            "format": schema,
            "options": {"temperature": 0, "seed": 20260922},
            "keep_alive": "10m",
        }
        response = self._request("chat", payload)
        content = (response.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError("semantic_missing_content")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("semantic_invalid_json") from exc
        return result.get("decisions", []) if isinstance(result, dict) else []

    def metadata(self) -> dict:
        metadata = {"provider": self.config.provider, "model": self.config.model, "digest": None}
        if self.config.provider == "institutional":
            try:
                health = self._request("health", None, "GET")
                metadata.update({key: health.get(key) for key in ("model", "digest")})
            except RuntimeError:
                pass
            return metadata
        if self.config.provider != "ollama":
            return metadata
        try:
            tags = self._request("tags", None, "GET")
            for model in tags.get("models", []):
                if model.get("name") == self.config.model or model.get("model") == self.config.model:
                    metadata["digest"] = model.get("digest")
                    break
        except RuntimeError:
            pass
        return metadata


class SemanticCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS semantic_cache ("
            "cache_key TEXT PRIMARY KEY, response_json TEXT NOT NULL, created_at INTEGER NOT NULL)"
        )

    def get(self, key: str) -> dict | None:
        row = self.connection.execute(
            "SELECT response_json FROM semantic_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, response: dict) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO semantic_cache(cache_key,response_json,created_at) VALUES(?,?,?)",
            (key, json.dumps(response, ensure_ascii=False, separators=(",", ":")), int(time.time())),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


def system_prompt(phase: str) -> str:
    action = (
        "Relaciona cada cifra de tabla con la cifra narrativa únicamente si hablan del mismo concepto y del mismo tipo de importe."
        if phase == "associate" else
        "Verifica críticamente la relación propuesta. Recházala ante cualquier duda sobre concepto, tipo de importe, unidad o ámbito."
    )
    return (
        "Eres un componente de extracción conservador para documentos de fiscalización en español. "
        + action + " No calcules, no corrijas cifras y no inventes evidencia. "
        "same_measure significa que el concepto y el tipo de importe coinciden (por ejemplo, ambos son pagados), "
        "aunque los valores numéricos sean distintos; same_concept significa que el concepto coincide, pero el tipo "
        "de importe no coincide o no está demostrado. No compares ni exijas igualdad entre las cantidades. "
        "Usa confianza 0.99 solo cuando el concepto está expresado de forma inequívoca en ambos lados y el mismo "
        "tipo de importe aparece explícitamente en ambos; usa 0.90 o menos si hay paráfrasis, inferencia o ambigüedad. "
        "Devuelve solo el JSON exigido. Cada evidencia debe ser un substring literal del campo correspondiente: "
        "no agregues comillas, prefijos, sufijos ni explicaciones dentro del valor. Usa uncertain cuando falte información."
    )


def response_schema(case_ids: list[str]) -> dict:
    decision = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "case_id": {"type": "string", "enum": case_ids},
            "relation": {"type": "string", "enum": sorted(RELATIONS)},
            "table_measure": {"type": "string", "enum": sorted(MEASURES)},
            "narrative_measure": {"type": "string", "enum": sorted(MEASURES)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "table_evidence": {"type": "string"},
            "narrative_evidence": {"type": "string"},
        },
        "required": ["case_id", "relation", "table_measure", "narrative_measure", "confidence",
                     "table_evidence", "narrative_evidence"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"decisions": {"type": "array", "items": decision,
                                       "minItems": len(case_ids), "maxItems": len(case_ids)}},
        "required": ["decisions"],
    }


def _plain(value: str | None) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _tokens(value: str | None) -> set[str]:
    return {token for token in _plain(value).split() if len(token) > 2 and token not in STOPWORDS}


def measure_type(value: str | None) -> str:
    matches = [name for name, pattern in MEASURE_PATTERNS.items() if pattern.search(value or "")]
    return matches[0] if len(matches) == 1 else "unspecified"


def _view_key(number: dict) -> str:
    return "+".join(sorted(number.get("vistas") or ["final"]))


def _unit_signature(number: dict) -> tuple:
    return number.get("tipo"), number.get("unidad_canonica"), str(number.get("multiplicador"))


def _decimal_text(value) -> str | None:
    return str(value) if isinstance(value, Decimal) else None


def _case_payload(table: dict, narrative: dict) -> dict:
    raw = "|".join((table["id"], narrative["id"], _view_key(table)))
    case_id = "semantic-case-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return {
        "case_id": case_id,
        "table": {
            "number_id": table["id"], "value": _decimal_text(table.get("valor_normalizado")),
            "text": table.get("contexto_inmediato") or table.get("texto_original") or "",
            "row": table.get("encabezado_fila") or "",
            "column": table.get("encabezado_columna") or "",
            "result": table.get("resultado"), "view": _view_key(table),
            "unit": table.get("unidad_canonica"), "scale": str(table.get("multiplicador")),
        },
        "narrative": {
            "number_id": narrative["id"], "value": _decimal_text(narrative.get("valor_normalizado")),
            "text": narrative.get("contexto_asociacion") or narrative.get("contexto_inmediato") or "",
            "result": narrative.get("resultado"), "view": _view_key(narrative),
            "unit": narrative.get("unidad_canonica"), "scale": str(narrative.get("multiplicador")),
        },
        "deterministic": {
            "table_measure": measure_type(table.get("encabezado_columna")),
            "narrative_measure": measure_type(narrative.get("contexto_asociacion")
                                               or narrative.get("contexto_inmediato")),
        },
        "_table_number": table,
        "_narrative_number": narrative,
    }


def public_case(case: dict) -> SemanticCase:
    return {key: value for key, value in case.items() if not key.startswith("_")}


def build_semantic_cases(numbers: list[dict], config: SemanticConfig) -> list[SemanticCase]:
    tables = [number for number in numbers if number.get("tabla") and number.get("encabezado_fila")
              and isinstance(number.get("valor_normalizado"), Decimal)
              and number.get("tipo") == "importe" and number.get("confidence") != "low"
              and MONETARY_HEADER.search(number.get("encabezado_columna") or "")]
    narratives = [number for number in numbers if not number.get("tabla")
                  and isinstance(number.get("valor_normalizado"), Decimal)
                  and number.get("tipo") == "importe" and number.get("confidence") != "low"]
    cases = []
    for table in tables:
        row_tokens = _tokens(table.get("encabezado_fila"))
        concept_tokens = {
            token for token in row_tokens
            if token not in NON_CONCEPT_TOKENS
            and any(character.isalpha() for character in token)
        }
        if not concept_tokens:
            continue
        table_measure = measure_type(table.get("encabezado_columna"))
        candidates = []
        for narrative in narratives:
            if table.get("seccion") != narrative.get("seccion"):
                continue
            if _view_key(table) != _view_key(narrative) or _unit_signature(table) != _unit_signature(narrative):
                continue
            if (table.get("resultado") and narrative.get("resultado")
                    and table["resultado"] != narrative["resultado"]):
                continue
            narrative_measure = measure_type(narrative.get("contexto_asociacion")
                                             or narrative.get("contexto_inmediato"))
            # El control final exige el mismo tipo explícito o que ambos lados
            # sean genéricos. Evita enviar al modelo pares que nunca podrían
            # producir una alerta, como Tuxtla: columna "pagado" frente a una
            # mención narrativa que solo identifica el fondo.
            if table_measure != narrative_measure:
                continue
            narrative_tokens = _tokens(narrative.get("contexto_asociacion")
                                       or narrative.get("contexto_inmediato"))
            overlap = len(row_tokens & narrative_tokens) / max(1, len(row_tokens))
            exact_value = table["valor_normalizado"] == narrative["valor_normalizado"]
            if not exact_value and not row_tokens & narrative_tokens:
                continue
            score = overlap + (2.0 if exact_value else 0.0)
            candidates.append((score, narrative["id"], narrative))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        for _, _, narrative in candidates[:config.max_candidates_per_table_value]:
            cases.append(_case_payload(table, narrative))
    return cases


def _evidence_haystack(case: dict, side: str) -> str:
    item = case[side]
    fields = ("text", "row", "column") if side == "table" else ("text",)
    return "\n".join(str(item.get(field) or "") for field in fields)


def validate_decision(decision: dict, case: dict) -> dict:
    required = {"case_id", "relation", "table_measure", "narrative_measure", "confidence",
                "table_evidence", "narrative_evidence"}
    if not isinstance(decision, dict) or set(decision) != required:
        raise ValueError("semantic_invalid_fields")
    if decision["case_id"] != case["case_id"] or decision["relation"] not in RELATIONS:
        raise ValueError("semantic_invalid_identity")
    if decision["table_measure"] not in MEASURES or decision["narrative_measure"] not in MEASURES:
        raise ValueError("semantic_invalid_measure")
    confidence = decision["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("semantic_invalid_confidence")
    for side in ("table", "narrative"):
        evidence = decision[f"{side}_evidence"]
        if not isinstance(evidence, str):
            raise ValueError("semantic_invalid_evidence")
        if decision["relation"] in {"same_concept", "same_measure", "different_measure"}:
            if not evidence.strip() or evidence not in _evidence_haystack(case, side):
                raise ValueError("semantic_untraceable_evidence")
    return decision


def _decision_gate(decision: dict, case: dict, threshold: float) -> bool:
    if decision["relation"] != "same_measure" or decision["confidence"] < threshold:
        return False
    if decision["table_measure"] != decision["narrative_measure"]:
        return False
    deterministic = case["deterministic"]
    table_expected = deterministic["table_measure"]
    narrative_expected = deterministic["narrative_measure"]
    # Un modelo no puede completar por inferencia un tipo de importe ausente en
    # uno de los lados. Para comentar, ambos textos deben expresar el mismo tipo o
    # ambos deben usar un importe genérico sin señales contradictorias.
    if (table_expected == "unspecified") != (narrative_expected == "unspecified"):
        return False
    if table_expected != "unspecified" and table_expected != narrative_expected:
        return False
    for side in ("table", "narrative"):
        expected = deterministic[f"{side}_measure"]
        if expected != "unspecified" and decision[f"{side}_measure"] != expected:
            return False
    return True


def _cache_key(source_sha256: str, case: dict, phase: str, metadata: dict) -> str:
    payload = {
        "source": source_sha256, "case": public_case(case), "phase": phase,
        "provider": metadata, "prompt": PROMPT_VERSION, "schema": SCHEMA_VERSION,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _run_phase(cases: list[dict], phase: str, provider: SemanticProvider, cache: SemanticCache,
               source_sha256: str, config: SemanticConfig, metadata: dict) -> tuple[list[dict], dict]:
    decisions, misses, hits, invalid = {}, [], 0, 0
    for case in cases:
        key = _cache_key(source_sha256, case, phase, metadata)
        cached = cache.get(key)
        if cached is None:
            misses.append((case, key))
        else:
            try:
                decisions[case["case_id"]] = validate_decision(cached, case)
                hits += 1
            except ValueError:
                misses.append((case, key))
    for offset in range(0, len(misses), config.batch_size):
        batch = misses[offset:offset + config.batch_size]
        batch_cases = [item[0] for item in batch]
        raw = provider.analyze([public_case(case) for case in batch_cases], phase)
        if not isinstance(raw, list):
            raise RuntimeError("semantic_invalid_response")
        raw_by_id = {item.get("case_id"): item for item in raw if isinstance(item, dict)}
        for case, key in batch:
            try:
                decision = validate_decision(raw_by_id.get(case["case_id"]), case)
            except (ValueError, TypeError):
                invalid += 1
                continue
            decisions[case["case_id"]] = decision
            cache.put(key, decision)
    ordered = [decisions[case["case_id"]] for case in cases if case["case_id"] in decisions]
    return ordered, {"cache_hits": hits, "cache_misses": len(misses), "invalid_responses": invalid}


def _suggestion(case: dict, decision: dict, reason: str) -> dict:
    identifier = hashlib.sha256((case["case_id"] + "|" + reason).encode("utf-8")).hexdigest()[:20]
    return {
        "id": f"semantic-suggestion-{identifier}", "case_id": case["case_id"],
        "relation": decision["relation"], "confidence": decision["confidence"],
        "table_measure": decision["table_measure"], "narrative_measure": decision["narrative_measure"],
        "reason": reason,
        "table": public_case(case)["table"], "narrative": public_case(case)["narrative"],
        "evidence": {"table": decision["table_evidence"],
                     "narrative": decision["narrative_evidence"]},
        "reviewer": {"status": "pending", "comment": ""},
    }


def run_semantic_review(numbers: list[dict], source_sha256: str, config: SemanticConfig,
                        provider: SemanticProvider | None = None) -> dict:
    started = time.perf_counter()
    provider = provider or OllamaProvider(config)
    metadata = provider.metadata()
    cases = build_semantic_cases(numbers, config)
    base = {
        **metadata, "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION,
        "calibration_version": CALIBRATION_VERSION, "confidence_threshold": config.confidence_threshold,
        "candidate_cases": len(cases), "accepted_relations": [], "suggestions": [],
        "cache": {"hits": 0, "misses": 0}, "invalid_responses": 0,
    }
    if metadata.get("provider") in {"ollama", "institutional"} and not metadata.get("digest"):
        return {**base, "status": "unavailable", "error_code": "semantic_model_digest_unavailable",
                "duration_seconds": round(time.perf_counter() - started, 6)}
    if config.expected_model_digest and metadata.get("digest") != config.expected_model_digest:
        return {**base, "status": "unavailable", "error_code": "semantic_model_digest_mismatch",
                "duration_seconds": round(time.perf_counter() - started, 6)}
    if not cases:
        return {**base, "status": "complete", "duration_seconds": round(time.perf_counter() - started, 6)}
    cache = SemanticCache(config.cache_path)
    try:
        association, stats_a = _run_phase(
            cases, "associate", provider, cache, source_sha256, config, metadata
        )
        by_case = {case["case_id"]: case for case in cases}
        association_by_id = {decision["case_id"]: decision for decision in association}
        gated = [(by_case[decision["case_id"]], decision) for decision in association
                 if _decision_gate(decision, by_case[decision["case_id"]], config.confidence_threshold)]
        table_counts = Counter(case["table"]["number_id"] for case, _ in gated)
        narrative_counts = Counter(case["narrative"]["number_id"] for case, _ in gated)
        unique = [(case, decision) for case, decision in gated
                  if table_counts[case["table"]["number_id"]] == 1
                  and narrative_counts[case["narrative"]["number_id"]] == 1]
        mismatch = [(case, decision) for case, decision in unique
                    if case["table"]["value"] != case["narrative"]["value"]]
        confirmed_equal_ids = {case["case_id"] for case, _ in unique
                               if case["table"]["value"] == case["narrative"]["value"]}
        verification, stats_v = _run_phase(
            [case for case, _ in mismatch], "verify", provider, cache,
            source_sha256, config, metadata,
        ) if mismatch else ([], {"cache_hits": 0, "cache_misses": 0, "invalid_responses": 0})
        verification_by_id = {decision["case_id"]: decision for decision in verification}
        accepted = []
        for case, first in mismatch:
            second = verification_by_id.get(case["case_id"])
            if second and _decision_gate(second, case, config.confidence_threshold):
                accepted.append({
                    "case": case, "association": first, "verification": second,
                    "confidence": min(float(first["confidence"]), float(second["confidence"])),
                })
        accepted_ids = {item["case"]["case_id"] for item in accepted}
        suggestions = []
        for case in cases:
            decision = association_by_id.get(case["case_id"])
            if not decision or case["case_id"] in accepted_ids or case["case_id"] in confirmed_equal_ids:
                continue
            if decision["relation"] == "unrelated" and decision["confidence"] >= config.confidence_threshold:
                continue
            reason = "Relación no confirmada por los dos pasos y controles determinísticos."
            if decision["case_id"] in {item[0]["case_id"] for item in mismatch}:
                reason = "La segunda verificación no confirmó la relación con confianza alta."
            suggestions.append(_suggestion(case, decision, reason))
            if len(suggestions) >= config.max_suggestions:
                break
        base.update(
            status="complete", duration_seconds=round(time.perf_counter() - started, 6),
            association_decisions=len(association), verification_decisions=len(verification),
            accepted_relations=accepted, suggestions=suggestions,
            cache={"hits": stats_a["cache_hits"] + stats_v["cache_hits"],
                   "misses": stats_a["cache_misses"] + stats_v["cache_misses"]},
            invalid_responses=stats_a["invalid_responses"] + stats_v["invalid_responses"],
        )
        return base
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        return {
            **base, "status": "unavailable", "duration_seconds": round(time.perf_counter() - started, 6),
            "error_code": str(exc)[:120],
        }
    finally:
        cache.close()


def serializable_semantic_run(run: dict) -> dict:
    """Quita referencias internas a cifras antes de exportar el reporte."""
    clean = dict(run)
    clean["accepted_relations"] = [{
        "case": public_case(item["case"]), "association": item["association"],
        "verification": item["verification"], "confidence": item["confidence"],
    } for item in run.get("accepted_relations", [])]
    return clean
