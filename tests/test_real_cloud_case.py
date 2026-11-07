import json

import pytest

import probe_real_ollama_case as real
from revisor_crf import editorial_consistency as p


def prepared(tmp_path, monkeypatch):
    source = tmp_path / "case.docx"
    source.write_bytes(b"local-fixture")
    before = "Se revisaron los derechos de agua nacionales por 18.00 pesos."
    after = "Se revisaron los derechos de aguas nacionales por 18.00 pesos."
    record = {"id": real.EVIDENCE_ID, "before": before, "after": after,
              "xml_paths": ["/w:document/w:body/w:p[1]"]}
    monkeypatch.setattr(real, "extract_evidence", lambda path: [record])
    return real.prepare(tmp_path, source), source


class Session:
    def __init__(self, fail=False, crash=False):
        self.requests = []
        self.fail = fail
        self.crash = crash
        self.on_result = None

    def chat(self, model, request):
        self.requests.append(request)
        if self.crash:
            raise KeyboardInterrupt()
        if self.fail:
            self.on_result({"status": "error"})
            raise RuntimeError("token-must-not-appear")
        self.on_result({"status": "received", "returned_model": model,
                        "response_text": '{"findings":[]}', "done_reason": "stop",
                        "prompt_eval_count": 100, "eval_count": 6})
        return '{"findings":[]}'


def test_prepare_is_offline_and_binds_document_and_configuration(tmp_path, monkeypatch):
    manifest, source = prepared(tmp_path, monkeypatch)
    assert len(manifest["variants"]) == 2
    assert manifest["max_requests"] == 6
    assert not (tmp_path / "result.json").exists()
    assert "agua nacionales" in (tmp_path / "case_preview.md").read_text("utf-8")
    assert real.prepare(tmp_path, source) == manifest
    source.write_bytes(b"modified")
    with pytest.raises(p.ProtocolError, match="source_or_configuration_changed"):
        real.prepare(tmp_path, source)


def test_only_two_blinded_paragraphs_are_sent_and_six_is_a_hard_limit(tmp_path, monkeypatch):
    manifest, _ = prepared(tmp_path, monkeypatch)
    session = Session()
    metadata = {"model": p.MODEL, "digest": "test"}
    report = real.execute(tmp_path, manifest, session, metadata)
    assert report["status"] == "completed"
    assert report["usage"]["attempted_requests"] == 6
    assert report["usage"]["reported_input_tokens"] == 600
    for request in session.requests:
        assert set(request) == {"fragment", "location", "rules", "criteria", "protected_elements"}
        assert "before" not in json.dumps(request) and "after" not in json.dumps(request)
        assert "case.docx" not in json.dumps(request)
        assert request["fragment"] in {variant["text"] for variant in manifest["variants"]}
    second = Session()
    real.execute(tmp_path, manifest, second, metadata)
    assert len(second.requests) == 0
    assert not (tmp_path / "experiment.json").exists()  # Es un diario independiente.


@pytest.mark.parametrize("crash", [False, True])
def test_failed_or_uncertain_attempt_is_not_resent(tmp_path, monkeypatch, crash):
    manifest, _ = prepared(tmp_path, monkeypatch)
    metadata = {"model": p.MODEL, "digest": "test"}
    session = Session(fail=not crash, crash=crash)
    expected_exception = KeyboardInterrupt if crash else p.ProtocolError
    with pytest.raises(expected_exception):
        real.execute(tmp_path, manifest, session, metadata)
    resumed = Session()
    report = real.execute(tmp_path, manifest, resumed, metadata)
    assert len(session.requests) == 1 and len(resumed.requests) == 5
    assert report["status"] == "completed_with_errors"
    assert report["attempts"][0]["assessment"]["invalid_response"]
    assert "token-must-not-appear" not in (tmp_path / "result.json").read_text("utf-8")


def test_metadata_change_blocks_additional_requests(tmp_path, monkeypatch):
    manifest, _ = prepared(tmp_path, monkeypatch)
    session = Session(fail=True)
    with pytest.raises(p.ProtocolError):
        real.execute(tmp_path, manifest, session, {"model": p.MODEL, "digest": "first"})
    another = Session()
    with pytest.raises(p.ProtocolError, match="manifest_or_model_changed"):
        real.execute(tmp_path, manifest, another, {"model": p.MODEL, "digest": "second"})
    assert another.requests == []


def test_invalid_response_and_nonliteral_evidence_are_recorded():
    assert real.assessment({"status": "received", "response_text": "bad JSON"}, "Texto")["invalid_response"]
    raw = json.dumps({"findings": [{"rule_id": "ASF-ED-I-CONTEXT", "category": "grammar", "severity": "suggestion",
                                   "problem_span": "no está", "message": "Mensaje", "suggested_text": None,
                                   "confidence": .9}]})
    result = real.assessment({"status": "received", "response_text": raw}, "Texto")
    assert result["nonliteral_spans"] == ["no está"]
