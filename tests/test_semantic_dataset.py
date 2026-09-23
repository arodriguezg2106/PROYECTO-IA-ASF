import json

from semantic_dataset import main


def _write_review_files(tmp_path, document_hash, item_id):
    suggestion = {
        "id": item_id,
        "case_id": "same-structural-id",
        "relation": "same_measure",
        "table_measure": "pagado",
        "narrative_measure": "pagado",
        "table": {"text": "100 pesos"},
        "narrative": {"text": "Se pagaron 120 pesos."},
    }
    report = {
        "source": {"sha256": document_hash},
        "engine": {"version": "0.5.0"},
        "semantic_review": {"prompt_version": "semantic-link-1.3",
                            "suggestions": [suggestion], "accepted_relations": []},
        "alerts": [],
    }
    decisions = {
        "source_sha256": document_hash,
        "decisions": [{"item_id": item_id, "status": "confirmed"}],
    }
    report_path = tmp_path / f"report-{item_id}.json"
    decisions_path = tmp_path / f"decisions-{item_id}.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
    return report_path, decisions_path


def test_dataset_deduplicates_by_document_and_structural_case_id(tmp_path):
    output = tmp_path / "dataset.jsonl"
    for document_hash, item_id in (("a" * 64, "suggestion-a"), ("b" * 64, "suggestion-b")):
        report, decisions = _write_review_files(tmp_path, document_hash, item_id)
        assert main([
            "--report", str(report), "--decisions", str(decisions), "--output", str(output),
            "--reviewer", "reviewer", "--approved-by", "approver",
        ]) == 0

    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert {item["document_sha256"] for item in records} == {"a" * 64, "b" * 64}
