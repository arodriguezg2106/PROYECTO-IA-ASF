"""Entrada CLI de consistency-v1; el protocolo y las métricas están aislados del MVP."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from evaluate_editorial_context import _source_commit
from evaluate_ollama_cloud import CloudSession, CloudStopped, NoRedirect
from revisor_crf import editorial_consistency as protocol

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "results/ollama_cloud/consistency-v1"


def model_metadata():
    request = urllib.request.Request("https://ollama.com/api/tags", method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        model = next(row for row in body["models"] if row.get("name") == protocol.MODEL)
        return {"model": protocol.MODEL, "digest": model["digest"],
                "details": model.get("details"), "capabilities": sorted(model.get("capabilities", []))}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        raise protocol.ProtocolError("model_metadata_unavailable") from None


def implementation_hash():
    paths = (Path(__file__), ROOT / "scripts/evaluate_ollama_cloud.py",
             Path(protocol.__file__), ROOT / "src/revisor_crf/editorial.py")
    return protocol.digest({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})


def sender(token, experiment):
    sessions = {}

    def send(task, request, prompt, attempt):
        name = task["prompt"]
        if name not in sessions:
            sessions[name] = CloudSession(token, 60, 60, 2048, prompt=prompt,
                                          think=False, record_response=True)
        session = sessions[name]

        def persist(call):
            attempt.update(call)
            # El ID de sesión, perfil y repetición se preservan en el mismo registro.
            experiment.save()

        session.on_result = persist
        print(f"{task['phase']} / {name} / repetición {task['repetition']} / {task['case_id']}", flush=True)
        return session.chat(protocol.MODEL, request)

    return send


def preflight(bank):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    (DIRECTORY / "bank_review.md").write_text(protocol.review_markdown(bank), encoding="utf-8")
    reviewed = False
    reason = "bank_pending_human_review"
    try:
        protocol.reviewed_bank(DIRECTORY, bank)
        reviewed, reason = True, None
    except protocol.ProtocolError as exc:
        reason = str(exc)
    payload = {"protocol": protocol.PROTOCOL, "model": protocol.MODEL,
               "status": "ready" if reviewed else "pending_review", "bank_sha256": protocol.digest(bank),
               "review_blocker": reason, "new_inference_requests": 0,
               "phases": {"selection": 60, "validation-a": 60, "validation-b": 60},
               "parameters": protocol.PARAMETERS, "review_file": "bank_review.md"}
    protocol.write_json(DIRECTORY / "preflight.json", payload)
    print(f"Preflight sin red: {payload['status']}; banco SHA-256: {payload['bank_sha256']}")
    print(f"Revisión de etiquetas: {DIRECTORY / 'bank_review.md'}")
    return payload


def run_cli(args):
    try:
        bank = protocol.load_bank()
        if args.preflight:
            if args.freeze_bank or args.phase:
                raise protocol.ProtocolError("preflight_no_acepta_fase_ni_congelacion")
            preflight(bank)
            return 0
        if args.freeze_bank:
            if args.phase:
                raise protocol.ProtocolError("freeze_no_acepta_fase")
            protocol.freeze_bank(DIRECTORY, bank, args.reviewer, args.reviewed_bank_sha256)
            print("Banco congelado tras revisión explícita; no se consumió API.")
            return 0
        if not args.phase:
            raise protocol.ProtocolError("phase_required")
        with protocol.experiment_lock(DIRECTORY):
            experiment = protocol.ConsistencyExperiment(DIRECTORY, bank, _source_commit(), implementation_hash())
            # Comprobar fase y ventana antes de usar credencial o contactar servicios.
            experiment.check_phase(args.phase, protocol.timestamp())
            if experiment.state["phases"].get(args.phase, {}).get("status") == "completed":
                print("La fase ya terminó; no se repiten solicitudes.")
                return 0
            token = os.getenv("OLLAMA_API_KEY", "").strip()
            if not token:
                raise protocol.ProtocolError("missing_OLLAMA_API_KEY")
            report = experiment.run(args.phase, model_metadata(), sender(token, experiment))
        print(f"Fase terminada: {report['conclusion']}; intentos acumulados: {report['usage']['attempted_requests']}/180")
        print(f"Reporte: {DIRECTORY / 'report.md'}")
        if args.phase == "selection":
            return 0 if report["selected_prompt"] else 2
        return 0 if all(row["quality_passed"] for row in report["phases"][args.phase]["profiles"].values()) else 2
    except (protocol.ProtocolError, CloudStopped) as exc:
        print(f"Evaluación detenida: {exc}")
        return 1
