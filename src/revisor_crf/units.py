"""Evidencia y procedencia de unidades; no fuerza unidades contradictorias."""

import re
from decimal import Decimal

PATTERN = re.compile(r"(?<!\w)(millones?\s+de\s+pesos|miles\s+de\s+pesos|mdp|pesos|por\s+ciento|%|personas|obras|municipios|unidades|kg|km|litros|horas)(?!\w)", re.I)


def signature(unit):
    unit = " ".join(unit.lower().split())
    if unit == "mdp" or unit.startswith("millon") or unit.startswith("millón"):
        return "importe", "pesos", Decimal("1000000")
    if unit.startswith("miles"):
        return "importe", "pesos", Decimal("1000")
    if unit == "pesos":
        return "importe", "pesos", Decimal("1")
    if unit in {"%", "por ciento"}:
        return "porcentaje", "%", Decimal("1")
    return "cantidad", unit, Decimal("1")


def evidence(text, source, element_id=None, certain=False):
    return [{"unit": m.group(), "source": source, "element_id": element_id, "unambiguous": certain}
            for m in PATTERN.finditer(text or "")]


def resolve(number):
    candidates = list(number.get("table_unit_candidates", []))
    for field, source in (("encabezado_columna", "column_header"), ("encabezado_fila", "row_header")):
        candidates.extend(evidence(number.get(field), source,
                                   number.get(field + "_id") or number.get(field + "_ids"),
                                   number.get(source + "_unambiguous", False)))
    if number.get("unidad_tabla") and not number.get("table_unit_candidates"):
        candidates.append({"unit": number["unidad_tabla"], "source": "table_title", "element_id": None,
                           "unambiguous": number.get("table_title_unambiguous", False)})
    if number.get("unidad_original") and number.get("unidad_origen") in {"texto_adyacente", "texto_previo"}:
        candidates.insert(0, {"unit": number["unidad_original"], "source": "explicit" if number["unidad_origen"] == "texto_adyacente" else "previous_paragraph",
                              "element_id": number.get("elemento_id"), "unambiguous": number["unidad_origen"] == "texto_adyacente"})
    number["unit_candidates"] = candidates
    candidates = [c for c in candidates if c.get("applicable", True)]
    if not candidates:
        number.update(unit_source="none", unit_unambiguous=False)
        return number
    # Never assign inherited monetary units to references or identifiers.
    if number["tipo"] in {"fecha", "año", "artículo", "fracción", "folio", "numero_de_auditoria", "otro"}:
        number.update(unit_source="none", unit_unambiguous=False)
        return number
    if len({signature(c["unit"]) for c in candidates}) > 1:
        number.update(unit_source="none", unit_unambiguous=False, ambigua=True,
                      unidad_original=None, valor_normalizado=None)
        number["motivos_ambiguedad"].append("unidades_contradictorias")
        return number
    priority = {"explicit": 0, "column_header": 1, "row_header": 2, "table_title": 3, "table_note": 4, "previous_paragraph": 5}
    chosen = min(candidates, key=lambda c: priority[c["source"]])
    kind, canonical, scale = signature(chosen["unit"])
    number.update(unit_source=chosen["source"], unit_unambiguous=chosen["unambiguous"],
                  unit_element_id=chosen["element_id"], unidad_original=chosen["unit"],
                  unidad_canonica=canonical, multiplicador=scale, tipo=kind)
    number["unidad_origen"] = {"explicit": "texto_adyacente", "column_header": "encabezado_columna", "row_header": "encabezado_fila",
                               "table_title": "rótulo_tabla", "table_note": "rótulo_tabla", "previous_paragraph": "texto_previo"}[chosen["source"]]
    if number["valor_decimal"] is not None:
        from decimal import localcontext
        with localcontext() as context:
            context.prec = max(28, len(number["valor_decimal"].as_tuple().digits) + 16)
            number["valor_normalizado"] = number["valor_decimal"] * scale
    removable = {"cantidad_sin_unidad_explicita", "moneda_o_unidad_no_especificada", "moneda_no_especificada_por_simbolo"}
    number["motivos_ambiguedad"] = [r for r in number["motivos_ambiguedad"] if r not in removable]
    number["ambigua"] = bool(number["motivos_ambiguedad"])
    return number
