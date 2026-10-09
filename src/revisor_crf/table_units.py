"""Relaciones estructurales de unidades, sin inferir títulos de documentos."""

import re
from .units import evidence, signature
from .revisions import text_views


def plain(cell, view):
    return "\n".join(text_views(p, view)[0][0] for p in cell["blocks"] if p["type"] == "paragraph")


def unit_only(text):
    items = evidence(text, "none")
    return len(items) == 1 and text.strip(" ()[]:;.\n\t").lower() == items[0]["unit"].lower()


def clear_label(text):
    units = evidence(text, "none")
    return (bool(units) and len({signature(e["unit"]) for e in units}) == 1
            and len(text) <= 80 and not re.search(r"\d|\b(?:o|quizá|aproximadamente|alternativ[oa]|según)\b", text, re.I))


def adjacent_evidence(text, element_id, style=None):
    title = bool(re.match(r"\s*(?:tabla|cuadro|importes?|cifras)\b", text, re.I)) or style == "Caption"
    note = bool(re.match(r"\s*nota\b", text, re.I))
    declaration = bool(re.search(r"\b(?:expresad[oa]s?|expresan|cifras\s+en|importes?\s+en|unidad(?:es)?\s*:)\b", text, re.I))
    source = "table_title" if title else "table_note" if note else "previous_paragraph"
    applicable = unit_only(text) or declaration or ((title or note) and len(text) <= 140)
    result = evidence(text, source, element_id, title and applicable and clear_label(text))
    for e in result:
        e.update(applicable=applicable, relation_reason="declaracion_de_unidad" if applicable else "mencion_narrativa_sin_relacion_de_unidad")
    return result


def layout(table, view):
    """Bandas iniciales: rótulos fusionados, después encabezados, luego datos."""
    rows = table["rows"]
    width = max((c["grid_column"] + c["column_span"] - 1 for r in rows for c in r["cells"]), default=0)
    headers, title_rows, units = [], set(), []
    in_band = True
    for row in rows:
        cells = row["cells"]
        texts = [plain(c, view) for c in cells]
        nonempty = [(cell, text) for cell, text in zip(cells, texts) if text.strip()]
        merged = len(cells) == 1 and width > 1 and cells[0]["column_span"] >= width
        dominant_merged_title = (
            len(nonempty) == 1
            and width > 2
            and nonempty[0][0]["column_span"] >= width - 1
            and bool(re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]", nonempty[0][1]))
        )
        if in_band and (merged or dominant_merged_title):
            title_rows.add(row["index"])
            title_cell = nonempty[0][0] if nonempty else cells[0]
            for p in title_cell["blocks"]:
                if p["type"] == "paragraph":
                    text = text_views(p, view)[0][0]
                    for line in text.splitlines():
                        if unit_only(line):
                            units.extend(evidence(line, "table_title", p["id"], True))
            continue
        # Short labels may contain footnote indices; numeric data cells end the band.
        label_row = all(not t.strip() or (bool(re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ%]", t)) and len(t) <= 100
                        and not re.match(r"\s*[($+−-]?\d", t)) for t in texts)
        if row.get("is_header") or (in_band and label_row):
            headers.append(row)
        else:
            in_band = False
        if not in_band and merged:
            for p in cells[0]["blocks"]:
                if p["type"] == "paragraph":
                    text = text_views(p, view)[0][0]
                    if re.match(r"\s*nota\b", text, re.I):
                        units.extend(adjacent_evidence(text, p["id"]))
    return headers, title_rows, units
