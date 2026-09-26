"""Carga reproducible del banco contextual sintético ampliado."""
from __future__ import annotations

import json
from pathlib import Path

_SUBJECTS=("La entidad","La unidad","La dirección","El área","El organismo","La dependencia","El programa")
_PAIRS=(
    ("omitió los controles, provocando una diferencia.","omitió los controles y ello provocó una diferencia.","provocando una diferencia","gerundio de consecuencia"),
    ("volvió a repetir la solicitud.","repitió la solicitud.","volvió a repetir","redundancia"),
    ("estaría identificando deficiencias.","identificó deficiencias.","estaría identificando","tiempo no concluyente"),
    ("comunicó a la unidad debía entregar el informe.","comunicó a la unidad que debía entregar el informe.","unidad debía","omisión de que"),
    ("concluyó que el proveedor pudiera incumplir.","concluyó que el proveedor incumplió.","pudiera incumplir","subjuntivo impropio"),
)
_HARD_IDS={"passive_unnecessary","passive_necessary_focus","conclusive_tense","long_sentence","concise_sentence","indicative_conclusion","ambiguous_pronoun","unambiguous_pronoun","logical_order","logical_order_clear"}


def load_context_bank(path):
    data=json.loads(Path(path).read_text(encoding="utf-8")); cases=[dict(x) for x in data["cases"]]
    for subject in _SUBJECTS:
        slug=(subject.lower().replace(" ","_").replace("á","a").replace("ó","o"))
        for index,(bad,good,span,focus) in enumerate(_PAIRS,1):
            cases.append({"case_id":f"derived_{slug}_{index}_bad","fragment":f"{subject} {bad}","expected_finding":True,"acceptable_spans":[span],"focus":focus})
            cases.append({"case_id":f"derived_{slug}_{index}_good","fragment":f"{subject} {good}","expected_finding":False,"acceptable_spans":[],"focus":f"contraejemplo válido: {focus}"})
    if len(cases)!=100:raise ValueError(f"El banco contextual debe contener 100 casos; contiene {len(cases)}.")
    for index,case in enumerate(cases):
        case["split"]="development" if index<40 else "calibration" if index<70 else "test"
        case["difficulty"]="hard" if case["case_id"] in _HARD_IDS else "standard"
    return {**data,"schema_version":"editorial-context-bank-2.0","synthetic":True,"cases":cases,
            "splits":{"development":40,"calibration":30,"test":30},"review_status":"expectations_pending_human_validation"}
