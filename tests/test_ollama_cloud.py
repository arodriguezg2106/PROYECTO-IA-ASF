import io
import json
import urllib.error

import pytest

import evaluate_ollama_cloud as cloud
from revisor_crf.editorial import protected_elements


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.body).encode("utf-8")


def test_cloud_transport_uses_auth_without_format_or_retry():
    session = cloud.CloudSession("private-token", 1, 10, 512)
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Response({"model": "gemma4:31b", "message": {"content": '{"findings":[]}'},
                             "prompt_eval_count": 100, "eval_count": 8})

    session.opener = Opener()
    request = {"fragment": "Texto inventado.", "location": {"case_id": "x"}}
    assert session.chat("gemma4:31b", request) == '{"findings":[]}'
    sent = json.loads(requests[0].data)
    assert requests[0].full_url == "https://ollama.com/api/chat"
    assert requests[0].get_header("Authorization") == "Bearer private-token"
    assert "format" not in sent
    assert sent["options"]["num_predict"] == 512
    assert "findings" in sent["messages"][0]["content"]
    assert session.calls[0]["eval_count"] == 8
    assert "private-token" not in json.dumps(session.calls)
    with pytest.raises(cloud.CloudStopped, match="request_budget"):
        session.chat("gemma4:31b", request)
    assert len(requests) == 1


@pytest.mark.parametrize("code", [401, 403, 402, 429, 500, 302])
def test_access_or_quota_errors_stop_without_logging_body(code):
    session = cloud.CloudSession("private-token", 12, 10, 512)

    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, code, "sensitive", {},
                                         io.BytesIO(b"private-token"))

    session.opener = Opener()
    with pytest.raises(cloud.CloudStopped, match=f"^cloud_http_{code}$"):
        session.chat("gemma4:31b", {"location": {"case_id": "x"}})
    assert len(session.calls) == 1
    assert session.calls[0]["status"] == "error"
    assert "private-token" not in json.dumps(session.calls)


@pytest.mark.parametrize("bad_row", [
    {"problem_span": []}, {"problem_span": ""}, {"suggested_text": {}},
    {"confidence": True}, {"confidence": float("nan")}, {"confidence": 1.5},
    {"rule_id": "unknown"},
])
def test_cloud_schema_rejects_malformed_fields(bad_row):
    row = {"rule_id": "ASF-ED-I-CONTEXT", "category": "grammar", "severity": "warning",
           "problem_span": "Texto", "message": "Ejemplo", "suggested_text": None,
           "confidence": 0.9, **bad_row}

    class Session:
        def chat(self, *args):
            return json.dumps({"findings": [row]})

    provider = cloud.CloudProvider(Session(), "gemma4:31b")
    with pytest.raises(RuntimeError, match="cloud_invalid_schema"):
        provider.review({}, cloud.SCHEMA)


def test_preflight_and_missing_key_never_contact_cloud(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No debe contactar la nube")

    monkeypatch.setattr(cloud.CloudSession, "chat", forbidden)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    output = tmp_path / "evaluation.json"
    assert cloud.main(["--preflight", "--output", str(output)]) == 0
    data = json.loads(output.read_text("utf-8"))
    assert data["plan"]["maximum_planned_requests"] == 12
    assert data["usage"]["attempted_requests"] == 0
    assert data["selected_model"] is None
    assert cloud.main(["--output", str(output)]) == 1
    data = json.loads(output.read_text("utf-8"))
    assert data["stop_reason"] == "missing_OLLAMA_API_KEY"
    assert data["calls"] == []


def test_insufficient_budget_rejected_before_network():
    with pytest.raises(SystemExit) as exc:
        cloud.main(["--through", "hard", "--max-requests", "12"])
    assert exc.value.code == 2


def test_pipeline_reuses_gates_and_stops_failed_model(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "private-token")
    called = []

    def fake_chat(self, model, request):
        called.append(model)
        # El proveedor no recibe las etiquetas del banco ni el hallazgo esperado.
        assert "expected_finding" not in request
        assert "acceptable_spans" not in request
        assert request["protected_elements"] == protected_elements(request["fragment"])
        self.calls.append({"model": model, "prompt_eval_count": 10, "eval_count": 5})
        return '{"findings": []}'

    monkeypatch.setattr(cloud.CloudSession, "chat", fake_chat)
    output = tmp_path / "evaluation.json"
    assert cloud.main(["--through", "final", "--max-requests", "252",
                       "--output", str(output)]) == 2
    data = json.loads(output.read_text("utf-8"))
    assert len(called) == 12  # Seis por modelo; no pasa a difícil ni final.
    assert data["status"] == "completed"
    assert all(row["status"] == "failed" for row in data["results"])
    assert data["usage"]["reported_input_tokens"] == 120
    assert data["selected_model"] is None
    assert "private-token" not in output.read_text("utf-8")


def test_quota_interrupts_entire_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "private-token")
    called = []

    def no_quota(self, model, request):
        called.append(model)
        raise cloud.CloudStopped("cloud_http_429")

    monkeypatch.setattr(cloud.CloudSession, "chat", no_quota)
    output = tmp_path / "evaluation.json"
    assert cloud.main(["--output", str(output)]) == 1
    data = json.loads(output.read_text("utf-8"))
    assert called == ["gemma4:31b"]
    assert data["stop_reason"] == "cloud_http_429"
    assert data["results"][0]["status"] == "interrupted"


def test_usage_probe_makes_exactly_one_request_without_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "private-token")
    called = []

    def fake_chat(self, model, request):
        called.append((model, request["fragment"]))
        self.calls.append({"model": model, "prompt_eval_count": 100, "eval_count": 20})
        return '{"findings": []}'

    monkeypatch.setattr(cloud.CloudSession, "chat", fake_chat)
    output = tmp_path / "probe.json"
    assert cloud.main(["--probe", "--models", "gemma4:31b",
                       "--output", str(output)]) == 0
    data = json.loads(output.read_text("utf-8"))
    assert len(called) == 1
    assert data["plan"]["max_requests"] == 1
    assert data["usage"]["attempted_requests"] == 1
    assert data["evaluation_scope"] == "single_synthetic_usage_probe"
    assert data["results"][0]["status"] == "probe_completed"
    assert data["results"][0]["stages"][0]["status"] == "observed"
    assert data["selected_model"] is None


def test_probe_rejects_multiple_models():
    with pytest.raises(SystemExit):
        cloud.main(["--probe"])
