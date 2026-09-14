"""Inventario numérico conservador. No valida ni compara cifras."""

import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from .revisions import text_views
from .confidence import apply_confidence, column_eligibility
from .units import resolve, evidence, signature
from .table_units import layout, clear_label, adjacent_evidence

MONTHS = {name: i for i, name in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio",
                                           "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1)}
DATE = r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{1,2}\s+de\s+(?:" + "|".join(MONTHS) + r")\s+de\s+\d{4})"
COMPOUND = r"(?:[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)+|(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]+)"
NUMBER = r"[+−-]?\d+(?:[.,]\d+|[ \u00a0\u202f]\d{3}(?!\d))*"
TOKEN = re.compile(r"(?P<fraction>\bfracci[oó]n\s+[IVXLCDM]+\b)|(?<!\w)(?P<date>" + DATE + r")(?!\w)|(?<!\w)(?P<compound>" + COMPOUND + r")(?!\w)|(?<!\w)(?P<number>" + NUMBER + r")(?!\w)", re.I)
UNIT = re.compile(r"(?<!\w)(?:millones?\s+de\s+pesos|miles\s+de\s+pesos|mdp|pesos|por\s+ciento|%)(?!\w)", re.I)
UNIT_AFTER = re.compile(r"\s*(?P<unit>millones?\s+de\s+pesos|miles\s+de\s+pesos|mdp|pesos|por\s+ciento|%)(?!\w)", re.I)
MONEY_PREFIX = re.compile(r"(?P<symbol>MX\$|US\$|MXN|USD|\$|€|£)\s*$", re.I)
IDENTIFIER = re.compile(r"\b(?P<kind>folios?|auditor[ií]as?|expedientes?|contratos?)\s*(?:(?:n[uú]m(?:ero)?|no)\.?\s*)?[:#-]?\s*$", re.I)
AUDIT_HEADER = re.compile(r"\s*(?:(?:n[uú]mero|n[uú]m\.?|no\.?)\s*(?:de\s+)?)?auditor[ií]a\s*[:#]?\s*", re.I)
ARTICLE = re.compile(r"\b(?:art[ií]culos?|arts?\.?)\s*(?:\d+\s*[,y]\s*)*$", re.I)
YEAR_HINT = re.compile(r"\b(?:año|ejercicio|ejercicio fiscal|cuenta p[uú]blica)\s*[:]?\s*$", re.I)
COUNT_HINT = re.compile(r"\b(?:cantidad|n[uú]mero de|total de)\b", re.I)
COUNT_AFTER = re.compile(r"\s*(?P<unit>personas|obras|acciones|municipios|contratos|beneficiarios|empleados|habitantes|unidades|documentos|kg|km|m²|m2|litros|horas)(?!\w)", re.I)


def decimal_value(raw):
    """Convención mexicana por defecto; reconoce pares de separadores invertidos."""
    token = re.sub(r"[\s\u00a0\u202f]", "", raw).replace("−", "-")
    errors = []
    if "," in token and "." in token:
        decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
        grouping = "," if decimal_sep == "." else "."
        whole, fraction = token.rsplit(decimal_sep, 1)
        unsigned = whole.lstrip("+-")
        if not re.fullmatch(r"\d{1,3}(?:" + re.escape(grouping) + r"\d{3})+", unsigned) or not fraction.isdigit():
            return None, ["separadores_no_validos"]
        token = whole.replace(grouping, "") + "." + fraction
    elif "," in token:
        if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+", token):
            token = token.replace(",", "")
        elif token.count(",") == 1:
            token = token.replace(",", ".")
        else:
            return None, ["separadores_no_validos"]
    elif token.count(".") > 1:
        if re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", token):
            token = token.replace(".", "")
            errors.append("agrupacion_con_punto_inferida")
        else:
            return None, ["separadores_no_validos"]
    try:
        return Decimal(token), errors
    except InvalidOperation:
        return None, ["valor_no_decimal"]


def unit_info(raw):
    kind, canonical, scale = signature(raw)
    return kind, scale


def bounded(text, length=80):
    return " ".join(text.split())[:length]


