"""Inventario por documento y verificación de cobertura, sin volcar las CRF."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from revisor_crf import read_docx, export_json
from revisor_crf.numbers import extract_numbers
from revisor_crf.duplicates import analyze_duplicates
from audit_crf import INPUT, ROOT, inventory, output_elements, structure_check


def cell(value):
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def main():
    parser = argparse.ArgumentParser(description="Inventario numérico por lote sin evaluación de cifras")
    parser.add_argument("--mode", choices=("final", "original", "all"), default="final")
    args = parser.parse_args()
    output = ROOT / "results" / "inventario_cifras" / args.mode
    output.mkdir(parents=True, exist_ok=True)
    duplicates = analyze_duplicates(list(INPUT.glob("*.docx")))
    identity = {d["documento_id"]: d for d in duplicates["documentos"]}
    export_json(duplicates, output / "documentos_duplicados.json")
    summary = []
    for path in sorted(INPUT.glob("*.docx")):
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        entry = {"documento": path.name, "modo": args.mode, "errores_tecnicos": []}
        entry.update({k: identity[path.name][k] for k in ("duplicate_group_id", "canonical_document_id", "included_in_aggregates")})
        try:
            result = read_docx(path, mode=args.mode)
            numbers = extract_numbers(result)
            numbers.update({k: identity[path.name][k] for k in ("duplicate_group_id", "canonical_document_id", "included_in_aggregates")})
            # All original XML evidence must survive even in final/original mode.
            elements = list(output_elements(result))
            paragraphs = [e for e in elements if e["type"] == "paragraph"]
            found = {(p["source"]["part"], p["source"]["xml_path"]): p for p in paragraphs}
            xml = inventory(path)
            retained = [p for p in xml if (p["parte"], p["ruta_xml"]) in found and
                        hashlib.sha256(found[(p["parte"], p["ruta_xml"])]["text_all"].encode()).hexdigest() == p["sha256_texto"]]
            with_text = [p for p in xml if p["con_texto"]]
            complete = sum(p["con_texto"] for p in retained)
            checks = structure_check(path, elements)
            entry.update(numbers["resumen"], parrafos_xml=len(xml), parrafos_con_texto=len(with_text),
                         parrafos_evidencia_completa=len(retained),
                         cobertura_xml_texto=100 * complete / len(with_text) if with_text else 100,
                         duplicados=len(checks["duplicados_elementos"]),
                         errores_orden_origen=len(checks["errores_orden_origen"]),
                         fragmentos_excluidos=sum(not f["included"] for p in paragraphs for f in p["content"] if f["type"] == "text"),
                         advertencias_lector=dict(Counter(w["element"] for w in result["warnings"])))
            numbers["verificacion_lector"] = {k: v for k, v in entry.items() if k not in {"clasificacion", "revision_status"}}
            export_json(numbers, output / (path.stem + ".json"))
            lines = [f"# Inventario numérico: {path.name}", "", f"Modo: `{args.mode}`. No se evalúa la corrección ni se comparan cifras.", "",
                     "Los importes y multiplicadores se serializan como cadenas decimales exactas. Los porcentajes se conservan en puntos porcentuales. Fechas e identificadores pueden no tener valor decimal o normalizado.", "",
                     "Contexto limitado a 150 caracteres; encabezados candidatos a 80. Unidades heredadas de rótulos y encabezados se identifican en el JSON. Las clasificaciones ambiguas requieren interpretación posterior.", "",
                     "| ID | Fragmento numérico | Valor decimal | Tipo | Unidad | Multiplicador | Normalizado | Estado | Sección | Tabla/fila/columna | Ambigüedad |",
                     "|---|---|---|---|---|---|---|---|---|---|---|"]
            for n in numbers["cifras"]:
                location = f"{n['tabla']} / {n['fila']} / {n['columna']}" if n["tabla"] else n["elemento_id"]
                row = [n["id"], n["texto_original"], n["valor_decimal"], n["tipo"], n["unidad_original"],
                       n["multiplicador"], n["valor_normalizado"], n["revision_status"], n["seccion"],
                       location, ", ".join(n["motivos_ambiguedad"])]
                lines.append("| " + " | ".join(cell(v) for v in row) + " |")
            lines.extend(["", "## Cifras ambiguas", "", ", ".join(n["id"] for n in numbers["cifras"] if n["ambigua"]) or "Ninguna.",
                          "", "## Cifras no clasificadas", "", ", ".join(n["id"] for n in numbers["cifras"] if n["no_clasificada"]) or "Ninguna.",
                          "", "El JSON del mismo nombre incluye contexto acotado, encabezados de fila/columna, offsets, origen XML y vistas de revisión."])
            (output / (path.stem + ".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as exc:
            entry["errores_tecnicos"].append({"tipo": type(exc).__name__})
        entry["original_sin_cambios"] = before == hashlib.sha256(path.read_bytes()).hexdigest()
        entry["sha256_original"] = before
        summary.append(entry)
        print(json.dumps({k: v for k, v in entry.items() if k != "sha256_original"}, ensure_ascii=True))
    export_json({"modo": args.mode, "documentos": summary}, output / "resumen.json")
    lines = ["# Resumen del inventario numérico", "", f"Modo: `{args.mode}`. Clasificación y normalización, sin revisión de cifras.", "",
             "La cobertura corresponde a la evidencia XML conservada en text_all, no al texto filtrado para análisis. Los originales se verifican con SHA-256.", "",
             "| Documento | Detectadas | Ambiguas | No clasificadas | Cobertura XML % | Duplicados | Errores técnicos |",
             "|---|---|---|---|---|---|---|"]
    for e in summary:
        lines.append("| " + " | ".join(cell(v) for v in [e["documento"], e.get("detectadas"), e.get("ambiguas"),
                      e.get("no_clasificadas"), e.get("cobertura_xml_texto"), e.get("duplicados"), len(e["errores_tecnicos"])]) + " |")
    (output / "resumen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    confidence_counts = Counter()
    types = Counter()
    origins = Counter()
    included_summary = [e for e in summary if e["included_in_aggregates"]]
    for entry in included_summary:
        confidence_counts.update(entry.get("confidence", {}))
        types.update(entry.get("clasificacion", {}))
        origins.update(entry.get("origen_unidad", {}))
    coverage = {"modo": args.mode, "total_cifras": sum(e.get("detectadas", 0) for e in included_summary),
                "total_cifras_sin_deduplicar": sum(e.get("detectadas", 0) for e in summary),
                "documentos_incluidos": len(included_summary), "copias_excluidas": len(summary) - len(included_summary),
                "confidence": {k: confidence_counts[k] for k in ("high", "medium", "low")},
                "utilizables": sum(e.get("utilizables", 0) for e in included_summary),
                "excluidas": sum(e.get("excluidas", 0) for e in included_summary),
                "eligibilidad": {k: sum(e.get("eligibilidad", {}).get(k, 0) for e in included_summary) for k in ("usable_for_arithmetic", "usable_for_cross_reference", "usable_for_temporal_analysis", "usable_for_identifier_matching")},
                "por_tipo": dict(types), "por_origen_unidad": dict(origins), "documentos": summary}
    export_json(coverage, output / "cobertura_confianza.json")
    lines = ["# Cobertura y confianza del inventario", "", f"Modo: {args.mode}.", "",
             f"Total de cifras: {coverage['total_cifras']}. Utilizables: {coverage['utilizables']}. Excluidas: {coverage['excluidas']}.", "",
             f"Documentos incluidos en agregados: {len(included_summary)}. Copias idénticas excluidas: {len(summary) - len(included_summary)}; se conservan sus reportes individuales.", "",
             "Utilizables/excluidas se refieren a elegibilidad aritmética. Los cuatro indicadores son independientes, no garantizan congruencia. No se comparan ni suman cifras.", "",
             "Los conteos por tipo conservan el tipo candidato; los registros ambiguos tienen classification=ambiguous, confidence=low y usable_for_comparison=false.", "",
             "| Distribución | Categoría | Registros |", "|---|---|---|"]
    for dimension, counts in (("confianza", coverage["confidence"]), ("tipo candidato", types), ("origen unidad", origins)):
        for key, count in sorted(counts.items()):
            lines.append(f"| {dimension} | {key} | {count} |")
    for key, count in coverage["eligibilidad"].items():
        lines.append(f"| elegibilidad | {key} | {count} |")
    lines.extend(["", "| Documento | High | Medium | Low | Utilizables | Excluidas | Cobertura XML % | Errores |", "|---|---|---|---|---|---|---|---|"])
    for e in summary:
        values = [e["documento"], *[e.get("confidence", {}).get(k, 0) for k in ("high", "medium", "low")],
                  e.get("utilizables"), e.get("excluidas"), e.get("cobertura_xml_texto"), len(e["errores_tecnicos"])]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines.extend(["", "La cobertura XML utiliza text_all y hashes, y no confunde exclusión por confianza o revisión con pérdida de párrafos. Los detalles de integridad y duplicados están en cobertura_confianza.json."])
    (output / "cobertura_confianza.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    from inventory_audit_reports import generate_reports
    generate_reports(output)


if __name__ == "__main__":
    main()
