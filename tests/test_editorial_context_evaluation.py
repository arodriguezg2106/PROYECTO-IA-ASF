import json
from pathlib import Path
from revisor_crf.editorial import load_editorial_catalog
from revisor_crf.editorial_context_bank import load_context_bank
from revisor_crf.editorial_context_evaluation import evaluate_context_provider

class Provider:
    def review(self,request,schema):
        text=request["fragment"]
        findings=[]
        if "determinando" in text:findings=[{"rule_id":"ASF-ED-I-CONTEXT","category":"grammar","severity":"warning","problem_span":"determinando que","message":"Gerundio posterior.","suggested_text":"Se analizó la documentación y se determinó que existía una diferencia.","confidence":.95}]
        elif "entidad debía" in text:findings=[{"rule_id":"ASF-ED-I-CONTEXT","category":"grammar","severity":"warning","problem_span":"entidad debía","message":"Falta que.","suggested_text":"Se informó a la entidad que debía presentar la documentación.","confidence":.95}]
        elif "deficiencias" in text:findings=[{"rule_id":"ASF-ED-I-CONTEXT","category":"grammar","severity":"suggestion","problem_span":"programa","message":"Repetición.","suggested_text":"El programa presentó deficiencias debido a que careció de controles.","confidence":.9}]
        return json.dumps({"findings":findings},ensure_ascii=False)

def test_context_metrics_and_protection():
    cases=json.loads((Path(__file__).parent/"data"/"editorial_context_cases.json").read_text(encoding="utf-8"))["cases"][:6]
    rule=next(x for x in load_editorial_catalog()["rules"] if x["rule_id"]=="ASF-ED-I-CONTEXT")
    result=evaluate_context_provider(Provider(),cases,rule)
    assert result["precision"]==1 and result["recall"]==1 and result["accuracy"]==1
    assert result["invalid_responses"]==0 and result["unsafe_suggestions"]==0

def test_context_bank_test_split_is_not_empty():
    bank=load_context_bank(Path(__file__).parent/"data"/"editorial_context_cases.json")
    assert len([x for x in bank["cases"] if x["split"]=="test"])==30
