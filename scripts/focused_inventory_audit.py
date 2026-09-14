"""Diagnóstico reproducible sin texto de CRF: IDs, unidades y agregados."""

import json
from collections import Counter, defaultdict
from pathlib import Path

from revisor_crf import read_docx, export_json
from revisor_crf.numbers import paragraph_contexts
from revisor_crf.table_units import layout, plain
from revisor_crf.units import evidence
from audit_crf import INPUT, ROOT, output_elements
from inventory_audit_reports import markdown_table

OUT = ROOT / "results/auditoria_focalizada"
CURRENT = ROOT / "results/inventario_cifras/final"


def documents(folder):
    result = {}
    for p in folder.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if "cifras" in d:
            result[d["source"]["file"]] = d
    return result


def occurrence(n):
    return n["elemento_id"], n["inicio_numero"], n["fin_numero"]


def no_unit_reason(n):
    if n["unit_source"] != "none":
        return None
    if n["tipo"] in {"año", "fecha", "artículo", "fracción", "folio", "numero_de_auditoria", "otro"}:
        return "referencia_identificador_o_tipo_no_resuelto"
    if "unidades_contradictorias" in n["motivos_ambiguedad"]:
        return "fuentes_contradictorias"
    if any(not c.get("applicable", True) for c in n.get("unit_candidates", [])):
        return "mencion_narrativa_sin_declaracion_de_unidad"
    return "sin_fuente_de_unidad_relacionada"


def exclusion_reason(n, peers):
    if n["confidence"] == "low":
        return "confianza_low: " + (", ".join(n["motivos_ambiguedad"]) or "sin_unidad")
    if n.get("is_table_header"):
        return "cifra_en_encabezado_o_rotulo"
    if not n.get("tabla"):
        return "confianza_medium_fuera_de_columna"
    reasons = []
    if any(p["confidence"] == "low" for p in peers):
        reasons.append("columna_con_registros_low")
    if any(p["tipo"] not in {"cantidad", "importe", "porcentaje"} for p in peers):
        reasons.append("columna_con_referencias_o_identificadores")
    if any(p["valor_decimal"] is None for p in peers):
        reasons.append("columna_con_valores_no_decimal")
    if any(not p["unidad_original"] for p in peers):
        reasons.append("columna_con_unidad_ausente")
    if len({(p.get("unidad_canonica"), p["multiplicador"], p["tipo"]) for p in peers}) > 1:
        reasons.append("columna_con_unidades_escalas_o_tipos_distintos")
    return "; ".join(reasons) or n.get("arithmetic_reason", n["reason"])


