"""Servicio institucional mínimo para aislar Ollama y serializar inferencias."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import queue
import ssl
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .semantic import OllamaProvider, SCHEMA_VERSION, SemanticConfig


LOGGER = logging.getLogger("revisor_crf.semantic_service")
MAX_BODY = 2 * 1024 * 1024
MAX_CASES = 100


class SemanticJobQueue:
    def __init__(self, provider: OllamaProvider, maxsize: int = 32):
        self.provider = provider
        self.jobs: queue.Queue = queue.Queue(maxsize=maxsize)
        self.worker = threading.Thread(target=self._work, name="semantic-worker", daemon=True)
        self.worker.start()

    def _work(self) -> None:
        while True:
            cases, phase, event, result = self.jobs.get()
            try:
                result["decisions"] = self.provider.analyze(cases, phase)
            except Exception as exc:  # La frontera HTTP traduce la falla sin exponer contenido.
                result["error"] = str(exc)[:120]
            finally:
                event.set()
                self.jobs.task_done()

    def submit(self, cases: list[dict], phase: str, timeout: float) -> list[dict]:
        event, result = threading.Event(), {}
        try:
            self.jobs.put_nowait((cases, phase, event, result))
        except queue.Full as exc:
            raise RuntimeError("semantic_queue_full") from exc
        if not event.wait(timeout):
            raise RuntimeError("semantic_queue_timeout")
        if result.get("error"):
            raise RuntimeError(result["error"])
        return result.get("decisions", [])


def build_handler(job_queue: SemanticJobQueue, token: str, timeout: float):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RevisorCRFSemantic/1.0"

        def log_message(self, _format, *args):
            LOGGER.info("http", extra={"client": self.client_address[0], "status": args[1] if len(args) > 1 else None})

        def _json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            return bool(token) and hmac.compare_digest(supplied, expected)

        def do_GET(self):
            if self.path != "/health":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            provider_metadata = job_queue.provider.metadata()
            self._json(HTTPStatus.OK, {"status": "ok", "schema_version": SCHEMA_VERSION,
                                      "queue_depth": job_queue.jobs.qsize(),
                                      "model": provider_metadata.get("model"),
                                      "digest": provider_metadata.get("digest")})

        def do_POST(self):
            started = time.perf_counter()
            if self.path != "/v1/semantic-relations":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_BODY:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_body_size"})
                return
            raw = self.rfile.read(length)
            request_hash = hashlib.sha256(raw).hexdigest()
            try:
                payload = json.loads(raw.decode("utf-8"))
                phase = payload["phase"]
                cases = payload["cases"]
                if payload.get("schema_version") != SCHEMA_VERSION or phase not in {"associate", "verify"}:
                    raise ValueError
                if payload.get("model") != job_queue.provider.config.model:
                    self._json(HTTPStatus.CONFLICT, {"error": "model_mismatch"})
                    return
                if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
                    raise ValueError
                if any(not isinstance(case, dict) or not isinstance(case.get("case_id"), str) for case in cases):
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
                return
            try:
                decisions = job_queue.submit(cases, phase, timeout)
            except RuntimeError as exc:
                status = HTTPStatus.TOO_MANY_REQUESTS if str(exc) == "semantic_queue_full" else HTTPStatus.SERVICE_UNAVAILABLE
                self._json(status, {"error": str(exc)})
                return
            LOGGER.info(json.dumps({
                "event": "semantic_request", "request_sha256": request_hash,
                "phase": phase, "cases": len(cases),
                "duration_seconds": round(time.perf_counter() - started, 6),
            }, separators=(",", ":")))
            self._json(HTTPStatus.OK, {"schema_version": SCHEMA_VERSION, "decisions": decisions})

    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Servicio interno de relaciones semánticas CRF.")
    parser.add_argument("--config", required=True, help="Configuración local de Ollama en JSON o TOML")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--certfile")
    parser.add_argument("--keyfile")
    parser.add_argument("--token-env", default="REVISOR_CRF_SEMANTIC_TOKEN")
    parser.add_argument("--queue-size", type=int, default=32)
    args = parser.parse_args(argv)
    try:
        config = SemanticConfig.load(args.config)
        if config.provider != "ollama" or config.profile != "local":
            raise ValueError("El servicio debe conectarse a un proveedor Ollama local.")
        token = os.environ.get(args.token_env, "")
        if not token:
            raise ValueError(f"Falta la variable de token {args.token_env}.")
        if args.host not in {"127.0.0.1", "localhost", "::1"} and not (args.certfile and args.keyfile):
            raise ValueError("Un servicio accesible por red requiere --certfile y --keyfile.")
        jobs = SemanticJobQueue(OllamaProvider(config), maxsize=args.queue_size)
        metadata = jobs.provider.metadata()
        if not metadata.get("digest"):
            raise ValueError("No se pudo verificar el digest del modelo local.")
        if config.expected_model_digest and metadata["digest"] != config.expected_model_digest:
            raise ValueError("El digest del modelo local no coincide con el autorizado.")
        server = ThreadingHTTPServer((args.host, args.port), build_handler(jobs, token, config.timeout_seconds))
        if args.certfile or args.keyfile:
            if not (args.certfile and args.keyfile):
                raise ValueError("Se requieren juntos --certfile y --keyfile.")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(args.certfile, args.keyfile)
            server.socket = context.wrap_socket(server.socket, server_side=True)
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        server.serve_forever()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
