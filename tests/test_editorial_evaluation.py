import json
from pathlib import Path
from editorial_validation_bank import CASES, generate
from evaluate_editorial import main
from revisor_crf.editorial_evaluation import evaluate_cases, render_evaluation_markdown

def test_multiset_metrics_include_false_positives_and_omissions():
    cases=[{"case_id":"a","expected_findings":[{"rule_id":"R1","problem_span":"x"},{"rule_id":"R1","problem_span":"x"}]}]
    reports={"a":{"findings":[{"rule_id":"R1","problem_span":"x"},{"rule_id":"R2","problem_span":"z"}]}}
    result=evaluate_cases(cases,reports)
    assert result["summary"]=={"cases":1,"true_positives":1,"false_positives":1,"false_negatives":1,"precision":.5,"recall":.5,"f1":.5}
    assert "Evaluación editorial sintética" in render_evaluation_markdown(result)

def test_generated_bank_and_cli_are_reproducible(tmp_path):
    bank=tmp_path/"bank"; payload=generate(bank)
    assert payload["synthetic"] is True and len(payload["cases"])==len(CASES)
    output=tmp_path/"evaluation.json"; markdown=tmp_path/"evaluation.md"
    code=main(["--bank",str(bank),"--output",str(output),"--markdown",str(markdown)])
    result=json.loads(output.read_text(encoding="utf-8"))
    assert code==0
    assert result["summary"]["false_positives"]==0
    assert result["summary"]["false_negatives"]==0
    assert markdown.is_file()
