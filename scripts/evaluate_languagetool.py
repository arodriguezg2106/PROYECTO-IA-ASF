"""Evalúa LanguageTool y genera una lista blanca sin almacenar texto documental."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from revisor_crf.editorial import _ignore_spelling_match, load_editorial_catalog, verify_protected
from revisor_crf.language_tool import LanguageToolProvider
from revisor_crf.language_tool_profile import load_language_tool_profile


THRESHOLDS = {
    "minimum_precision": 0.95,
    "minimum_recall": 0.75,
    "maximum_false_positive_rate": 0.05,
    "minimum_agreement": 1.0,
    "maximum_invalid_responses": 0,
    "maximum_unsafe_suggestions": 0,
    "minimum_positive_hits_per_rule": 3,
}
DEFAULT_ACCEPTED_TERMS = ("ASF", "CRF", "UAA", "SHCP")
DEFAULT_EXCLUDED_CATEGORIES = ("CASING",)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Banco inválido: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError(f"Banco sin casos válidos: {path}")
    return data


def _adapt_bank(path: Path) -> tuple[list[dict], dict]:
    data = _read(path)
    schema = data.get("schema_version")
    cases = []
    if schema == "languagetool-evaluation-bank-1.0":
        cases = [{"case_id": item["case_id"], "fragment": item["fragment"],
                  "expected_finding": bool(item["expected_finding"]),
                  "category": item.get("category"), "synthetic": True} for item in data["cases"]]
    elif schema in {"editorial-paired-evaluation-bank-1.0", "editorial-synthetic-paired-bank-1.0"}:
        synthetic = bool(data.get("synthetic"))
        cases = [{"case_id": item["case_id"], "fragment": item["fragment"],
                  "expected_finding": bool(item["expected_finding"]),
                  "category": item.get("category"), "synthetic": synthetic}
                 for item in data["cases"] if item.get("category") == "Ortografía o gramática"]
    elif schema == "editorial-validation-bank-1.0":
        catalog = {item["rule_id"]: item for item in load_editorial_catalog()["rules"]}
        for item in data["cases"]:
            expected = item.get("expected_findings") or []
            categories = {catalog.get(row.get("rule_id"), {}).get("category") for row in expected}
            if expected and categories != {"grammar"}:
                continue
            cases.append({"case_id": f"editorial-{item['case_id']}", "fragment": item["text"],
                          "expected_finding": bool(expected), "category": "editorial_regression",
                          "synthetic": True})
    else:
        raise ValueError(f"Esquema de banco no compatible: {schema}")
    if not cases:
        raise ValueError(f"El banco no contiene casos compatibles con LanguageTool: {path}")
    return cases, {"path": str(path), "sha256": _hash(path), "schema_version": schema,
                   "cases": len(cases), "synthetic": all(item["synthetic"] for item in cases)}


def _safe_matches(text: str, matches: list[dict], accepted_terms: tuple[str, ...],
                  excluded_categories: tuple[str, ...]) -> tuple[list[dict], int]:
    safe = []
    unsafe = 0
    excluded = {item.upper() for item in excluded_categories}
    for match in matches:
        rule = match.get("rule") or {}
        category = str((rule.get("category") or {}).get("id") or "").upper()
        if category in excluded or _ignore_spelling_match(match, text, accepted_terms, ()):
            continue
        replacements = match.get("replacements") or []
        if replacements and isinstance(replacements[0], dict):
            start = max(0, int(match.get("offset") or 0))
            end = start + max(0, int(match.get("length") or 0))
            proposed = text[:start] + str(replacements[0].get("value") or "") + text[end:]
            if not verify_protected(text, proposed)["safe"]:
                unsafe += 1
                continue
        safe.append(match)
    return safe, unsafe


def _signature(matches: list[dict]) -> tuple[tuple[str, int, int], ...]:
    return tuple(sorted((str((item.get("rule") or {}).get("id") or "UNKNOWN"),
                         int(item.get("offset") or 0), int(item.get("length") or 0))
                        for item in matches))


def evaluate(cases: list[dict], provider: LanguageToolProvider, *, repetitions: int,
             rule_ids: tuple[str, ...], accepted_terms: tuple[str, ...],
             excluded_categories: tuple[str, ...]) -> dict:
    runs = []
    invalid = unsafe = 0
    for repetition in range(repetitions):
        current = {}
        for case in cases:
            try:
                matches = provider.check(case["fragment"], rule_ids=rule_ids)
                matches, rejected = _safe_matches(case["fragment"], matches, accepted_terms,
                                                  excluded_categories)
                unsafe += rejected
                current[case["case_id"]] = _signature(matches)
            except RuntimeError:
                invalid += 1
                current[case["case_id"]] = (("__INVALID__", 0, 0),)
        runs.append(current)
    first = runs[0]
    tp = fp = fn = tn = 0
    per_rule = defaultdict(lambda: {"positive_hits": set(), "negative_hits": set()})
    results = []
    for case in cases:
        signature = first[case["case_id"]]
        predicted = bool(signature) and signature[0][0] != "__INVALID__"
        expected = case["expected_finding"]
        tp += int(expected and predicted); fn += int(expected and not predicted)
        fp += int(not expected and predicted); tn += int(not expected and not predicted)
        rules = sorted({row[0] for row in signature if row[0] != "__INVALID__"})
        for rule_id in rules:
            per_rule[rule_id]["positive_hits" if expected else "negative_hits"].add(case["case_id"])
        results.append({"case_id": case["case_id"], "expected_finding": expected,
                        "predicted_finding": predicted, "rule_ids": rules,
                        "synthetic": case["synthetic"]})
    comparable = len(cases) * max(0, repetitions - 1)
    equal = sum(runs[index][case["case_id"]] == first[case["case_id"]]
                for index in range(1, repetitions) for case in cases)
    precision = None if tp + fp == 0 else tp / (tp + fp)
    recall = None if tp + fn == 0 else tp / (tp + fn)
    fp_rate = None if fp + tn == 0 else fp / (fp + tn)
    agreement = 1.0 if comparable == 0 else equal / comparable
    rules = [{"rule_id": rule_id, "positive_hits": len(values["positive_hits"]),
              "negative_hits": len(values["negative_hits"]),
              "eligible": len(values["positive_hits"]) >= THRESHOLDS["minimum_positive_hits_per_rule"]
                          and not values["negative_hits"] and agreement == 1.0}
             for rule_id, values in sorted(per_rule.items())]
    metrics = {"cases": len(cases), "true_positives": tp, "false_positives": fp,
               "false_negatives": fn, "true_negatives": tn,
               "precision": None if precision is None else round(precision, 4),
               "recall": None if recall is None else round(recall, 4),
               "false_positive_rate": None if fp_rate is None else round(fp_rate, 4),
               "agreement": round(agreement, 4), "invalid_responses": invalid,
               "unsafe_suggestions": unsafe, "repetitions": repetitions}
    passed = (precision is not None and precision >= THRESHOLDS["minimum_precision"]
              and recall is not None and recall >= THRESHOLDS["minimum_recall"]
              and fp_rate is not None and fp_rate <= THRESHOLDS["maximum_false_positive_rate"]
              and agreement >= THRESHOLDS["minimum_agreement"] and invalid == 0 and unsafe == 0)
    return {"metrics": metrics, "passed": passed, "rules": rules, "cases": results}


def _profile(*, status: str, rules: list[str], sources: list[dict], metrics: dict,
             accepted_terms: tuple[str, ...], excluded_categories: tuple[str, ...]) -> dict:
    material = json.dumps({"rules": rules, "sources": sources, "metrics": metrics}, sort_keys=True)
    version = "lt-es-6.6-" + hashlib.sha256(material.encode()).hexdigest()[:12]
    return {"schema_version": "languagetool-profile-1.0", "profile_version": version,
            "status": status, "provider": {"name": "LanguageTool", "version": "6.6", "language": "es"},
            "approved_rule_ids": rules, "accepted_terms": list(accepted_terms),
            "excluded_categories": list(excluded_categories),
            "source": {"banks": sources}, "metrics": metrics,
            "privacy": {"contains_raw_text": False, "safe_for_version_control": True}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("discovery", "gate"), required=True)
    parser.add_argument("--bank", action="append", required=True)
    parser.add_argument("--profile", help="Perfil candidato requerido en modo gate")
    parser.add_argument("--profile-output", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8081/v2")
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        if args.repetitions != 2:
            raise ValueError("La compuerta de LanguageTool requiere exactamente dos repeticiones.")
        banks = [_adapt_bank(Path(value)) for value in args.bank]
        cases = [case for bank_cases, _ in banks for case in bank_cases]
        if len({item["case_id"] for item in cases}) != len(cases):
            raise ValueError("Los bancos contienen identificadores de caso duplicados.")
        sources = [metadata for _, metadata in banks]
        rules: tuple[str, ...] = ()
        accepted = DEFAULT_ACCEPTED_TERMS
        excluded = DEFAULT_EXCLUDED_CATEGORIES
        if args.mode == "gate":
            if not args.profile:
                raise ValueError("El modo gate requiere --profile.")
            candidate = load_language_tool_profile(args.profile, require_approved=False)
            if candidate.status != "candidate" or not candidate.approved_rule_ids:
                raise ValueError("La compuerta requiere un perfil candidato con reglas.")
            expected_sources = candidate.source.get("banks")
            if not isinstance(expected_sources, list) or [
                (item.get("sha256"), item.get("schema_version"), item.get("cases"))
                for item in expected_sources
            ] != [(item["sha256"], item["schema_version"], item["cases"]) for item in sources]:
                raise ValueError("El perfil candidato no corresponde a los bancos evaluados.")
            rules = candidate.approved_rule_ids
            accepted = candidate.accepted_terms
            excluded = candidate.excluded_categories
        result = evaluate(cases, LanguageToolProvider(args.url, "es", 10), repetitions=2,
                          rule_ids=rules, accepted_terms=accepted, excluded_categories=excluded)
        if args.mode == "discovery":
            selected = [item["rule_id"] for item in result["rules"] if item["eligible"]]
            status = "candidate" if selected else "insufficient_evidence"
        else:
            selected = list(rules) if result["passed"] else []
            real_positive = sum(not item["synthetic"] and item["expected_finding"] for item in cases)
            status = ("approved_for_pilot" if result["passed"] and real_positive >= 10
                      else "approved_for_demo" if result["passed"] else "rejected")
        profile = _profile(status=status, rules=selected, sources=sources,
                           metrics=result["metrics"], accepted_terms=accepted,
                           excluded_categories=excluded)
        report = {"schema_version": "languagetool-evaluation-1.0",
                  "generated_at": datetime.now(timezone.utc).isoformat(), "mode": args.mode,
                  "thresholds": THRESHOLDS, "sources": sources, **result,
                  "profile_version": profile["profile_version"], "profile_status": status,
                  "privacy": {"contains_raw_text": False, "safe_for_version_control": True}}
        for path, payload in ((Path(args.output), report), (Path(args.profile_output), profile)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": status, **result["metrics"]}, ensure_ascii=False))
        return 0 if status in {"candidate", "approved_for_demo", "approved_for_pilot"} else 2
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
