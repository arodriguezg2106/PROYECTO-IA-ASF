from docx import Document

from revisor_crf import review_document
from revisor_crf.sample import create_sample


def test_demo_sample_contains_a_detectable_discrepancy(tmp_path):
    target = create_sample(tmp_path / "demo.docx", with_discrepancy=True)
    report = review_document(target)
    assert any(alert["rule_id"] == "NUM-TOTAL-001" for alert in report["alerts"])


def test_default_sample_does_not_add_demo_table(tmp_path):
    target = create_sample(tmp_path / "sample.docx")
    document = Document(target)
    assert all("Cuadro demostrativo" not in paragraph.text for paragraph in document.paragraphs)
