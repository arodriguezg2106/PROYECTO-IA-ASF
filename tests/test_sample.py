from docx import Document

from revisor_crf import review_document
from revisor_crf.sample import DEMO_CASES, create_demo_cases, create_sample
from verify_direction_demo import verify


def test_demo_sample_contains_a_detectable_discrepancy(tmp_path):
    target = create_sample(tmp_path / "demo.docx", with_discrepancy=True)
    report = review_document(target)
    assert any(alert["rule_id"] == "NUM-TOTAL-001" for alert in report["alerts"])


def test_default_sample_does_not_add_demo_table(tmp_path):
    target = create_sample(tmp_path / "sample.docx")
    document = Document(target)
    assert all("Cuadro demostrativo" not in paragraph.text for paragraph in document.paragraphs)


def test_direction_demo_suite_is_synthetic_and_passes_preflight(tmp_path):
    output_dir = tmp_path / "demo"
    paths = create_demo_cases(output_dir)
    assert set(paths) == set(DEMO_CASES)
    assert all(path.is_file() for path in paths.values())

    result = verify(output_dir)
    assert result["synthetic_only"] is True
    assert result["case_count"] == 4
    assert result["passed"] is True
    assert all(item["passed"] for item in result["cases"])