def detect_numbers(text, metadata=None):
    """Detecta candidatos en una sola vista. Los valores monetarios son Decimal."""
    metadata = metadata or {}
    results = []
    for match in TOKEN.finditer(text):
        raw = match.group()
        if not any(c.isdigit() for c in raw) and match.lastgroup != "fraction":
            continue
        start, end = match.span()
        prefix, suffix = text[max(0, start - 55):start], text[end:end + 45]
        identifier = IDENTIFIER.search(prefix)
        audit_header = AUDIT_HEADER.fullmatch(metadata.get("encabezado_columna") or "")
        parentheses = prefix.endswith("(") and suffix.startswith(")")
        unit_match = UNIT_AFTER.match(suffix[1:] if parentheses else suffix)
        money = MONEY_PREFIX.search(prefix[:-1] if parentheses else prefix)
        count_unit = COUNT_AFTER.match(suffix)
        problems = []
        kind, subtype, unit, symbol, unit_source = "otro", None, None, None, None
        multiplier = Decimal("1")
        value, normalized, iso_date = None, None, None
        numeric_start, numeric_end = start, end
        if match.lastgroup == "fraction":
            roman = raw.split()[-1].upper()
            values = {"I":1, "V":5, "X":10, "L":50, "C":100, "D":500, "M":1000}
            total = 0
            for i, letter in enumerate(roman):
                total += -values[letter] if i + 1 < len(roman) and values[letter] < values[roman[i + 1]] else values[letter]
            value = normalized = Decimal(total)
            kind = "fracción"
            if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", roman):
                problems.append("numeral_romano_no_canonico")
        elif identifier or audit_header:
            kind, subtype = ("numero_de_auditoria", "numero_auditoria") if audit_header or "auditor" in identifier.group("kind").lower() else ("folio", identifier.group("kind").lower())
            if re.fullmatch(r"\d+", raw):
                value = Decimal(raw)
        elif match.lastgroup == "date":
            kind = "fecha"
            try:
                if " de " in raw.lower():
                    day, month, year = re.split(r"\s+de\s+", raw.lower())
                    iso_date = date(int(year), MONTHS[month], int(day)).isoformat()
                else:
                    parts = re.split(r"[/-]", raw)
                    year, month, day = parts if len(parts[0]) == 4 else parts[::-1]
                    iso_date = date(int(year), int(month), int(day)).isoformat()
            except ValueError:
                problems.append("fecha_no_interpretable")
        elif match.lastgroup == "compound":
            problems.append("identificador_o_intervalo_sin_contexto")
        else:
            value, parse_problems = decimal_value(raw)
            problems.extend(parse_problems)
            if money:
                symbol = money.group("symbol")
                start = numeric_start - len(prefix) + money.start()
            if unit_match:
                unit = unit_match.group("unit")
                end += unit_match.end() + int(parentheses)
                unit_source = "texto_adyacente"
            else:
                previous_units = [u for u in UNIT.finditer(prefix) if not prefix[u.end():].strip(" :($\t")]
                if previous_units:
                    unit = previous_units[-1].group()
                    unit_source = "texto_adyacente"
            header = metadata.get("encabezado_columna") or ""
            row_header = metadata.get("encabezado_fila") or ""
            header_hint = header + " " + row_header
            if re.search(r"\bfracci[oó]n\s*$", prefix, re.I) or re.search(r"\bfracci[oó]n\b", header, re.I):
                kind = "fracción"
            elif ARTICLE.search(prefix) or re.search(r"\bart[ií]culo\b", header, re.I):
                kind = "artículo"
            elif YEAR_HINT.search(prefix) or re.search(r"\b(?:año|ejercicio)\b", header, re.I):
                kind = "año"
            elif re.search(r"\b(?:folio|expediente)\b", header, re.I):
                kind, subtype = "folio", "folio"
            elif unit:
                kind, multiplier = unit_info(unit)
            elif symbol:
                kind = "importe"
            elif count_unit or COUNT_HINT.search(header):
                kind = "cantidad"
                if count_unit:
                    unit = count_unit.group("unit")
                    end += count_unit.end()
                    unit_source = "texto_adyacente"
            else:
                units = list(UNIT.finditer(header_hint))
                inherited = metadata.get("unidad_tabla")
                if units:
                    unit = units[-1].group()
                    unit_source = "encabezado_fila" if UNIT.search(row_header) else "encabezado_columna"
                elif inherited and not re.search(r"\b(?:fecha|n[uú]mero|no\.|clave|c[oó]digo|cantidad)\b", header, re.I):
                    unit = inherited
                    unit_source = "rótulo_tabla"
                if unit:
                    kind, multiplier = unit_info(unit)
                    if len({unit_info(u.group()) for u in units}) > 1:
                        problems.append("unidades_de_encabezado_en_conflicto")
                elif value is not None and value == value.to_integral_value() and Decimal("1900") <= value <= Decimal("2099"):
                    kind = "año"
                    problems.append("año_inferido_por_rango")
                elif re.search(r"\b(?:importe|monto|pagado|pagados|presupuesto)\b[^\d.;:]*$", prefix, re.I) or re.search(r"\b(?:importe|monto)\b", header, re.I):
                    kind = "importe"
                    problems.append("moneda_o_unidad_no_especificada")
                elif value is not None:
                    kind = "cantidad"
                    problems.append("cantidad_sin_unidad_explicita")
            if parentheses and kind == "importe" and value is not None:
                value = -abs(value)
                if not money:
                    start -= 1
                if not unit_match:
                    end += 1
            if kind == "importe" and symbol == "$" and not unit:
                problems.append("moneda_no_especificada_por_simbolo")
            if value is not None and kind not in {"folio", "numero_de_auditoria"}:
                with localcontext() as ctx:
                    ctx.prec = max(28, len(value.as_tuple().digits) + 16)
                    normalized = value * multiplier
        results.append(apply_confidence(resolve({
            "texto_original": text[start:end], "valor_original": raw,
            "valor_decimal": value, "tipo": kind, "subtipo": subtype,
            "unidad_original": unit, "multiplicador": multiplier, "valor_normalizado": normalized,
            "simbolo_monetario": symbol, "unidad_origen": unit_source, "fecha_iso": iso_date,
            "contexto_inmediato": bounded(text[max(0, start - 32):min(len(text), end + 32)], 150),
            "ambigua": bool(problems), "motivos_ambiguedad": problems, "no_clasificada": kind == "otro",
            "inicio": start, "fin": end, "inicio_numero": numeric_start, "fin_numero": numeric_end,
            **metadata,
        })))
    return results


