"""Evaluación externa acotada: sólo el banco sintético versionado del proyecto."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from evaluate_editorial_context import _source_commit, _write_json
from revisor_crf.editorial import SYSTEM_PROMPT, load_editorial_catalog, ollama_schema
from revisor_crf.editorial_context_bank import load_context_bank
from revisor_crf.editorial_context_evaluation import evaluate_context_provider
from revisor_crf.editorial_model_evaluation import aggregate_runs, build_stage_cases
from revisor_crf.editorial_models import evaluation_passes, load_model_registry

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("gemma4:31b", "gpt-oss:20b", "gpt-oss:120b")
STAGES = ("smoke", "hard", "final")
SCHEMA = ollama_schema(["ASF-ED-I-CONTEXT"])
CLOUD_PROMPT = SYSTEM_PROMPT + (
    "\nResponde únicamente con un objeto JSON que cumpla este esquema. "
    "No incluyas Markdown ni explicaciones fuera del JSON:\n"
    + json.dumps(SCHEMA, ensure_ascii=False, sort_keys=True)
)


class CloudStopped(Exception):
    """Interrumpe toda la corrida; el evaluador no debe absorber errores de acceso."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CloudSession:
    def __init__(self, token, max_requests, timeout, max_output_tokens, *,
                 prompt=CLOUD_PROMPT, think=None, record_response=False, on_result=None):
        self._token = token
        self.max_requests = max_requests
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.prompt = prompt
        self.think = think
        self.record_response = record_response
        self.on_result = on_result
        self.calls = []
        self.opener = urllib.request.build_opener(NoRedirect())

    def chat(self, model, request):
        if len(self.calls) >= self.max_requests:
            raise CloudStopped("request_budget_exhausted")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
            ],
            "stream": False,
            "options": {"temperature": 0, "seed": 20260923,
                        "num_predict": self.max_output_tokens},
        }
        if self.think is not None:
            payload["think"] = self.think
        # No se envía format: Cloud no garantiza generación con un esquema JSON.
        transport = urllib.request.Request(
            "https://ollama.com/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._token}"},
            method="POST",
        )
        call = {"model": model, "case_id": request["location"]["case_id"],
                "status": "started"}
        self.calls.append(call)
        started = time.perf_counter()
        try:
            with self.opener.open(transport, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("invalid_envelope")
            if body.get("error"):
                raise CloudStopped("cloud_response_error")
            for field in ("prompt_eval_count", "prompt_eval_cached_count", "eval_count"):
                value = body.get(field)
                if type(value) is int and value >= 0:
                    call[field] = value
            call.update(status="received", returned_model=body.get("model"),
                        done_reason=body.get("done_reason"))
            content = (body.get("message") or {}).get("content")
            if not isinstance(content, str):
                raise ValueError("missing_content")
            if self.record_response:
                call["response_text"] = content
            return content
        except urllib.error.HTTPError as exc:
            # Ni el cuerpo de error ni las cabeceras se imprimen o guardan.
            raise CloudStopped(f"cloud_http_{exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise CloudStopped("cloud_transport_error") from None
        except (ValueError, TypeError, AttributeError):
            call["status"] = "invalid_response"
            raise RuntimeError("cloud_invalid_envelope") from None
        finally:
            call["duration_seconds"] = round(time.perf_counter() - started, 4)
            if call["status"] == "started":
                call["status"] = "error"
            if self.on_result is not None:
                self.on_result(dict(call))


class CloudProvider:
    def __init__(self, session, model):
        self.session, self.model = session, model

    def review(self, request, schema):
        raw = self.session.chat(self.model, request)
        try:
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {"findings"}:
                raise ValueError()
            if not isinstance(data["findings"], list):
                raise ValueError()
            fields = set(SCHEMA["properties"]["findings"]["items"]["required"])
            for row in data["findings"]:
                if not isinstance(row, dict) or set(row) != fields:
                    raise ValueError()
                if any(not isinstance(row[key], str) for key in
                       ("rule_id", "category", "severity", "problem_span", "message")):
                    raise ValueError()
                if row["rule_id"] != "ASF-ED-I-CONTEXT" or row["severity"] not in {
                    "error", "warning", "suggestion", "info"
                }:
                    raise ValueError()
                if not row["problem_span"].strip():
                    raise ValueError()
                if row["suggested_text"] is not None and not isinstance(row["suggested_text"], str):
                    raise ValueError()
                confidence = row["confidence"]
                if (type(confidence) not in (int, float) or not math.isfinite(confidence)
                        or not 0 <= confidence <= 1):
                    raise ValueError()
        except (ValueError, TypeError, OverflowError):
            raise RuntimeError("cloud_invalid_schema") from None
        return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="gemma4:31b,gpt-oss:20b")
    parser.add_argument("--through", choices=STAGES, default="smoke")
    parser.add_argument("--max-requests", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--preflight", action="store_true", help="Sin credencial ni red")
    parser.add_argument("--probe", action="store_true",
                        help="Un caso y una solicitud, sólo para observar consumo")
    parser.add_argument("--output", default="results/ollama_cloud/evaluation.json")
    parser.add_argument("--protocol", choices=("legacy", "consistency-v1"), default="legacy")
    parser.add_argument("--phase", choices=("selection", "validation-a", "validation-b"))
    parser.add_argument("--freeze-bank", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--reviewed-bank-sha256")
    args = parser.parse_args(argv)
    if args.protocol == "consistency-v1":
        if (args.probe or args.through != "smoke" or args.max_requests != 12
                or args.max_output_tokens != 2048 or args.timeout != 60
                or args.output != "results/ollama_cloud/evaluation.json"
                or args.models not in ("gemma4:31b,gpt-oss:20b", "gemma4:31b")):
            parser.error("consistency-v1 tiene modelo, límites, parámetros y directorio propios.")
        from evaluate_editorial_consistency import run_cli
        return run_cli(args)
    if args.phase or args.freeze_bank or args.reviewer or args.reviewed_bank_sha256:
        parser.error("Las opciones de consistencia requieren --protocol consistency-v1.")
    models = [value.strip() for value in args.models.split(",") if value.strip()]
    if (not models or len(set(models)) != len(models) or set(models) - set(MODELS)
            or args.max_requests < 1 or not 0 < args.timeout <= 60
            or not 1 <= args.max_output_tokens <= 8192):
        parser.error("Modelos o límites inválidos; consulte --help.")
    if args.probe and (len(models) != 1 or args.through != "smoke"):
        parser.error("--probe requiere exactamente un modelo y --through smoke.")
    dataset_path = ROOT / "tests/data/editorial_context_cases.json"
    dataset = load_context_bank(dataset_path)
    cases = build_stage_cases(dataset["cases"], include_real=False)
    stages = STAGES[:STAGES.index(args.through) + 1]
    repetitions = 1 if args.probe else 3
    if args.probe:
        cases["smoke"] = cases["smoke"][:1]
        args.max_requests = 1
    required = sum(len(cases[stage]) for stage in stages) * repetitions * len(models)
    if args.max_requests < required:
        parser.error(f"El plan requiere como máximo {required} solicitudes; ajuste --max-requests.")
    payload = {
        "schema_version": "editorial-cloud-screening-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _source_commit(),
        "evaluation_scope": ("single_synthetic_usage_probe" if args.probe
                             else "synthetic_screening_only"),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "dataset_review_status": dataset["review_status"],
        "prompt_version": "editorial-context-cloud-1.0",
        "prompt_sha256": hashlib.sha256(CLOUD_PROMPT.encode("utf-8")).hexdigest(),
        "structured_output": "prompt_only_locally_validated",
        "thinking": "model_default",
        "selected_model": None,
        "plan": {"models": models, "stages": list(stages), "repetitions": repetitions,
                 "maximum_planned_requests": required, "max_requests": args.max_requests,
                 "max_output_tokens": args.max_output_tokens, "timeout_seconds": args.timeout},
        "criteria": load_model_registry()["approval_criteria"],
        "status": "preflight_complete", "results": [], "calls": [],
        "billing": {"free_credit_verified": False,
                    "note": "Los tokens no acreditan saldo ni garantizan costo cero."},
    }
    target = Path(args.output)
    session = None
    try:
        if not args.preflight:
            token = os.getenv("OLLAMA_API_KEY", "").strip()
            if not token:
                raise CloudStopped("missing_OLLAMA_API_KEY")
            session = CloudSession(token, args.max_requests, args.timeout, args.max_output_tokens)
            payload["calls"] = session.calls
            rule = next(row for row in load_editorial_catalog()["rules"]
                        if row["rule_id"] == "ASF-ED-I-CONTEXT")
            payload["status"] = "running"
            for model in models:
                provider = CloudProvider(session, model)
                result = {"model": model, "status": "running", "stages": []}
                payload["results"].append(result)
                for stage in stages:
                    print(f"{model}: {stage} ({len(cases[stage])} casos x {repetitions})", flush=True)
                    runs = []
                    for _ in range(repetitions):
                        runs.append(evaluate_context_provider(provider, cases[stage], rule))
                        _write_json(target, payload)
                    metrics = aggregate_runs(runs, len(cases[stage]))
                    passed = (False if args.probe else
                              evaluation_passes(metrics, payload["criteria"], repetitions=3))
                    result["stages"].append({"stage": stage,
                                             "status": ("observed" if args.probe else
                                                        "passed" if passed else "failed"),
                                             "metrics": metrics})
                    _write_json(target, payload)
                    if not passed:
                        break
                result["status"] = ("probe_completed" if args.probe else
                                    f"synthetic_{args.through}_passed" if passed else "failed")
            payload["status"] = "completed"
    except CloudStopped as exc:
        payload.update(status="stopped", stop_reason=str(exc))
        for result in payload["results"]:
            if result["status"] == "running":
                result["status"] = "interrupted"
    finally:
        payload["usage"] = {
            "attempted_requests": len(payload["calls"]),
            "reported_input_tokens": sum(row.get("prompt_eval_count", 0) for row in payload["calls"]),
            "reported_output_tokens": sum(row.get("eval_count", 0) for row in payload["calls"]),
            "responses_with_token_counts": sum("eval_count" in row and "prompt_eval_count" in row
                                              for row in payload["calls"]),
        }
        _write_json(target, payload)
    print(f"Evaluación: {payload['status']}; reporte: {target}")
    if payload["status"] == "stopped":
        print(f"Motivo: {payload['stop_reason']}")
        return 1
    return 0 if args.preflight or args.probe or any(row["status"].endswith("_passed")
                                     for row in payload["results"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
