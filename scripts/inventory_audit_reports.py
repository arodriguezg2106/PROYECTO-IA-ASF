"""Cruces, identidad y cambios de política del inventario; sin texto completo."""

import json
from collections import Counter
from revisor_crf import export_json


def markdown_table(lines, headers, rows):
    lines.extend(["", "| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"])
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")


def generate_reports(output):
    all_documents = []
    for path in sorted(output.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "cifras" in data:
            all_documents.append(data)
    numbers = [n for d in all_documents if d["included_in_aggregates"] for n in d["cifras"]]
    dimensions = [("classification", "confidence"), ("classification", "usable_for_comparison"),
                  ("classification", "unit_source"), ("confidence", "unit_source"),
                  ("ubicacion", "classification"), ("ubicacion", "confidence"), ("tipo", "confidence")]
    dimensions += [("classification", k) for k in ("usable_for_arithmetic", "usable_for_cross_reference", "usable_for_temporal_analysis", "usable_for_identifier_matching")]
    dimensions += [(a, b) for a in ("confidence", "unit_source")
                   for b in ("usable_for_arithmetic", "usable_for_cross_reference")]
    lines = ["# Tablas cruzadas", "", "Sin copias idénticas. classification es la decisión operativa; tipo conserva la hipótesis léxica. usable_for_comparison es un indicador legado, sólo para trazabilidad histórica."]
    crosses = {}
    for a, b in dimensions:
        counts = Counter((str(("tabla" if n["tabla"] else "párrafo") if a == "ubicacion" else n[a]), str(n[b])) for n in numbers)
        crosses[a + " × " + b] = [{a: key[0], b: key[1], "registros": count} for key, count in sorted(counts.items())]
        lines.extend(["", "## " + a + " × " + b])
        markdown_table(lines, [a, b, "registros"], [[*key, count] for key, count in sorted(counts.items())])
    counts = Counter((n["classification"], "tabla" if n["tabla"] else "párrafo", n["unit_source"]) for n in numbers)
    name = "classification × ubicacion × unit_source"
    crosses[name] = [{"classification": k[0], "ubicacion": k[1], "unit_source": k[2], "registros": v} for k, v in sorted(counts.items())]
    lines.extend(["", "## " + name])
    markdown_table(lines, ["classification", "ubicacion", "unit_source", "registros"], [[*k, v] for k, v in sorted(counts.items())])
    export_json({"registros_sin_duplicados_documentales": len(numbers), "tablas": crosses}, output / "tablas_cruzadas.json")
    (output / "tablas_cruzadas.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    duplicate = json.loads((output / "documentos_duplicados.json").read_text(encoding="utf-8"))
    lines = ["# Identidad documental", "", duplicate["metodo"]]
    markdown_table(lines, ["Documento", "duplicate_group_id", "Representante", "En agregados"],
                   [[d[k] for k in ("documento_id", "duplicate_group_id", "canonical_document_id", "included_in_aggregates")] for d in duplicate["documentos"]])
    markdown_table(lines, ["Documento A", "Documento B", "SHA archivo igual", "Texto igual", "Secuencia igual", "Similitud %", "Idénticos"], [list(p.values()) for p in duplicate["pares"]])
    (output / "documentos_duplicados.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Keep policy changes separate from the historical 4579 -> 4681 comparison.
    from audit_inventory_history import OUTPUT, key
    history_path = OUTPUT / "diferencias_4579_4681.json"
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
        identities = {d["documento_id"]: d for d in duplicate["documentos"]}
        for change in history["diferencias"]:
            identity = identities[change["documento_id"]]
            change.update({k: identity[k] for k in ("duplicate_group_id", "included_in_aggregates")})
        history["adiciones_sin_copias_documentales"] = sum(c["cambio"] == "añadido" and c["included_in_aggregates"] for c in history["diferencias"])
        history["adiciones_en_copias_documentales"] = sum(c["cambio"] == "añadido" and not c["included_in_aggregates"] for c in history["diferencias"])
        export_json(history, history_path)
        md = OUTPUT / "diferencias_4579_4681.md"
        existing = md.read_text(encoding="utf-8").split("\n## Duplicados documentales")[0]
        md.write_text(existing + f"\n## Duplicados documentales\n\nLas 102 adiciones no repiten ubicaciones dentro de un documento. Tras excluir la copia documental idéntica, quedan {history['adiciones_sin_copias_documentales']} adiciones en representantes y {history['adiciones_en_copias_documentales']} en la copia conservada. No deben confundirse duplicados de extracción con archivos duplicados.\n", encoding="utf-8")
    changed = []
    for d in all_documents:
        old_path = OUTPUT / "snapshot_4681" / (d["source"]["file"][:-5] + ".json")
        if not old_path.exists():
            continue
        old = {key(n): n for n in json.loads(old_path.read_text(encoding="utf-8"))["cifras"]}
        for n in d["cifras"]:
            previous = old.get(key(n))
            if previous and any(previous.get(k) != n.get(k) for k in ("tipo", "classification", "confidence", "unidad_original", "multiplicador")):
                changed.append({"documento_id": d["source"]["file"], "elemento_id": n["elemento_id"],
                                "tipo_anterior": previous["tipo"], "tipo_actual": n["tipo"],
                                "confidence_anterior": previous["confidence"], "confidence_actual": n["confidence"],
                                "unit_source": n["unit_source"], "motivo": n["reason"]})
    export_json({"comparacion": "snapshot_4681 contra política actual, separada de las 102 fracciones", "cambios": changed}, output / "cambios_politica_actual.json")
    policy_lines = ["# Cambios de política posteriores al snapshot de 4681", "", "No confundir con las 102 adiciones históricas. Se registran cambios de tipo, clasificación operativa, confianza, unidad o escala."]
    markdown_table(policy_lines, ["Documento", "elemento_id", "Tipo anterior", "Tipo actual", "Confianza anterior", "Confianza actual", "Origen unidad", "Motivo"],
                   [list(c.values()) for c in changed])
    (output / "cambios_politica_actual.md").write_text("\n".join(policy_lines) + "\n", encoding="utf-8")
    current_delta, delta_totals = [], Counter()
    for d in all_documents:
        path = output.parent / "all" / (d["source"]["file"][:-5] + ".json")
        if not path.exists():
            continue
        historical = json.loads(path.read_text(encoding="utf-8"))
        old = {key(n): n for n in historical["cifras"] if "final" in n["vistas"]}
        new = {key(n): n for n in d["cifras"]}
        for status, keys in (("añadido", new.keys() - old.keys()), ("eliminado", old.keys() - new.keys()),
                             ("reclasificado", {k for k in old.keys() & new.keys() if (old[k]["tipo"], old[k].get("subtipo")) != (new[k]["tipo"], new[k].get("subtipo"))})):
            delta_totals[status] += len(keys)
            for k in sorted(keys):
                a, b = old.get(k), new.get(k)
                n = b or a
                current_delta.append({"documento_id": d["source"]["file"], "cambio": status, "elemento_id": n["elemento_id"],
                                      "tipo_anterior": a["tipo"] if a else None, "tipo_actual": b["tipo"] if b else None,
                                      "motivo": "Detección de fracción normativa romana." if status == "añadido" and n["tipo"] == "fracción" else
                                      "Herencia de unidad o filtrado conservador de encabezados; " + (b["reason"] if b else "ocurrencia no recuperada"),
                                      "origen": n["origen"], "offsets_text_all": n["offsets_text_all"]})
    export_json({"base": "Vista final reconstruida del all histórico de 4579", "actual": "Después de la política actual", "totales": dict(delta_totals), "diferencias": current_delta}, output / "diferencias_4579_actual.json")
    lines = ["# Diferencias 4579 → inventario después de la política actual", "", "El aumento histórico de 102 fracciones se distingue de las reclasificaciones adicionales introducidas ahora por la herencia de unidades y el filtrado de encabezados. Se incluyen las copias documentales para comparar el mismo lote de 14 archivos.", "", str(dict(delta_totals))]
    markdown_table(lines, ["Documento", "Cambio", "elemento_id", "Tipo anterior", "Tipo actual", "Motivo"],
                   [[c[k] for k in ("documento_id", "cambio", "elemento_id", "tipo_anterior", "tipo_actual", "motivo")] for c in current_delta])
    (output / "diferencias_4579_actual.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
