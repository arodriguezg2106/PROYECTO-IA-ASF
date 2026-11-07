"""Piloto autorizado sobre un único par real, aislado de consistency-v1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from build_revision_evidence_handoff import extract_evidence
from evaluate_editorial_consistency import model_metadata
from evaluate_ollama_cloud import CloudSession
from revisor_crf import editorial_consistency as p
from revisor_crf.editorial import protected_elements, verify_protected

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/CRF-sinteticas/CRF FORTAMUN SON TMHPR_Rv_DG.docx"
EVIDENCE_ID = "REV-ca9b40e9770c500e"
DIRECTORY = ROOT / "results/ollama_cloud/real_case_sonora"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settings():
    bank = p.load_bank()
    return {"model": p.MODEL, "parameters": p.PARAMETERS, "prompt": p.PROMPTS["conservative"],
            "rules": p.configuration(bank)["rules"], "criteria": bank["evaluation_criteria"],
            "implementation_sha256": file_hash(Path(__file__))}


def prepare(directory=DIRECTORY, source=SOURCE):
    directory, source = Path(directory), Path(source)
    config = settings()
    manifest_path = directory / "case.json"
    if manifest_path.exists():
        manifest = p.read_json(manifest_path)
        if manifest["source_sha256"] != file_hash(source) or manifest["configuration_sha256"] != p.digest(config):
            raise p.ProtocolError("source_or_configuration_changed")
        return manifest
    record = next((row for row in extract_evidence(source) if row["id"] == EVIDENCE_ID), None)
    if not record or not record["before"] or not record["after"] or record["before"] == record["after"]:
        raise p.ProtocolError("reference_pair_not_found")
    manifest = {"schema_version": "authorized-real-case-1.0", "source": str(source),
                "source_sha256": file_hash(source), "evidence_id": EVIDENCE_ID,
                "xml_paths": record["xml_paths"], "configuration_sha256": p.digest(config),
                "authorization": "Usuario autorizó usar cualquier caso del corpus local con cifras alteradas.",
                "reference_status": "Cambio humano registrado; no equivale a una adjudicación exhaustiva del párrafo.",
                "variants": [{"case_id": "R01", "variant": "before", "text": record["before"]},
                             {"case_id": "R02", "variant": "after", "text": record["after"]}],
                "max_requests": 6, "repetitions": 3}
    p.write_json(manifest_path, manifest)
    (directory / "case_preview.md").write_text(
        "# Caso real autorizado: Sonora\n\nFuente: " + source.name + "\n\n"
        "Referencia: cambio de `agua nacionales` a `aguas nacionales`.\n\n"
        "Los importes se conservan. Sólo se enviarán estos dos párrafos, sin nombre del archivo, "
        "comentarios, identidad del revisor, etiquetas ni comparación humana.\n\n"
        "## Antes\n\n" + record["before"] + "\n\n## Después\n\n" + record["after"] + "\n",
        encoding="utf-8")
    return manifest


def tasks(manifest):
    return [{"task_id": f"{variant['case_id']}:{repetition}", "repetition": repetition, **variant}
            for repetition in range(1, 4) for variant in manifest["variants"]]


def assessment(attempt, text):
    result = {"findings": [], "invalid_response": False, "nonliteral_spans": [], "protection_diagnostics": []}
    try:
        if attempt["status"] != "received" or attempt.get("done_reason") not in (None, "stop"):
            raise ValueError()
        result["findings"] = p.validate_response(attempt.get("response_text"))
    except ValueError:
        result["invalid_response"] = True
        return result
    for row in result["findings"]:
        if row["problem_span"] not in text:
            result["nonliteral_spans"].append(row["problem_span"])
        if row["suggested_text"] is not None:
            result["protection_diagnostics"].append(verify_protected(text, row["suggested_text"]))
    return result


def save(directory, state):
    p.write_json(directory / "result.json", state)
    rows = state["attempts"]
    usage = {"attempted_requests": len(rows),
             "reported_input_tokens": sum(row.get("prompt_eval_count", 0) for row in rows),
             "reported_cached_input_tokens": sum(row.get("prompt_eval_cached_count", 0) for row in rows),
             "reported_output_tokens": sum(row.get("eval_count", 0) for row in rows)}
    report = {"status": state["status"], "usage": usage, "reference": "case.json",
              "stop_reason": state.get("stop_reason"), "attempts": rows,
              "note": "Piloto descriptivo de un par real; no modifica ni aprueba consistency-v1. "
                      "Los diagnósticos mecánicos de protección requieren revisión humana."}
    p.write_json(directory / "report.json", report)
    lines = ["# Piloto real: párrafo de Sonora", "", f"Estado: {state['status']}; intentos: {len(rows)}/6.",
             "", "La corrección humana de referencia no se envió al modelo. No se calculan métricas generales con un solo par.", "",
             f"Tokens de entrada: {usage['reported_input_tokens']}; salida: {usage['reported_output_tokens']}; "
             f"entrada en caché (incluida en entrada): {usage['reported_cached_input_tokens']}.", ""]
    for row in rows:
        result = row.get("assessment", {})
        lines.extend([f"## {row['variant']} — repetición {row['repetition']}", "",
                      f"Transporte: {row['status']}. Respuesta inválida: {result.get('invalid_response', 'pendiente')}.", ""])
        for finding in result.get("findings", []):
            lines.extend([f"- Evidencia: {finding['problem_span']}", f"- Explicación: {finding['message']}",
                          f"- Propuesta: {finding['suggested_text'] or 'sin propuesta'}", ""])
        if "assessment" in row and not result["findings"]:
            lines.append("Sin hallazgos aceptados por el parser.\n")
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def execute(directory, manifest, session, metadata):
    directory = Path(directory)
    path = directory / "result.json"
    state = p.read_json(path) if path.exists() else {
        "schema_version": "authorized-real-case-results-1.0", "status": "running", "attempts": [],
        "manifest_sha256": p.digest(manifest), "model_metadata": metadata,
    }
    if state["manifest_sha256"] != p.digest(manifest) or state["model_metadata"] != metadata:
        raise p.ProtocolError("manifest_or_model_changed")
    attempts = state["attempts"]
    if len(attempts) > 6 or len({row["task_id"] for row in attempts}) != len(attempts):
        raise p.ProtocolError("invalid_attempt_journal")
    variants = {variant["case_id"]: variant for variant in manifest["variants"]}
    for row in attempts:
        if row["status"] == "started":
            row["status"] = "uncertain"
        if "assessment" not in row:
            row["assessment"] = assessment(row, variants[row["case_id"]]["text"])
    state["status"] = "running"
    state.pop("stop_reason", None)
    save(directory, state)
    done = {row["task_id"] for row in attempts}
    config = settings()
    for task in tasks(manifest):
        if task["task_id"] in done:
            continue
        if len(attempts) >= 6:
            raise p.ProtocolError("request_budget_exhausted")
        attempt = {key: task[key] for key in ("task_id", "repetition", "variant", "case_id")}
        attempt.update(status="started", parameters=p.PARAMETERS)
        attempts.append(attempt)
        save(directory, state)

        def persist(call):
            attempt.update(call)
            save(directory, state)

        session.on_result = persist
        request = {"fragment": task["text"], "location": {"case_id": task["case_id"]},
                   "rules": config["rules"], "criteria": config["criteria"],
                   "protected_elements": protected_elements(task["text"])}
        print(f"Caso real {task['case_id']}, repetición {task['repetition']}/3", flush=True)
        try:
            raw = session.chat(p.MODEL, request)
            if attempt.get("returned_model") != p.MODEL:
                raise p.ProtocolError("returned_model_changed")
            attempt.update(response_text=raw, status="received")
            attempt["assessment"] = assessment(attempt, task["text"])
        except Exception:
            if attempt["status"] == "started":
                attempt["status"] = "uncertain"
            attempt["assessment"] = assessment(attempt, task["text"])
            state.update(status="stopped", stop_reason="request_interrupted_no_retry")
            save(directory, state)
            raise p.ProtocolError("request_interrupted_no_retry") from None
        save(directory, state)
    state["status"] = "completed" if all(row["status"] == "received" for row in attempts) else "completed_with_errors"
    return save(directory, state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Extrae el par localmente, sin red ni credencial")
    args = parser.parse_args(argv)
    try:
        with p.experiment_lock(DIRECTORY):
            manifest = prepare()
            if args.prepare:
                print(f"Caso preparado sin API: {DIRECTORY / 'case_preview.md'}")
                return 0
            existing = DIRECTORY / "result.json"
            if existing.exists() and len(p.read_json(existing)["attempts"]) == 6:
                print("Los seis intentos ya figuran en el diario; no se repiten solicitudes.")
                return 0
            token = os.getenv("OLLAMA_API_KEY", "").strip()
            if not token:
                raise p.ProtocolError("missing_OLLAMA_API_KEY")
            session = CloudSession(token, 6, 60, 2048, prompt=p.PROMPTS["conservative"],
                                   think=False, record_response=True)
            report = execute(DIRECTORY, manifest, session, model_metadata())
        print(f"Piloto terminado: {report['status']}; reporte: {DIRECTORY / 'report.md'}")
        return 0 if report["status"] == "completed" else 2
    except (p.ProtocolError, OSError, ValueError) as exc:
        if isinstance(exc, p.ProtocolError):
            print(f"Piloto detenido: {exc}")
        else:
            print("Piloto detenido por error del archivo local; no se reintenta inferencia.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
