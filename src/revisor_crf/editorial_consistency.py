"""Protocolo sintético consistency-v1, con revisión y diario de intentos durable."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .editorial import SYSTEM_PROMPT, load_editorial_catalog, ollama_schema, protected_elements, verify_protected
from .ollama_research import SYSTEM_PROMPT as RESEARCH_PROMPT

PROTOCOL = "consistency-v1"
MODEL = "gemma4:31b"
BANK_PATH = Path(__file__).with_name("editorial_consistency_bank.json")
PHASES = ("selection", "validation-a", "validation-b")
PARAMETERS = {"temperature": 0, "seed": 20260923, "think": False, "num_predict": 2048}
SCHEMA = ollama_schema(["ASF-ED-I-CONTEXT"])
THRESHOLDS = {"precision": .90, "recall": .85, "accuracy": .90, "agreement": .95}
SUFFIX = (
    "\nAplica también los criterios de evaluación incluidos en la solicitud. "
    "suggested_text debe contener el fragmento completo corregido o null; "
    "no debe ser un reemplazo parcial. Conserva todos los elementos protegidos. "
    "Devuelve únicamente JSON conforme al siguiente esquema, sin Markdown:\n"
    + json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True)
)
PROMPTS = {"conservative": SYSTEM_PROMPT + SUFFIX, "research": RESEARCH_PROMPT + SUFFIX}


class ProtocolError(Exception):
    """Error verificable que impide gastar nuevas solicitudes."""


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def timestamp():
    return datetime.now(timezone.utc)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    # En Windows el antivirus puede retener brevemente el destino. Se reintenta
    # exclusivamente el reemplazo local; jamás la solicitud de inferencia.
    for delay in (.01, .03, .1, .2, .5, None):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@contextmanager
def experiment_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "experiment.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        raise ProtocolError("experiment_locked: revise si hay otra ejecución antes de retirar el bloqueo") from None
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def load_bank(path=BANK_PATH):
    bank = read_json(path)
    cases = bank.get("cases", [])
    if (bank.get("schema_version") != "editorial-consistency-bank-1.0"
            or bank.get("synthetic") is not True or len(cases) != 30
            or not bank.get("evaluation_criteria")):
        raise ProtocolError("invalid_consistency_bank")
    ids, texts = set(), set()
    for case in cases:
        text = case.get("fragment", "")
        normal = " ".join(unicodedata.normalize("NFKC", text).lower().split())
        if (not re.fullmatch(r"C\d{2}", case.get("case_id", "")) or not text.strip()
                or case["case_id"] in ids or normal in texts
                or type(case.get("expected_finding")) is not bool
                or not case.get("rationale") or not case.get("focus")
                or not isinstance(case.get("acceptable_spans"), list)):
            raise ProtocolError("invalid_consistency_case")
        spans = case["acceptable_spans"]
        if (bool(spans) != case["expected_finding"]
                or any(not isinstance(span, str) or not span.strip() or span not in text for span in spans)):
            raise ProtocolError("invalid_consistency_evidence")
        ids.add(case["case_id"])
        texts.add(normal)
    for split, size in (("selection", 10), ("validation", 20)):
        group = [case for case in cases if case.get("split") == split]
        if len(group) != size or sum(case["expected_finding"] for case in group) != size // 2:
            raise ProtocolError("unbalanced_consistency_bank")
    return bank


def review_markdown(bank):
    lines = ["# Revisión humana del banco Gemma 4", "",
             "Estado: pendiente de revisión. Estos textos son sintéticos; las etiquetas son propuestas.",
             "Revisar las 30 etiquetas, las evidencias, las justificaciones y los criterios antes de congelar.",
             "La partición reservada no debe usarse para ajustar prompts tras comenzar la selección.",
             "", f"SHA-256 del banco: `{digest(bank)}`", "", "## Criterios comunes", ""]
    lines.extend(f"- {criterion}" for criterion in bank["evaluation_criteria"])
    for split, title in (("selection", "Selección: 10 textos"), ("validation", "Validación reservada: 20 textos")):
        lines.extend(["", f"## {title}", ""])
        for case in bank["cases"]:
            if case["split"] != split:
                continue
            lines.extend([f"### {case['case_id']} — {case['focus']}", "", case["fragment"], "",
                          f"Propuesta: **{'con hallazgo' if case['expected_finding'] else 'sin hallazgo'}**.",
                          f"Justificación: {case['rationale']}",
                          "Evidencia aceptable: " + ("; ".join(f"`{span}`" for span in case["acceptable_spans"]) or "ninguna"), ""])
    return "\n".join(lines) + "\n"


def freeze_bank(directory, bank, reviewer, reviewed_hash, now=None):
    if not reviewer or not reviewer.strip() or reviewed_hash != digest(bank):
        raise ProtocolError("review_required: proporcione revisor y hash exacto del banco revisado")
    directory = Path(directory)
    with experiment_lock(directory):
        if (directory / "review.json").exists() or (directory / "experiment.json").exists():
            raise ProtocolError("review_already_frozen")
        write_json(directory / "frozen_bank.json", bank)
        write_json(directory / "review.json", {
            "protocol": PROTOCOL, "bank_sha256": digest(bank), "reviewer": reviewer.strip(),
            "reviewed_at": (now or timestamp()).isoformat(), "status": "human_reviewed",
        })


def reviewed_bank(directory, current_bank):
    directory = Path(directory)
    if not (directory / "review.json").exists():
        raise ProtocolError("bank_pending_human_review")
    review = read_json(directory / "review.json")
    frozen = load_bank(directory / "frozen_bank.json")
    if (review.get("status") != "human_reviewed" or not review.get("reviewer")
            or review.get("protocol") != PROTOCOL or digest(frozen) != review.get("bank_sha256")
            or digest(current_bank) != digest(frozen)):
        raise ProtocolError("reviewed_bank_changed")
    return frozen


def configuration(bank):
    rule = next(row for row in load_editorial_catalog()["rules"] if row["rule_id"] == "ASF-ED-I-CONTEXT")
    return {"protocol": PROTOCOL, "model": MODEL, "parameters": dict(PARAMETERS), "timeout_seconds": 60,
            "bank_sha256": digest(bank), "rules": [rule], "rules_sha256": digest([rule, bank["evaluation_criteria"]]),
            "prompt_sha256": {name: digest(prompt) for name, prompt in PROMPTS.items()},
            "schema_sha256": digest(SCHEMA), "thresholds": dict(THRESHOLDS),
            "order_seed": 20261029, "phase_limit": 60, "experiment_limit": 180}


def validate_response(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"findings"} or not isinstance(data["findings"], list):
            raise ValueError()
        required = set(SCHEMA["properties"]["findings"]["items"]["required"])
        for row in data["findings"]:
            if not isinstance(row, dict) or set(row) != required:
                raise ValueError()
            if any(not isinstance(row[key], str) for key in
                   ("rule_id", "category", "severity", "problem_span", "message")):
                raise ValueError()
            if (row["rule_id"] != "ASF-ED-I-CONTEXT" or not row["problem_span"].strip()
                    or row["severity"] not in {"error", "warning", "suggestion", "info"}
                    or row["suggested_text"] is not None and not isinstance(row["suggested_text"], str)):
                raise ValueError()
            confidence = row["confidence"]
            if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ValueError("invalid_json_or_schema") from None
    return data["findings"]


def grade(case, raw, transport_status="received", done_reason="stop"):
    expected = case["expected_finding"]
    result = {"case_id": case["case_id"], "expected": expected, "tp": 0, "fp": 0,
              "fn": int(expected), "tn": 0, "invalid_responses": 0, "unsafe_suggestions": 0,
              "issues": [], "findings": [], "signature": None}
    try:
        if transport_status != "received" or done_reason not in (None, "stop"):
            raise ValueError("transport_or_truncated_response")
        findings = validate_response(raw)
    except ValueError as exc:
        result["invalid_responses"] = 1
        result["issues"].append(str(exc))
        return result
    result["findings"] = findings
    accepted, unsupported = False, False
    for row in findings:
        literal = row["problem_span"] in case["fragment"]
        if not literal:
            result["invalid_responses"] = 1
            result["issues"].append("nonliteral_evidence")
        relevant = expected and row["problem_span"] in case["acceptable_spans"]
        accepted = accepted or relevant
        unsupported = unsupported or not relevant
        if row["suggested_text"] is not None and not verify_protected(case["fragment"], row["suggested_text"])["safe"]:
            result["unsafe_suggestions"] += 1
            result["issues"].append("protected_elements_changed")
    result.update(tp=int(accepted), fn=int(expected and not accepted), fp=int(unsupported),
                  tn=int(not expected and not findings))
    # Se mide la decisión y la regla; no la redacción de las explicaciones.
    result["signature"] = sorted({row["rule_id"] for row in findings})
    return result


def metrics(grades):
    totals = {key: sum(row[key] for row in grades) for key in
              ("tp", "fp", "fn", "tn", "invalid_responses", "unsafe_suggestions")}
    denominator = totals["tp"] + totals["fp"]
    totals.update(cases=len(grades), precision=totals["tp"] / denominator if denominator else None,
                  recall=totals["tp"] / (totals["tp"] + totals["fn"]) if totals["tp"] + totals["fn"] else 0,
                  accuracy=(totals["tp"] + totals["tn"]) / len(grades) if grades else 0)
    return totals


def quality_passes(values):
    return (all(values[key] is not None and values[key] >= THRESHOLDS[key]
                for key in ("precision", "recall", "accuracy"))
            and values["invalid_responses"] == 0 and values["unsafe_suggestions"] == 0)


def schedule(bank, phase, prompt=None):
    group = [row for row in bank["cases"] if row["split"] == ("selection" if phase == "selection" else "validation")]
    profiles = list(PROMPTS) if phase == "selection" else [prompt]
    tasks = []
    for profile_index, profile in enumerate(profiles):
        for repetition in range(1, 4):
            seed = 20261029 + PHASES.index(phase) * 1000 + profile_index * 100 + repetition
            ordered = list(group)
            random.Random(seed).shuffle(ordered)
            for case in ordered:
                tasks.append({"task_id": f"{phase}:{profile}:{repetition}:{case['case_id']}",
                              "phase": phase, "prompt": profile, "repetition": repetition,
                              "order_seed": seed, "case_id": case["case_id"]})
    return tasks


def stability(records, cases, required_repetitions):
    groups = {case["case_id"]: [] for case in cases}
    for row in records:
        if row["case_id"] in groups:
            groups[row["case_id"]].append(row)
    if any(len(rows) != required_repetitions for rows in groups.values()):
        return None
    values = {name: 0 for name in ("decision_rule", "severity", "evidence", "correction")}
    for rows in groups.values():
        signatures = {key: [] for key in values}
        usable = all(row.get("grade") and row["grade"]["invalid_responses"] == 0 for row in rows)
        if not usable:
            continue
        for row in rows:
            findings = row["grade"]["findings"]
            signatures["decision_rule"].append(row["grade"]["signature"])
            signatures["severity"].append(sorted((x["rule_id"], x["severity"]) for x in findings))
            signatures["evidence"].append(sorted((x["rule_id"], x["problem_span"]) for x in findings))
            signatures["correction"].append(sorted((x["rule_id"], " ".join(unicodedata.normalize(
                "NFKC", x["suggested_text"]).split()) if x["suggested_text"] is not None else "<null>") for x in findings))
        for key, comparisons in signatures.items():
            values[key] += int(all(value == comparisons[0] for value in comparisons))
    return {key: count / len(cases) for key, count in values.items()}


def phase_result(state, bank, phase):
    attempts = [row for row in state["attempts"] if row["phase"] == phase]
    expected = schedule(bank, phase, state.get("selected_prompt"))
    complete = len(attempts) == len(expected) and all(row["status"] != "started" for row in attempts)
    result = {"complete": complete, "attempts": len(attempts), "profiles": {}}
    profiles = list(PROMPTS) if phase == "selection" else [state.get("selected_prompt")]
    for profile in profiles:
        records = [row for row in attempts if row["prompt"] == profile]
        cases = [case for case in bank["cases"] if case["split"] == ("selection" if phase == "selection" else "validation")]
        runs = []
        for repetition in range(1, 4):
            rows = [row for row in records if row["repetition"] == repetition]
            scored = [row["grade"] for row in rows if row.get("grade")]
            values = metrics(scored)
            values["complete"] = len(scored) == len(cases)
            runs.append(values)
        combined = metrics([row["grade"] for row in records if row.get("grade")])
        result["profiles"][profile] = {
            "runs": runs, "metrics": combined, "stability": stability(records, cases, 3),
            "quality_passed": complete and all(run["complete"] and quality_passes(run) for run in runs),
            "reported_tokens": sum(row.get("prompt_eval_count", 0) + row.get("eval_count", 0) for row in records),
            "cases_with_issues": sorted({row["case_id"] for row in records if row.get("grade")
                                        and any(row["grade"][key] for key in
                                                ("fp", "fn", "invalid_responses", "unsafe_suggestions"))}),
        }
    return result


def select_prompt(result):
    eligible = [(name, row) for name, row in result["profiles"].items() if row["quality_passed"]]
    if not eligible:
        return None
    eligible.sort(key=lambda item: (-item[1]["metrics"]["recall"], -item[1]["metrics"]["precision"],
                                    item[1]["reported_tokens"], item[0]))
    return eligible[0][0]


def summarize(state, bank):
    results = {phase: phase_result(state, bank, phase) for phase in state["phases"]}
    report = {"protocol": PROTOCOL, "model": MODEL, "selected_model": None,
              "selected_prompt": state.get("selected_prompt"), "conclusion": "no validado",
              "comparability": state.get("comparability", "comparable"), "phases": results,
              "final_stability": None, "usage": {
                  "attempted_requests": len(state["attempts"]),
                  "reported_input_tokens": sum(row.get("prompt_eval_count", 0) for row in state["attempts"]),
                  "reported_cached_input_tokens": sum(row.get("prompt_eval_cached_count", 0) for row in state["attempts"]),
                  "reported_output_tokens": sum(row.get("eval_count", 0) for row in state["attempts"]),
                  "responses_with_token_counts": sum("eval_count" in row and "prompt_eval_count" in row for row in state["attempts"]),
                  "duration_seconds": sum(row.get("duration_seconds", 0) for row in state["attempts"]),
              }, "stop_reason": state.get("stop_reason"),
              "billing": "El diario no consulta saldo; las solicitudes fallidas pueden consumir tokens no reportados."}
    if report["comparability"] != "comparable":
        return report
    selection = results.get("selection")
    if selection and selection["complete"] and not state.get("selected_prompt"):
        if all(row["stability"] and row["stability"]["decision_rule"] >= .95
               for row in selection["profiles"].values()):
            report["conclusion"] = "estable pero insuficiente"
    if all(results.get(phase, {}).get("complete") for phase in ("validation-a", "validation-b")):
        records = [row for row in state["attempts"] if row["phase"] != "selection"]
        final = stability(records, [case for case in bank["cases"] if case["split"] == "validation"], 6)
        report["final_stability"] = final
        stable = final is not None and final["decision_rule"] >= .95
        useful = all(results[phase]["profiles"][state["selected_prompt"]]["quality_passed"]
                     for phase in ("validation-a", "validation-b"))
        report["conclusion"] = ("candidato consistente para piloto sintético" if stable and useful else
                                "útil pero inestable" if useful else
                                "estable pero insuficiente" if stable else "no validado")
    return report


def report_markdown(report):
    usage = report["usage"]
    lines = ["# Evaluación de consistencia de Gemma 4 31B", "",
             f"Conclusión: **{report['conclusion']}**.",
             f"Comparabilidad: {report['comparability']}. Prompt elegido: {report['selected_prompt'] or 'ninguno'}.",
             "", f"Intentos: {usage['attempted_requests']}/180; tokens de entrada reportados: {usage['reported_input_tokens']}; "
             f"salida: {usage['reported_output_tokens']}; entrada en caché: {usage['reported_cached_input_tokens']}.",
             "Los tokens en caché son parte de la entrada, no se suman otra vez.",
             f"Tiempo acumulado de solicitudes: {usage['duration_seconds']:.2f} s. No acredita saldo ni costo exacto.", "",
             "| Fase / prompt | Completa | Precisión | Exhaustividad | Exactitud | Acuerdo | Calidad por repetición |",
             "|---|---|---|---|---|---|---|"]
    def percent(value):
        return "N/C" if value is None else f"{value:.1%}"
    for phase, result in report["phases"].items():
        for name, row in result["profiles"].items():
            values = row["metrics"]
            agreement = row["stability"]["decision_rule"] if row["stability"] else None
            lines.append(f"| {phase} / {name} | {result['complete']} | {percent(values['precision'])} | "
                         f"{percent(values['recall'])} | {percent(values['accuracy'])} | {percent(agreement)} | {row['quality_passed']} |")
    for phase, result in report["phases"].items():
        lines.extend(["", f"## {phase}", ""])
        for name, row in result["profiles"].items():
            lines.append(f"Prompt **{name}**. Casos con omisiones, falsas alarmas o errores: "
                         + (", ".join(row["cases_with_issues"]) or "ninguno") + ".")
            for index, run in enumerate(row["runs"], 1):
                lines.append(f"- Repetición {index}: precisión {percent(run['precision'])}, "
                             f"exhaustividad {percent(run['recall'])}, exactitud {percent(run['accuracy'])}; "
                             f"FP {run['fp']}, FN {run['fn']}, inválidas {run['invalid_responses']}, "
                             f"inseguras {run['unsafe_suggestions']}. Completa: {run['complete']}.")
    if report["final_stability"]:
        lines.extend(["", "## Estabilidad entre las seis repeticiones finales", ""])
        lines.extend(f"- {name}: {percent(value)}" for name, value in report["final_stability"].items())
    if report.get("stop_reason"):
        lines.extend(["", f"Interrupción: `{report['stop_reason']}`."])
    lines.extend(["", "Un piloto sintético no aprueba el uso institucional. Las explicaciones y correcciones requieren revisión humana.",
                  "Los promedios de calidad no sustituyen el cumplimiento en cada repetición; consulte el JSON."])
    return "\n".join(lines) + "\n"


class ConsistencyExperiment:
    def __init__(self, directory, bank, commit, implementation_sha256):
        self.directory = Path(directory)
        self.bank = reviewed_bank(directory, bank)
        self.config = configuration(self.bank)
        self.config.update(source_commit=commit, implementation_sha256=implementation_sha256)
        path = self.directory / "experiment.json"
        self.state = read_json(path) if path.exists() else {
            "protocol": PROTOCOL, "config": self.config, "config_sha256": digest(self.config),
            "model_metadata": None, "comparability": "comparable", "selected_prompt": None,
            "phases": {}, "attempts": [],
        }
        attempts = self.state.get("attempts", [])
        if (len(attempts) > 180 or len({row["task_id"] for row in attempts}) != len(attempts)
                or any(sum(row["phase"] == phase for row in attempts) > 60 for phase in PHASES)):
            raise ProtocolError("invalid_attempt_journal")
        if (self.state.get("config_sha256") != digest(self.config)
                or digest(self.state["config"]) != self.state.get("config_sha256")):
            self.state.update(comparability="not_comparable", stop_reason="configuration_changed")
            self.save()
            raise ProtocolError("configuration_changed")
        if self.state["comparability"] != "comparable":
            raise ProtocolError("experiment_not_comparable")

    def save(self):
        write_json(self.directory / "experiment.json", self.state)
        report = summarize(self.state, self.bank)
        write_json(self.directory / "report.json", report)
        (self.directory / "report.md").write_text(report_markdown(report), encoding="utf-8")

    def check_phase(self, phase, now):
        if phase not in PHASES:
            raise ProtocolError("invalid_phase")
        if phase != "selection":
            if not self.state.get("selected_prompt"):
                raise ProtocolError("no_prompt_passed_selection")
            previous = "selection" if phase == "validation-a" else "validation-a"
            if self.state["phases"].get(previous, {}).get("status") != "completed":
                raise ProtocolError("previous_phase_not_completed")
        if phase == "validation-b":
            completed = datetime.fromisoformat(self.state["phases"]["validation-a"]["completed_at"])
            elapsed = now - completed
            if elapsed < timedelta(hours=24):
                raise ProtocolError("validation_b_too_early")
            if elapsed > timedelta(hours=72):
                raise ProtocolError("validation_b_window_expired")

    def run(self, phase, metadata, send, now=None):
        """send(task, request, prompt, attempt) actualiza el intento con el resultado de transporte."""
        supplied_now = now
        now = now or timestamp()
        self.check_phase(phase, now)
        if not metadata.get("digest") or metadata.get("model") != MODEL:
            raise ProtocolError("model_metadata_missing")
        if self.state["model_metadata"] is None:
            self.state["model_metadata"] = metadata
        elif digest(self.state["model_metadata"]) != digest(metadata):
            self.state.update(comparability="not_comparable", stop_reason="model_metadata_changed")
            self.save()
            raise ProtocolError("model_metadata_changed")
        if self.state["phases"].get(phase, {}).get("status") == "completed":
            return summarize(self.state, self.bank)
        info = self.state["phases"].setdefault(phase, {"started_at": now.isoformat()})
        info["status"] = "running"
        self.state.pop("stop_reason", None)
        cases = {case["case_id"]: case for case in self.bank["cases"]}
        attempted = {row["task_id"] for row in self.state["attempts"]}
        # Un intento sin resultado se conserva como incierto; jamás se vuelve a enviar.
        for row in self.state["attempts"]:
            if row["phase"] == phase and row["status"] == "started":
                row["status"] = "uncertain"
            if row["phase"] == phase and not row.get("grade"):
                row["grade"] = grade(cases[row["case_id"]], row.get("response_text"),
                                     row["status"], row.get("done_reason"))
        self.save()
        for task in schedule(self.bank, phase, self.state.get("selected_prompt")):
            if task["task_id"] in attempted:
                continue
            if len(self.state["attempts"]) >= 180 or sum(row["phase"] == phase for row in self.state["attempts"]) >= 60:
                raise ProtocolError("request_budget_exhausted")
            case = cases[task["case_id"]]
            request = {"fragment": case["fragment"], "location": {"case_id": case["case_id"]},
                       "rules": self.config["rules"], "criteria": self.bank["evaluation_criteria"],
                       "protected_elements": protected_elements(case["fragment"])}
            attempt = {**task, "session": phase, "status": "started", "started_at": timestamp().isoformat(),
                       "parameters": self.config["parameters"], "prompt_sha256": self.config["prompt_sha256"][task["prompt"]],
                       "request": request}
            self.state["attempts"].append(attempt)
            self.save()  # Persistir antes de enviar protege contra duplicados tras una caída.
            try:
                raw = send(task, request, PROMPTS[task["prompt"]], attempt)
                if attempt.get("returned_model") != MODEL:
                    self.state["comparability"] = "not_comparable"
                    raise ProtocolError("returned_model_changed")
                attempt["response_text"] = raw
                attempt["status"] = "received"
                attempt["grade"] = grade(case, raw, done_reason=attempt.get("done_reason"))
            except Exception as exc:
                if attempt["status"] == "started":
                    attempt["status"] = "uncertain"
                attempt["grade"] = grade(case, None, attempt["status"])
                info["status"] = "stopped"
                # El mensaje del transporte puede contener secretos; sólo se aceptan códigos conocidos.
                reason = str(exc)
                if not re.fullmatch(r"(?:cloud_http_\d{3}|cloud_transport_error|cloud_response_error|returned_model_changed)", reason):
                    reason = "request_interrupted"
                self.state["stop_reason"] = reason
                self.save()
                raise ProtocolError(reason) from None
            self.save()
        info.update(status="completed", completed_at=(supplied_now or timestamp()).isoformat())
        if phase == "selection":
            self.state["selected_prompt"] = select_prompt(phase_result(self.state, self.bank, phase))
        self.save()
        return summarize(self.state, self.bank)
