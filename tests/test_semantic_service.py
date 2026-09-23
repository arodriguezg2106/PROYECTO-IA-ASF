import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from revisor_crf.semantic_service import SemanticJobQueue, build_handler


class Provider:
    config = SimpleNamespace(model="approved-model")

    def metadata(self):
        return {"provider": "static", "model": "approved-model", "digest": "sha256:model"}

    def analyze(self, cases, phase):
        return [{
            "case_id": case["case_id"], "relation": "uncertain",
            "table_measure": "unspecified", "narrative_measure": "unspecified",
            "confidence": 0.0, "table_evidence": "", "narrative_evidence": "",
        } for case in cases]


def request(url, path, token=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    return urllib.request.urlopen(urllib.request.Request(url + path, data=data, headers=headers), timeout=3)


def test_institutional_service_auth_health_and_contract():
    jobs = SemanticJobQueue(Provider(), maxsize=2)
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(jobs, "secret", 3))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with request(base, "/health", "secret") as response:
            health = json.loads(response.read())
        assert health["model"] == "approved-model" and health["digest"] == "sha256:model"
        with request(base, "/v1/semantic-relations", "secret", {
            "schema_version": "semantic-1.0", "phase": "associate", "model": "approved-model",
            "cases": [{"case_id": "case-1"}],
        }) as response:
            result = json.loads(response.read())
        assert result["decisions"][0]["case_id"] == "case-1"
        try:
            request(base, "/health")
            raise AssertionError("La salud del servicio no debe exponerse sin autenticación")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
