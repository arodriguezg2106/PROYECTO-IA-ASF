"""Elegibilidad conservadora; no ejecuta comparaciones ni valida importes."""

NON_MEASURES = {"año", "fecha", "artículo", "fracción", "folio", "numero_de_auditoria"}
EXPLANATIONS = {
    "cantidad_sin_unidad_explicita": "Cantidad sin unidad determinable.",
    "año_inferido_por_rango": "Podría ser un año; falta un rótulo inequívoco.",
    "moneda_o_unidad_no_especificada": "Falta moneda o unidad explícita.",
    "moneda_no_especificada_por_simbolo": "El símbolo no determina la moneda.",
    "identificador_o_intervalo_sin_contexto": "Identificador o intervalo sin contexto suficiente.",
    "tipo_no_identificado": "Tipo numérico no identificado.",
    "encabezado_no_inequivoco": "El encabezado no determina inequívocamente la unidad.",
    "unidades_de_encabezado_en_conflicto": "Los encabezados aportan unidades distintas.",
    "revision_desconocida": "Estado de revisión desconocido.",
    "fecha_no_interpretable": "La expresión no se puede normalizar como fecha.",
}


def apply_confidence(number):
    origins = {None: "none", "texto_adyacente": "explicit", "texto_previo": "nearby_text",
               "rótulo_tabla": "table_caption", "encabezado_columna": "column_header",
               "encabezado_fila": "row_header"}
    origin = origins.get(number.get("unidad_origen"), "none")
    number["origin_unit"] = origin
    reasons = list(number["motivos_ambiguedad"])
    if number.get("revision_status") == "unknown":
        reasons.append("revision_desconocida")
    if number["no_clasificada"]:
        reasons.append("tipo_no_identificado")
    if reasons or number["ambigua"]:
        number.update(classification="ambiguous", confidence="low", usable_for_comparison=False,
                      reason=" ".join(EXPLANATIONS.get(r, r.replace("_", " ")) for r in dict.fromkeys(reasons)) or "Contexto insuficiente.", ambigua=True)
    elif number["tipo"] in NON_MEASURES:
        number.update(classification=number["tipo"], confidence="medium", usable_for_comparison=False,
                      reason="Referencia no comparable como magnitud.")
    elif (number["valor_normalizado"] is not None and number["unidad_original"] and
          number.get("unit_source") in {"explicit", "column_header", "row_header", "table_title"} and number.get("unit_unambiguous")):
        number.update(classification=number["tipo"], confidence="high", usable_for_comparison=True,
                      reason="Tipo y unidad identificados; valor normalizable.")
    elif number["unidad_original"]:
        number.update(classification=number["tipo"], confidence="medium", usable_for_comparison=False,
                      reason="Evidencia indirecta o unidad insuficiente para comparación automática.")
    else:
        number.update(classification="ambiguous", confidence="low", usable_for_comparison=False,
                      reason="Sin unidad determinable.", ambigua=True)
    eligible = number["confidence"] != "low" and number.get("revision_status") != "unknown"
    measure = number["tipo"] in {"importe", "porcentaje", "cantidad"}
    number.update(usable_for_arithmetic=measure and number["confidence"] == "high",
                  usable_for_cross_reference=measure and eligible and bool(number.get("encabezado_fila")) and bool(number["unidad_original"]),
                  usable_for_temporal_analysis=eligible and (number["tipo"] == "año" or number["tipo"] == "fecha" and bool(number["fecha_iso"])),
                  usable_for_identifier_matching=eligible and number["tipo"] in {"folio", "numero_de_auditoria"})
    number["eligibility_scope"] = "Sólo elegibilidad futura; identidad del concepto y compatibilidad deben comprobarse antes de operar."
    return number


def column_eligibility(numbers):
    from collections import defaultdict
    from decimal import Decimal
    groups = defaultdict(list)
    for n in numbers:
        if n.get("tabla") and not n.get("is_table_header"):
            for view in n.get("vistas", ["final"]):
                groups[(n["tabla"], n["columna"], view)].append(n)
    outcomes = defaultdict(list)
    for (table, column, view), values in groups.items():
        eligible = all(n["tipo"] in {"importe", "porcentaje", "cantidad"} and n["confidence"] != "low" and
                       isinstance(n["valor_decimal"], Decimal) and n["valor_decimal"].is_finite() and n["unidad_original"] for n in values)
        scales = {(n.get("unidad_canonica"), str(n["multiplicador"]), n["tipo"]) for n in values}
        eligible = eligible and len(scales) == 1
        for n in values:
            outcomes[id(n)].append(bool(eligible))
    for n in numbers:
        if n.get("is_table_header"):
            n["usable_for_arithmetic"] = False
        if id(n) in outcomes:
            n["column_arithmetic_eligible"] = all(outcomes[id(n)])
            n["usable_for_arithmetic"] = n["column_arithmetic_eligible"]
            n["arithmetic_reason"] = "Columna con Decimal válidos y unidad/escala común." if n["column_arithmetic_eligible"] else "Columna con tipos, unidades, escalas o valores no elegibles."
        if n["tipo"] in NON_MEASURES:
            n["usable_for_arithmetic"] = False
