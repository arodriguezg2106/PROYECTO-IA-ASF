"""Métricas separadas para la revisión contextual editorial."""
from __future__ import annotations
import time
from .editorial import _parse_response, ollama_schema, protected_elements, verify_protected

def evaluate_context_provider(provider, cases, rule):
    results=[]; tp=fp=fn=tn=invalid=unsafe=0; started=time.perf_counter()
    schema=ollama_schema([rule["rule_id"]])
    for case in cases:
        request={"fragment":case["fragment"],"location":{"case_id":case["case_id"]},"rules":[rule],"protected_elements":protected_elements(case["fragment"])}
        error=None; case_invalid=0
        try:rows=_parse_response(provider.review(request,schema),{rule["rule_id"]})
        except (RuntimeError,ValueError) as exc:rows=[]; error=str(exc); invalid+=1; case_invalid+=1
        valid=[]
        for row in rows:
            if row["problem_span"] not in case["fragment"]:invalid+=1; case_invalid+=1; error="editorial_problem_span_not_literal"; continue
            if row.get("suggested_text") and not verify_protected(case["fragment"],row["suggested_text"])["safe"]:unsafe+=1; continue
            valid.append(row)
        predicted=bool(valid); expected=bool(case["expected_finding"])
        span_ok=not predicted or not expected or any(any(token in row["problem_span"] or row["problem_span"] in token for token in case["acceptable_spans"]) for row in valid)
        if predicted and expected and span_ok:tp+=1
        elif predicted and not expected:fp+=1
        elif expected:fn+=1
        else:tn+=1
        results.append({"case_id":case["case_id"],"expected":expected,"predicted":predicted,"span_accepted":span_ok,"invalid_responses":case_invalid,"findings":valid,"error":error})
    precision=tp/(tp+fp) if tp+fp else 0.0; recall=tp/(tp+fn) if tp+fn else 0.0
    return {"cases":len(cases),"true_positives":tp,"false_positives":fp,"false_negatives":fn,"true_negatives":tn,
            "precision":round(precision,4),"recall":round(recall,4),"accuracy":round((tp+tn)/len(cases),4) if cases else 0.0,
            "invalid_responses":invalid,"unsafe_suggestions":unsafe,"duration_seconds":round(time.perf_counter()-started,4),"details":results}
