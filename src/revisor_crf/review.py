"""Motor local de validaciones determinísticas con evidencia trazable."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .catalog import load_catalog
from .numbers import extract_numbers, paragraph_contexts
from .reader import read_docx
from .revisions import text_views

ENGINE_VERSION = "0.4.1"
RULE_VERSIONS = {
    "NUM-TOTAL-001": "1.1",
    "NUM-CROSS-001": "1.1",
    "DOC-OBS-001": "1.0",
    "DATA-NEG-001": "1.0",
}
STOPWORDS = {
    "de", "del", "la", "las", "el", "los", "en", "y", "a", "por", "para", "un", "una",
    "importe", "monto", "total", "subtotal", "suma", "observado", "observada", "pesos", "peso",
}
MONETARY_HEADER = re.compile(
    r"\b(?:importe|monto|pagad[oa]s?|ejercid[oa]s?|contratad[oa]s?|observad[oa]s?|subtotal|total|precio|costo)\b",
    re.I,
)
RESULT_NUMBER = re.compile(r"\bn[uú]m\.?\s+del\s+resultado\s*:\s*(?P<number>\d+)", re.I)
RESULT_CHECKBOX = re.compile(
    r"\bn[uú]m\.?\s+del\s+resultado\s*:\s*(?P<number>\d+).*?"
    r"\bcon\s+observaci[oó]n\s+s[ií]\s*\(\s*(?P<yes>[x×☒■✓]?)\s*\)\s*"
    r"no\s*\(\s*(?P<no>[x×☒■✓]?)\s*\)", re.I,
)


def _plain(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _tokens(value: str | None) -> set[str]:
    return {token for token in _plain(value).split() if len(token) > 2 and token not in STOPWORDS}


def _scope_from_headings(headings: list[dict], section: str | None, scope_patterns: list[re.Pattern]) -> str:
    for heading in reversed(headings or []):
        text = heading.get("texto") or heading.get("text") or ""
        for pattern in scope_patterns:
            match = pattern.search(text)
            if match:
                return f"{section or 'sin-seccion'}:{_plain(match.group())}"
    return section or "sin-seccion"


def _location(number: dict) -> dict:
    return {
        "elemento_id": number.get("elemento_id"),
        "seccion": number.get("seccion"),
        "tabla": number.get("tabla"),
        "fila": number.get("fila"),
        "columna": number.get("columna"),
        "celda_id": number.get("celda_id"),
        "origen": number.get("origen"),
        "vistas": number.get("vistas", []),
        "resultado": number.get("resultado"),
        "tabla_ordinal": number.get("tabla_ordinal"),
        "encabezado_fila": number.get("encabezado_fila"),
        "encabezado_columna": number.get("encabezado_columna"),
    }


def _number_evidence(number: dict, role: str) -> dict:
    return {
        "rol": role,
        "cifra_id": number["id"],
        "texto": number.get("texto_original"),
        "contexto": number.get("contexto_inmediato"),
        "texto_busqueda": number.get("contexto_inmediato"),
        "valor": number.get("valor_normalizado"),
        "unidad": number.get("unidad_canonica") or number.get("unidad_original"),
        "ubicacion": _location(number),
    }


def _text_evidence(paragraph: dict, text: str, view: str, role: str,
                   coordinates: dict | None = None) -> dict:
    coordinates = coordinates or {}
    return {
        "rol": role,
        "elemento_id": paragraph["id"],
        "texto": " ".join(text.split())[:500],
        "texto_busqueda": " ".join(text.split())[:180],
        "ubicacion": {
            "elemento_id": paragraph["id"],
            "seccion": paragraph.get("section_id"),
            "tabla": coordinates.get("tabla"),
            "fila": coordinates.get("fila"),
            "columna": coordinates.get("columna"),
            "celda_id": coordinates.get("celda_id"),
            "origen": paragraph.get("source"),
            "vistas": [view],
            "resultado": coordinates.get("resultado"),
            "tabla_ordinal": coordinates.get("tabla_ordinal"),
            "encabezado_fila": coordinates.get("encabezado_fila"),
            "encabezado_columna": coordinates.get("encabezado_columna"),
        },
    }


def _human_locator(evidence: list[dict]) -> dict:
    primary = evidence[0]
    location = primary.get("ubicacion", {})
    parts = []
    if location.get("resultado"):
        parts.append(f"Resultado {location['resultado']}")
    if location.get("tabla_ordinal"):
        parts.append(f"Tabla {location['tabla_ordinal']}")
    if location.get("fila"):
        parts.append(f"fila {location['fila']}")
    if location.get("columna"):
        parts.append(f"columna {location['columna']}")
    if location.get("encabezado_columna"):
        parts.append(f"«{location['encabezado_columna']}»")
    search = primary.get("texto_busqueda") or primary.get("contexto") or primary.get("texto") or ""
    return {
        "ruta": " > ".join(parts) or location.get("elemento_id") or "Ubicación estructural disponible en la evidencia",
        "resultado": location.get("resultado"),
        "tabla_ordinal": location.get("tabla_ordinal"),
        "fila": location.get("fila"),
        "columna": location.get("columna"),
        "encabezado_fila": location.get("encabezado_fila"),
        "encabezado_columna": location.get("encabezado_columna"),
        "texto_busqueda": " ".join(str(search).split())[:180],
    }


def _verification_instruction(rule_id: str, operation: dict) -> str:
    if operation.get("type") == "not_evaluable":
        return "Confirme la relación, unidad, escala o bloque antes de decidir; el motor no realizó una operación automática."
    return {
        "NUM-TOTAL-001": "Verifique que las filas mostradas sean exactamente las que integran el subtotal o total.",
        "NUM-CROSS-001": "Confirme que ambas cifras correspondan al mismo concepto, contrato, resultado y unidad.",
        "DOC-OBS-001": "Revise la casilla SÍ/NO del resultado y la conclusión explícita asociada.",
        "DATA-NEG-001": "Confirme si el guion o paréntesis representa un valor negativo o solo formato documental.",
    }[rule_id]


def _navigation_context(document: dict, mode: str) -> dict:
    """Relaciona cada párrafo/vista con resultado y número ordinal de tabla."""
    current_result = {}
    table_ordinals = {}
    paragraphs = {}
    for paragraph, coordinates in paragraph_contexts(document):
        table_id = coordinates.get("tabla")
        if table_id and table_id not in table_ordinals:
            table_ordinals[table_id] = len(table_ordinals) + 1
        for text, _, view in text_views(paragraph, mode):
            match = RESULT_NUMBER.search(text)
            if match:
                current_result[view] = match.group("number")
            paragraphs[(paragraph["id"], view)] = {
                "resultado": current_result.get(view),
                "tabla_ordinal": table_ordinals.get(table_id),
            }
    return {"paragraphs": paragraphs, "tables": table_ordinals}


def _decorate_numbers(numbers: list[dict], navigation: dict) -> None:
    for number in numbers:
        contexts = [navigation["paragraphs"].get((number["elemento_id"], view), {})
                    for view in number.get("vistas") or ["final"]]
        results = {context.get("resultado") for context in contexts if context.get("resultado")}
        number["resultado"] = next(iter(results)) if len(results) == 1 else None
        number["tabla_ordinal"] = navigation["tables"].get(number.get("tabla"))


def _alert(rule_id: str, category: str, severity: str, message: str, operation: dict,
           evidence: list[dict], confidence: str, mode: str, *, reason: str | None = None) -> dict:
    if not evidence:
        raise ValueError("Una alerta requiere evidencia localizable.")
    fingerprint = "|".join([
        rule_id,
        mode,
        *(f"{item.get('cifra_id') or item.get('elemento_id')}@{','.join(item.get('ubicacion', {}).get('vistas', []))}"
          for item in evidence),
        str(operation.get("declarado")),
        str(operation.get("calculado")),
    ])
    identifier = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:20]
    return {
        "id": f"alert-{identifier}",
        "rule_id": rule_id,
        "rule_version": RULE_VERSIONS[rule_id],
        "category": category,
        "severity": severity,
        "status": "pending",
        "message": message,
        "operation": operation,
        "evidence": evidence,
        "where_to_review": _human_locator(evidence),
        "review_instruction": _verification_instruction(rule_id, operation),
        "confidence": confidence,
        "reading_mode": mode,
        "not_evaluable_reason": reason,
        "reviewer": {"status": "pending", "comment": ""},
    }


def _unit_signature(number: dict) -> tuple:
    return (number.get("tipo"), number.get("unidad_canonica"), str(number.get("multiplicador")))


def _view_key(number: dict) -> str:
    views = number.get("vistas") or ["final"]
    return "+".join(sorted(views))


def _unexpected_sign(number: dict) -> bool:
    value = number.get("valor_decimal")
    raw = (number.get("texto_original") or "").strip()
    return (isinstance(value, Decimal) and value < 0) or raw.startswith(("-", "−")) or "(" in raw


def _numbers_by_view(numbers: list[dict], mode: str) -> list[dict]:
    """Proyecta cifras normales en ambas vistas para que `all` no mezcle alternativas."""
    if mode != "all":
        return numbers
    projected = []
    for number in numbers:
        for view in number.get("vistas") or ["final"]:
            copy = dict(number)
            copy["vistas"] = [view]
            projected.append(copy)
    return projected


def _negative_alerts(numbers: list[dict], mode: str) -> tuple[list[dict], int]:
    alerts = []
    for number in numbers:
        value = number.get("valor_decimal")
        if number.get("tipo") not in {"importe", "cantidad", "porcentaje"} or not isinstance(value, Decimal):
            continue
        if _unexpected_sign(number):
            alerts.append(_alert(
                "DATA-NEG-001", "numeric_input", "medium",
                "Se encontró una cifra negativa o entre paréntesis; requiere interpretación humana.",
                {"type": "manual_review", "declarado": number.get("valor_normalizado"),
                 "calculado": None, "diferencia": None,
                 "unidad": number.get("unidad_canonica"), "escala": number.get("multiplicador")},
                [_number_evidence(number, "cifra_no_esperada")], "high", mode,
                reason="Las cifras negativas no se incorporan automáticamente a operaciones CRF.",
            ))
    return alerts, len(alerts)


def _total_rule(numbers: list[dict], catalog: dict, mode: str) -> tuple[list[dict], dict]:
    labels = [re.compile(pattern, re.I) for pattern in catalog["total_labels"]]
    def is_total_label(value: str | None) -> bool:
        raw = (value or "").strip()
        return any(pattern.fullmatch(raw) or pattern.fullmatch(_plain(raw)) for pattern in labels)

    grouped = defaultdict(list)
    for number in numbers:
        if number.get("tabla") and number.get("fila") and number.get("columna"):
            grouped[(number["tabla"], number["columna"], _view_key(number))].append(number)
    alerts, evaluated, excluded = [], 0, 0
    for values in grouped.values():
        values.sort(key=lambda item: (item["fila"], item.get("inicio", 0)))
        summary_rows = {}
        for item in values:
            label = item.get("encabezado_fila")
            if is_total_label(label):
                summary_rows[item["fila"]] = (
                    "subtotal" if _plain(label).startswith("subtotal") else "total"
                )
        total_rows = sorted(summary_rows)
        prior_summary = 0
        prior_total = 0
        for total_row in total_rows:
            declared = [item for item in values if item["fila"] == total_row]
            details = []
            block_strategy = "contiguous_details"
            if summary_rows[total_row] == "total":
                subtotal_rows = [row for row, kind in summary_rows.items()
                                 if kind == "subtotal" and prior_total < row < total_row]
                trailing = []
                if subtotal_rows:
                    detail_row = total_row - 1
                    while detail_row > max(subtotal_rows):
                        row_values = [item for item in values if item["fila"] == detail_row]
                        if not row_values:
                            break
                        trailing[0:0] = row_values
                        detail_row -= 1
                if subtotal_rows and (not trailing or len(subtotal_rows) > 1):
                    block_strategy = "named_subtotals"
                    for row in sorted(subtotal_rows):
                        details.extend(item for item in values if item["fila"] == row)
                    # Conserva detalles directos colocados después del último subtotal,
                    # pero no vuelve a sumar las filas ya cubiertas por un subtotal.
                    details.extend(trailing)
                else:
                    detail_row = total_row - 1
                    while detail_row > prior_summary:
                        row_values = [item for item in values if item["fila"] == detail_row]
                        if not row_values:
                            break
                        details[0:0] = row_values
                        detail_row -= 1
                prior_total = total_row
            else:
                detail_row = total_row - 1
                while detail_row > prior_summary:
                    row_values = [item for item in values if item["fila"] == detail_row]
                    if not row_values:
                        break
                    details[0:0] = row_values
                    detail_row -= 1
            prior_summary = total_row
            if len(declared) != 1:
                excluded += 1
                evidence = [_number_evidence(item, "total_candidato") for item in declared]
                if evidence:
                    alerts.append(_alert(
                        "NUM-TOTAL-001", "total", "medium",
                        "El total no es evaluable porque su fila contiene más de una cifra candidata.",
                        {"type": "not_evaluable", "declarado": None, "calculado": None,
                         "diferencia": None, "unidad": None, "escala": None}, evidence, "medium", mode,
                        reason="Fila de total ambigua.",
                    ))
                continue
            target = declared[0]
            ambiguous_detail_row = any(
                sum(item["fila"] == row for item in details) != 1
                for row in {item["fila"] for item in details}
            )
            invalid = [item for item in details if not item.get("usable_for_arithmetic") or
                       not isinstance(item.get("valor_normalizado"), Decimal) or
                       _unexpected_sign(item)]
            compatible = [item for item in details if _unit_signature(item) == _unit_signature(target)]
            target_value = target.get("valor_decimal")
            if (not details or ambiguous_detail_row or invalid or len(compatible) != len(details)
                    or not target.get("usable_for_arithmetic")
                    or not isinstance(target_value, Decimal) or _unexpected_sign(target)):
                excluded += 1
                evidence = [_number_evidence(target, "total_declarado")]
                evidence.extend(_number_evidence(item, "detalle_no_evaluable") for item in details[:10])
                alerts.append(_alert(
                    "NUM-TOTAL-001", "total", "medium",
                    "El subtotal o total no pudo evaluarse con seguridad.",
                    {"type": "not_evaluable", "declarado": target.get("valor_normalizado"),
                     "calculado": None, "diferencia": None,
                     "unidad": target.get("unidad_canonica"), "escala": target.get("multiplicador")},
                    evidence, "medium", mode,
                    reason="Faltan detalles elegibles o existen unidades, escalas o signos incompatibles.",
                ))
                continue
            calculated = sum((item["valor_normalizado"] for item in compatible), Decimal(0))
            declared_value = target["valor_normalizado"]
            evaluated += 1
            if calculated != declared_value:
                alerts.append(_alert(
                    "NUM-TOTAL-001", "total", "high",
                    "El subtotal o total declarado no coincide con la suma exacta de su bloque.",
                    {"type": "sum", "expression": " + ".join(str(item["valor_normalizado"]) for item in compatible),
                     "declarado": declared_value, "calculado": calculated,
                     "diferencia": declared_value - calculated,
                     "unidad": target.get("unidad_canonica"), "escala": target.get("multiplicador"),
                     "block_strategy": block_strategy},
                    [_number_evidence(target, "total_declarado"),
                     *[_number_evidence(item, "sumando") for item in compatible]], "high", mode,
                ))
    return alerts, {"evaluated": evaluated, "excluded": excluded}


def _cross_reference_rule(numbers: list[dict], catalog: dict, mode: str) -> tuple[list[dict], dict]:
    scope_patterns = [re.compile(pattern, re.I) for pattern in catalog["scope_markers"]]
    table_values = [
        item for item in numbers
        if item.get("tabla") and item.get("encabezado_fila")
        and MONETARY_HEADER.search(item.get("encabezado_columna") or "")
    ]
    narrative = [item for item in numbers if not item.get("tabla")]
    alerts, evaluated, excluded, used_pairs = [], 0, 0, set()
    for table_number in table_values:
        if not isinstance(table_number.get("valor_decimal"), Decimal) or _unexpected_sign(table_number):
            continue
        concept = _tokens(table_number.get("encabezado_fila"))
        if not concept or not table_number.get("usable_for_cross_reference"):
            continue
        scope = _scope_from_headings(table_number.get("jerarquia_encabezados", []), table_number.get("seccion"), scope_patterns)
        candidates, near_candidates = [], []
        for text_number in narrative:
            other_scope = _scope_from_headings(text_number.get("jerarquia_encabezados", []), text_number.get("seccion"), scope_patterns)
            context_tokens = _tokens(text_number.get("contexto_inmediato"))
            overlap = len(concept & context_tokens) / len(concept)
            same_result = (
                not table_number.get("resultado")
                or not text_number.get("resultado")
                or table_number["resultado"] == text_number["resultado"]
            )
            if (same_result and scope == other_scope
                    and _view_key(table_number) == _view_key(text_number) and overlap >= 0.6):
                near_candidates.append(text_number)
                if (_unit_signature(table_number) == _unit_signature(text_number)
                        and text_number.get("confidence") != "low"
                        and isinstance(text_number.get("valor_decimal"), Decimal)
                        and not _unexpected_sign(text_number)):
                    candidates.append(text_number)
        if len(candidates) > 1:
            excluded += 1
            alerts.append(_alert(
                "NUM-CROSS-001", "cross_reference", "medium",
                "La relación entre la cifra tabular y la narrativa es ambigua.",
                {"type": "not_evaluable", "declarado": table_number.get("valor_normalizado"),
                 "calculado": None, "diferencia": None,
                 "unidad": table_number.get("unidad_canonica"), "escala": table_number.get("multiplicador")},
                [_number_evidence(table_number, "cifra_tabular"),
                 *[_number_evidence(item, "candidato_narrativo") for item in candidates]], "medium", mode,
                reason="Más de una cifra narrativa coincide con el mismo concepto y ámbito.",
            ))
            continue
        if not candidates and near_candidates:
            excluded += 1
            alerts.append(_alert(
                "NUM-CROSS-001", "cross_reference", "medium",
                "La posible relación tabla–narrativa no es evaluable por su unidad, escala o confianza.",
                {"type": "not_evaluable", "declarado": table_number.get("valor_normalizado"),
                 "calculado": None, "diferencia": None,
                 "unidad": table_number.get("unidad_canonica"), "escala": table_number.get("multiplicador")},
                [_number_evidence(table_number, "cifra_tabular"),
                 *[_number_evidence(item, "candidato_narrativo") for item in near_candidates]], "medium", mode,
                reason="El concepto y el ámbito coinciden, pero la unidad, escala o confianza no es compatible.",
            ))
            continue
        if len(candidates) != 1:
            continue
        text_number = candidates[0]
        pair = (table_number["id"], text_number["id"], _view_key(table_number))
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        evaluated += 1
        table_value, narrative_value = table_number.get("valor_normalizado"), text_number.get("valor_normalizado")
        if isinstance(table_value, Decimal) and isinstance(narrative_value, Decimal) and table_value != narrative_value:
            alerts.append(_alert(
                "NUM-CROSS-001", "cross_reference", "high",
                "El importe de la tabla no coincide con el importe narrativo del mismo concepto.",
                {"type": "comparison", "declarado": table_value, "calculado": narrative_value,
                 "diferencia": table_value - narrative_value,
                 "unidad": table_number.get("unidad_canonica"), "escala": table_number.get("multiplicador")},
                [_number_evidence(table_number, "cifra_tabular"),
                 _number_evidence(text_number, "cifra_narrativa")], "high", mode,
            ))
    return alerts, {"evaluated": evaluated, "excluded": excluded}


def _observation_rule(document: dict, catalog: dict, mode: str,
                      navigation: dict) -> tuple[list[dict], dict]:
    positive = [re.compile(pattern, re.I) for pattern in catalog["observation_positive"]]
    negative = [re.compile(pattern, re.I) for pattern in catalog["observation_negative"]]
    conclusion = [re.compile(pattern, re.I) for pattern in catalog["conclusion_markers"]]
    scope_patterns = [re.compile(pattern, re.I) for pattern in catalog["scope_markers"]]
    findings = defaultdict(lambda: {"source": [], "conclusion": []})
    current_scope = {}
    for paragraph, coordinates in paragraph_contexts(document):
        for text, _, view in text_views(paragraph, mode):
            local_coordinates = {
                **coordinates,
                **navigation["paragraphs"].get((paragraph["id"], view), {}),
            }
            checkbox_match = RESULT_CHECKBOX.search(text)
            if checkbox_match:
                scope = f"{paragraph.get('section_id') or 'sin-seccion'}:resultado {checkbox_match.group('number')}"
                current_scope[view] = scope
                yes_checked, no_checked = bool(checkbox_match.group("yes")), bool(checkbox_match.group("no"))
                if yes_checked != no_checked:
                    state = "positive" if yes_checked else "negative"
                    findings[(scope, view)]["source"].append(
                        (state, paragraph, text, view, local_coordinates)
                    )
                continue
            negative_match = any(pattern.search(text) for pattern in negative)
            positive_match = not negative_match and any(pattern.search(text) for pattern in positive)
            if not (negative_match or positive_match):
                continue
            headings = paragraph.get("headings", [])
            heading_text = " ".join(item.get("text", "") for item in headings)
            role = "conclusion" if any(pattern.search(text + " " + heading_text) for pattern in conclusion) else "source"
            scope = (current_scope.get(view) if role == "conclusion" else None)
            scope = scope or _scope_from_headings(headings, paragraph.get("section_id"), scope_patterns)
            findings[(scope, view)][role].append(
                ("negative" if negative_match else "positive", paragraph, text, view, local_coordinates)
            )
    alerts, evaluated, excluded = [], 0, 0
    for roles in findings.values():
        if not roles["source"] or not roles["conclusion"]:
            continue
        source_states = {item[0] for item in roles["source"]}
        conclusion_states = {item[0] for item in roles["conclusion"]}
        if len(source_states) != 1 or len(conclusion_states) != 1:
            excluded += 1
            items = roles["source"] + roles["conclusion"]
            alerts.append(_alert(
                "DOC-OBS-001", "documentary_consistency", "medium",
                "El ámbito contiene marcadores contradictorios y no puede evaluarse automáticamente.",
                {"type": "not_evaluable", "declarado": None, "calculado": None,
                 "diferencia": None, "unidad": None, "escala": None},
                [_text_evidence(p, text, view, "marcador_ambiguo", coordinates)
                 for _, p, text, view, coordinates in items],
                "medium", mode, reason="Existen varios estados explícitos en el mismo ámbito.",
            ))
            continue
        evaluated += 1
        if source_states != conclusion_states:
            source_item, conclusion_item = roles["source"][0], roles["conclusion"][0]
            alerts.append(_alert(
                "DOC-OBS-001", "documentary_consistency", "medium",
                "La conclusión contradice el estado explícito de observación del resultado.",
                {"type": "status_comparison", "declarado": next(iter(source_states)),
                 "calculado": next(iter(conclusion_states)), "diferencia": None,
                 "unidad": None, "escala": None},
                [_text_evidence(source_item[1], source_item[2], source_item[3], "estado_resultado", source_item[4]),
                 _text_evidence(conclusion_item[1], conclusion_item[2], conclusion_item[3], "estado_conclusion", conclusion_item[4])],
                "high", mode,
            ))
    return alerts, {"evaluated": evaluated, "excluded": excluded}


def review_document(path: str | Path, mode: str = "final", catalog_path: str | Path | None = None) -> dict:
    """Ejecuta las tres reglas sobre un DOCX sin modificarlo."""
    source = Path(path)
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    document = read_docx(source, mode=mode)
    inventory = extract_numbers(document)
    navigation = _navigation_context(document, mode)
    _decorate_numbers(inventory["cifras"], navigation)
    evaluation_numbers = _numbers_by_view(inventory["cifras"], mode)
    catalog = load_catalog(catalog_path)
    alerts = []
    coverage = {}
    negative, negative_count = _negative_alerts(evaluation_numbers, mode)
    alerts.extend(negative)
    coverage["DATA-NEG-001"] = {"evaluated": len(evaluation_numbers), "excluded": 0,
                                "alerts": negative_count}
    for rule_id, runner in (("NUM-TOTAL-001", _total_rule), ("NUM-CROSS-001", _cross_reference_rule)):
        found, stats = runner(evaluation_numbers, catalog, mode)
        alerts.extend(found)
        coverage[rule_id] = {**stats, "alerts": len(found)}
    found, stats = _observation_rule(document, catalog, mode, navigation)
    alerts.extend(found)
    coverage["DOC-OBS-001"] = {**stats, "alerts": len(found)}
    after_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if before_hash != after_hash:
        raise RuntimeError("El archivo de entrada cambió durante la revisión.")
    alerts.sort(key=lambda item: (item["rule_id"], item["id"]))
    return {
        "schema_version": "review-1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": {"name": "revisor-crf-deterministic", "version": ENGINE_VERSION,
                   "catalog_version": catalog["version"], "rule_versions": RULE_VERSIONS},
        "source": {**document["source"], "sha256": before_hash, "unchanged": True},
        "reading_mode": mode,
        "rules_executed": list(coverage),
        "alerts": alerts,
        "coverage": coverage,
        "summary": {
            "alerts": len(alerts),
            "by_rule": dict(Counter(item["rule_id"] for item in alerts)),
            "by_severity": dict(Counter(item["severity"] for item in alerts)),
            "by_status": dict(Counter(item["status"] for item in alerts)),
            "evaluated": sum(item["evaluated"] for item in coverage.values()),
            "excluded": sum(item["excluded"] for item in coverage.values()),
        },
        "warnings": document["warnings"],
    }