def _plain_cell(cell, mode):
    return "\n".join(text_views(p, mode)[0][0] for p in cell["blocks"] if p["type"] == "paragraph")


def paragraph_contexts(result):
    """Each XML paragraph exactly once; nested tables establish their own coordinates."""
    mode = result.get("reading_mode", "final")

    def blocks(items, coordinates=None):
        prior_units = {"final": None, "original": None}
        prior_evidence = {"final": [], "original": []}
        for item_index, item in enumerate(items):
            if item["type"] == "paragraph":
                yield item, coordinates or {}
                yield from blocks(item.get("blocks", []), coordinates)
                for view in prior_units:
                    visible = text_views(item, view)[0][0]
                    prior_evidence[view] = adjacent_evidence(visible, item["id"], (item.get("style") or {}).get("id"))
                    accepted = [e for e in prior_evidence[view] if e.get("applicable", True)]
                    prior_units[view] = accepted[0]["unit"] if accepted else None
            elif item["type"] == "table":
                # A brief, explicitly labelled note immediately after the table
                # supplies indirect unit evidence, never high confidence by itself.
                if item_index + 1 < len(items) and items[item_index + 1]["type"] == "paragraph":
                    note = items[item_index + 1]
                    for view in prior_units:
                        note_text = text_views(note, view)[0][0]
                        matches = list(UNIT.finditer(note_text))
                        if re.match(r"\s*nota\b", note_text, re.I):
                            prior_evidence[view].extend(evidence(note_text, "table_note", note["id"], False))
                        if prior_units[view] is None and re.match(r"\s*nota\b", note_text, re.I) and len(note_text) <= 100 and len(matches) == 1 and not re.search(r"\d", note_text):
                            prior_units[view] = matches[0].group()
                rows = item["rows"]
                layouts = {view: layout(item, view) for view in ("final", "original")}
                for row in rows:
                    for cell in row["cells"]:
                        col = cell["grid_column"]
                        leading = next((c for c in row["cells"] if c["grid_column"] < col), None)
                        labels = {}
                        for view in ("final", "original"):
                            header_rows, title_rows, internal_units = layouts[view]
                            header_cells = [c for r in header_rows if r["index"] < row["index"] for c in r["cells"]
                                            if c["grid_column"] <= col < c["grid_column"] + c["column_span"]]
                            header = " / ".join(_plain_cell(c, view) for c in header_cells)
                            row_label = _plain_cell(leading, view) if leading else ""
                            row_label = row_label if re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]", row_label) and not re.search(r"\d", row_label) else ""
                            labels[view] = {"encabezado_columna": bounded(header) or None,
                                            "encabezado_fila": bounded(row_label) or None,
                                            "encabezado_fila_id": leading["id"] if row_label else None,
                                            "unidad_tabla": prior_units[view],
                                            "table_unit_candidates": [*prior_evidence[view], *internal_units,
                                                *evidence(header, "column_header", [c["id"] for c in header_cells], clear_label(header)),
                                                *evidence(row_label, "row_header", leading["id"] if leading else None, clear_label(row_label))],
                                            "encabezado_columna_ids": [c["id"] for c in header_cells],
                                            "is_table_header": row["index"] in title_rows or row in header_rows,
                                            "column_header_unambiguous": clear_label(header),
                                            "row_header_unambiguous": clear_label(row_label)}
                        coords = {"tabla": item["id"], "fila": row["index"], "columna": col,
                                  "celda_id": cell["id"], "_labels_by_view": labels,
                                  "encabezado_columna_ids": [c["id"] for c in header_cells],
                                  "is_table_header": bool(row.get("is_header")) or row["index"] == 1 and bool(UNIT.search(_plain_cell(cell, "final" if mode == "all" else mode))) and not re.search(r"\d", _plain_cell(cell, "final" if mode == "all" else mode)),
                                  "metodo_encabezado": "tblHeader_o_banda_inicial_tras_rotulos_fusionados_y_celda_izquierda"}
                        yield from blocks(cell["blocks"], coords)
                prior_units = {"final": None, "original": None}
                prior_evidence = {"final": [], "original": []}
    yield from blocks(result["blocks"])
    for section in result["sections"]:
        for story in section["headers_and_footers"]:
            yield from blocks(story["blocks"])
    for story in result.get("supplementary_parts", []):
        yield from blocks(story["blocks"])