def main():
    before, after = documents(OUT / "before"), documents(CURRENT)
    assert before and before.keys() == after.keys(), "Se necesita el snapshot previo completo."
    tables, transitions, exclusions, rows_medium = [], [], [], []
    for filename, d in after.items():
        old = before[filename]
        index = {occurrence(n): n for n in d["cifras"]}
        peers = defaultdict(list)
        for n in old["cifras"]:
            if n["tabla"] and not n.get("is_table_header"):
                peers[n["tabla"], n["columna"]].append(n)
        for n in old["cifras"]:
            current = index.get(occurrence(n))
            assert current is not None, "Ocurrencia anterior no recuperada."
            if n["unit_source"] == "previous_paragraph" and old["included_in_aggregates"]:
                transitions.append({"documento": filename, "elemento_id": n["elemento_id"], "tabla": n["tabla"],
                                    "inicio_numero": n["inicio_numero"], "origen_anterior": n["unit_source"],
                                    "origen_actual": current["unit_source"], "confianza_actual": current["confidence"],
                                    "motivo": no_unit_reason(current) or current["reason"]})
            if n["unit_source"] == "row_header" and old["included_in_aggregates"]:
                rows_medium.append({"documento": filename, "elemento_id": n["elemento_id"], "tabla": n["tabla"],
                                    "unidad": n["unidad_original"], "antes": n["confidence"], "ahora": current["confidence"],
                                    "motivo_anterior": "La certeza usaba UNIT (dinero y porcentaje), no reconocía municipios; marcó unambiguous=false.",
                                    "motivo_actual": current["reason"]})
            if (old["included_in_aggregates"] and n["tipo"] in {"cantidad", "importe", "porcentaje"}
                    and n["confidence"] != "low" and not n["usable_for_arithmetic"]):
                exclusions.append({"documento": filename, "elemento_id": n["elemento_id"], "tipo": n["tipo"],
                                   "confianza": n["confidence"], "motivo_anterior": exclusion_reason(n, peers[n["tabla"], n["columna"]]),
                                   "arithmetic_actual": current["usable_for_arithmetic"], "confianza_actual": current["confidence"]})
        result = read_docx(INPUT / filename)
        contexts = defaultdict(list)
        for p, c in paragraph_contexts(result):
            if c.get("tabla"):
                contexts[c["tabla"]].append((p, c))
        grouped = defaultdict(list)
        for n in d["cifras"]:
            if n["tabla"]:
                grouped[n["tabla"]].append(n)
        for table in output_elements(result):
            if table["type"] != "table":
                continue
            tid = table["id"]
            nums = grouped[tid]
            headers, title_rows, internal = layout(table, "final")
            column_labels, row_labels, candidates, units = {}, {}, {}, []
            for row in headers:
                for c in row["cells"]:
                    column_labels[c["id"]] = {"id": c["id"], "fila": row["index"], "columna": c["grid_column"],
                                               "longitud": len(plain(c, "final")), "unidades": evidence(plain(c, "final"), "column_header", c["id"])}
            for p, c in contexts[tid]:
                label = c["_labels_by_view"]["final"]
                if label.get("encabezado_fila_id"):
                    row_labels[label["encabezado_fila_id"]] = {"id": label["encabezado_fila_id"], "fila": c["fila"],
                       "longitud": len(label["encabezado_fila"]), "unidades": evidence(label["encabezado_fila"], "row_header", label["encabezado_fila_id"])}
                for e in label["table_unit_candidates"]:
                    candidates[json.dumps(e, sort_keys=True)] = e
                units.extend(evidence(p["text"], "table_cell", p["id"]))
            tables.append({"documento": filename, "table_id": tid, "included_in_aggregates": d["included_in_aggregates"],
                "filas": len(table["rows"]), "columnas": max((c["grid_column"] + c["column_span"] - 1 for r in table["rows"] for c in r["cells"]), default=0),
                "celdas_numericas": len({n["celda_id"] for n in nums}), "registros": len(nums),
                "encabezados_columna": list(column_labels.values()), "encabezados_fila": list(row_labels.values()),
                "filas_rotulo": sorted(title_rows), "titulos_notas": [e for e in candidates.values() if e["source"] in {"table_title", "table_note"}],
                "expresiones_unidad_en_celdas": units, "fuentes_candidatas": list(candidates.values()),
                "unit_source_asignado": dict(Counter(n["unit_source"] for n in nums)),
                "motivos_sin_unidad": dict(Counter(no_unit_reason(n) for n in nums if n["unit_source"] == "none"))})
    old_nums = [n for d in before.values() if d["included_in_aggregates"] for n in d["cifras"]]
    new_nums = [n for d in after.values() if d["included_in_aggregates"] for n in d["cifras"]]
    stats = {"total_anterior": len(old_nums), "total_actual": len(new_nums),
             "origen_anterior": dict(Counter(n["unit_source"] for n in old_nums)),
             "origen_actual": dict(Counter(n["unit_source"] for n in new_nums)),
             "destino_717": dict(Counter(t["origen_actual"] for t in transitions)),
             "exclusiones_señaladas": dict(Counter(e["tipo"] for e in exclusions)),
             "clasificacion_auditoria": sum(n["tipo"] == "numero_de_auditoria" for n in new_nums)}
    export_json({"resumen": stats, "tablas": tables, "trazabilidad_717": transitions,
                 "row_header_medium_anterior": rows_medium, "exclusiones_114": exclusions}, OUT / "diagnostico.json")
    lines = ["# Auditoría focalizada del inventario", "",
        "Sólo diagnósticos de extracción y elegibilidad; no se suman ni comparan valores de las cifras. Los conteos excluyen la copia idéntica; el diagnóstico por tabla conserva los 14 archivos.", "",
        "## Causas verificadas", "",
        "Los 717 previous_paragraph provenían de menciones de pesos (495) o municipios (222) en párrafos anteriores; la regla aceptaba cualquier mención, sin exigir declaración de unidad. No todos constituían una relación válida con la tabla.", "",
        "Los encabezados sólo se buscaban en la primera fila o mediante tblHeader. Los rótulos fusionados dentro de tablas y los encabezados de filas posteriores quedaban fuera. La nueva banda inicial reconoce estos contenedores; los reportes indican IDs, longitudes y unidades, sin reproducir títulos ni encabezados completos.", "",
        "El único row_header correspondía a municipios. Su confianza medium derivaba de un error de cobertura de la expresión regular de certeza, limitada a unidades monetarias y porcentajes. Se evalúa ahora con el mismo catálogo de unidades y con relación de fila; el resultado individual aparece abajo.", "",
        "Ese registro pasa a low y unit_source=none: al recuperar el rótulo fusionado de la tabla se detectan pesos frente a municipios en la fila. Se conserva ambas evidencias, sin forzar una interpretación. No se detectaron notas de tabla con declaración de unidad aplicable; table_note=0 no se rellena por fallback.", "",
        "Prioridad: explicit > column_header > row_header > table_title > table_note > previous_paragraph > none. La prioridad no anula contradicciones: fuentes incompatibles producen low, sin normalización forzada. Las menciones narrativas rechazadas se conservan como evidencia no aplicable. Un encabezado breve debe aportar una única unidad y una relación de columna/fila; una nota o párrafo cercano conserva medium. Los títulos fusionados requieren una expresión de unidad separada, no basta la ubicación.", "",
        "numero_de_auditoria es una categoría independiente; conserva formato/valor originales, no es aritmética y sólo permite identifier_matching con contexto inequívoco. Un número aislado no recibe esa categoría.", "",
        "## Distribución de orígenes"]
    sources = ["explicit", "column_header", "row_header", "table_title", "table_note", "previous_paragraph", "none"]
    markdown_table(lines, ["Origen", "Antes", "Ahora", "Destino de los 717"], [[s, stats["origen_anterior"].get(s, 0), stats["origen_actual"].get(s, 0), stats["destino_717"].get(s, 0)] for s in sources])
    lines.extend(["", "## Registro row_header anterior"])
    markdown_table(lines, ["Documento", "elemento_id", "Unidad", "Antes", "Ahora"], [[r[k] for k in ("documento", "elemento_id", "unidad", "antes", "ahora")] for r in rows_medium])
    lines.extend(["", "## Las 57 cantidades, 56 importes y 1 porcentaje", "",
                  "Son registros high/medium excluidos de aritmética en el inventario anterior; no son el conjunto de exclusiones low. Los motivos combinados de cada columna se agrupan sin mostrar cifras ni texto. El JSON conserva la trazabilidad individual y su elegibilidad actual."])
    groups = Counter((e["tipo"], e["confianza"], e["motivo_anterior"]) for e in exclusions)
    markdown_table(lines, ["Tipo", "Confianza", "Motivo", "Registros"], [[*k, v] for k, v in sorted(groups.items())])
    lines.extend(["", "## Diagnóstico por tabla", "", "Los encabezados se cuentan por celda candidata, no por número. JSON incluye los IDs y las expresiones de unidad; las filas fusionadas sin declaración no justifican una unidad."])
    markdown_table(lines, ["Documento", "table_id", "Filas", "Columnas", "Celdas numéricas", "Enc. columna", "Enc. fila", "Títulos/notas con unidad", "Expresiones de unidad", "Origen asignado", "Sin herencia"],
        [[t["documento"], t["table_id"], t["filas"], t["columnas"], t["celdas_numericas"], len(t["encabezados_columna"]), len(t["encabezados_fila"]), len(t["titulos_notas"]), len(t["expresiones_unidad_en_celdas"]), t["unit_source_asignado"], t["motivos_sin_unidad"]] for t in tables])
    (OUT / "diagnostico.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=True))


if __name__ == "__main__":
    main()