def extract_numbers(result):
    mode = result.get("reading_mode", "final")
    numbers = []
    seen = {}
    for paragraph, coordinates in paragraph_contexts(result):
        coordinates = dict(coordinates)
        labels = coordinates.pop("_labels_by_view", {})
        metadata = {"elemento_id": paragraph["id"], "seccion": paragraph["section_id"],
                    "origen": paragraph["source"], "tabla": None, "fila": None, "columna": None,
                    "encabezado_fila": None, "encabezado_columna": None, **coordinates}
        for text, mapping, view in text_views(paragraph, mode):
            for number in detect_numbers(text, {**metadata, **labels.get(view, {})}):
                source_positions = mapping[number["inicio"]:number["fin"]]
                states = {status for _, status in source_positions} - {"normal"}
                status = next(iter(states)) if len(states) == 1 else "unknown" if states else "normal"
                key = (paragraph["id"], tuple(i for i, _ in source_positions), number["tipo"], number["unidad_original"])
                if key in seen:
                    seen[key]["vistas"].append(view)
                    continue
                number["revision_status"] = status
                number["vistas"] = [view]
                number["offsets_text_all"] = [i for i, _ in source_positions]
                number["id"] = f"{paragraph['id']}/number-{len(numbers) + 1:05d}"
                if status == "unknown":
                    number["ambigua"] = True
                    number["motivos_ambiguedad"].append("revision_desconocida")
                apply_confidence(number)
                numbers.append(number)
                seen[key] = number
    column_eligibility(numbers)
    return {"schema_version": "numbers-1.3", "source": result["source"], "reading_mode": mode,
            "cifras": numbers,
            "resumen": {"detectadas": len(numbers), "clasificacion": dict(Counter(n["tipo"] for n in numbers)),
                        "ambiguas": sum(n["ambigua"] for n in numbers),
                        "no_clasificadas": sum(n["no_clasificada"] for n in numbers),
                        "confidence": dict(Counter(n["confidence"] for n in numbers)),
                        "utilizables": sum(n["usable_for_arithmetic"] for n in numbers),
                        "excluidas": sum(not n["usable_for_arithmetic"] for n in numbers),
                        "eligibilidad": {key: sum(n[key] for n in numbers) for key in ("usable_for_arithmetic", "usable_for_cross_reference", "usable_for_temporal_analysis", "usable_for_identifier_matching")},
                        "origen_unidad": dict(Counter(n["unit_source"] for n in numbers)),
                        "revision_status": dict(Counter(n["revision_status"] for n in numbers))},
            "warnings": result["warnings"]}
