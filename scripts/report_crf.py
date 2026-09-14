"""Reporte técnico por lote; no exporta el texto completo ni modifica entradas."""

import hashlib
import json
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

from revisor_crf import read_docx


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "CRF-sinteticas"
OUTPUT = ROOT / "results" / "reporte_crf"
KINDS = {"paragraph": "parrafos", "table": "tablas", "row": "filas", "cell": "celdas"}
TAGS = {qn(f"w:{tag}"): kind for tag, kind in zip(("p", "tbl", "tr", "tc"), KINDS.values())}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk(blocks):
    for block in blocks:
        yield block
        yield from walk(block.get("blocks", []))
        for row in block.get("rows", []):
            yield row
            for cell in row["cells"]:
                yield cell
                yield from walk(cell["blocks"])


def location(element):
    return element["source"]["part"], element["source"]["xml_path"]


def counts(elements):
    counter = Counter(KINDS[e["type"]] for e in elements)
    return {kind: counter[kind] for kind in KINDS.values()}


def inspect_file(path):
    item = {"archivo": path.relative_to(INPUT).as_posix(), "abierto": False,
            "extraccion_completada": False, "errores_tecnicos": [], "advertencias_python": []}
    before = digest(path)
    stage = "apertura"
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            Document(path)
            item["abierto"] = True
            stage = "lectura"
            result = read_docx(path)
            item["extraccion_completada"] = True
            body = list(walk(result["blocks"]))
            all_elements = list(body)
            stories = []
            story_contents = {}
            for section in result["sections"]:
                for story in section["headers_and_footers"]:
                    elements = list(walk(story["blocks"]))
                    all_elements.extend(elements)
                    story_contents[story["id"]] = elements
                    referenced_elements = story_contents.get(story.get("content_ref"), elements)
                    stories.append({"id": story["id"], "tipo": story["kind"],
                                    "heredado": story["linked_to_previous"],
                                    "parte": story.get("part"), "content_ref": story.get("content_ref"),
                                    "conteos": counts(referenced_elements)})
            for story in result.get("supplementary_parts", []):
                all_elements.extend(walk(story["blocks"]))
            unique = {location(e): e for e in all_elements}
            elements = list(unique.values())
            item.update(conteos=counts(elements), conteos_cuerpo=counts(body),
                        conteos_representaciones_del_lector=counts(all_elements),
                        secciones=len(result["sections"]), encabezados_y_pies=stories,
                        titulos_identificados=[{"id": e["id"], "nivel": e["heading_level"],
                                               "texto": e["text"], "estilo": e["style"], "origen": e["source"]}
                                              for e in elements if e["type"] == "paragraph" and e["heading_level"] is not None],
                        elementos_vacios=[{"id": e["id"], "tipo": KINDS[e["type"]], "origen": e["source"]}
                                          for e in elements if not e["text"].strip()],
                        conteos_vacios=counts([e for e in elements if not e["text"].strip()]),
                        advertencias_lector=result["warnings"],
                        resumen_advertencias_lector=dict(Counter(w["element"] for w in result["warnings"])))
            # Contraste estructural independiente: también detecta elementos omitidos
            # dentro de cuadros de texto, revisiones y otras partes del paquete.
            stage = "inventario_xml"
            unprocessed = []
            inventory = Counter()
            with ZipFile(path) as package:
                for name in package.namelist():
                    if not name.startswith("word/") or not name.endswith(".xml"):
                        continue
                    root = etree.fromstring(package.read(name), parser=etree.XMLParser(resolve_entities=False, no_network=True))
                    for node in root.iter():
                        if node.tag not in TAGS:
                            continue
                        kind = TAGS[node.tag]
                        inventory[kind] += 1
                        xml_path = node.getroottree().getpath(node)
                        if ("/" + name, xml_path) not in unique:
                            unprocessed.append({"tipo": kind, "parte": "/" + name, "xml_path": xml_path})
            item["inventario_xml"] = {kind: inventory[kind] for kind in KINDS.values()}
            item["elementos_no_extraidos"] = unprocessed
            item["resumen_no_extraidos"] = dict(Counter(e["tipo"] for e in unprocessed))
        except Exception as exc:
            # Un fallo en un documento no detiene el resto del lote.
            item["errores_tecnicos"].append({"etapa": stage, "tipo": type(exc).__name__, "mensaje": str(exc)})
        finally:
            item["advertencias_python"] = [{"tipo": w.category.__name__, "mensaje": str(w.message)} for w in captured]
            after = digest(path)
            item.update(sha256_antes=before, sha256_despues=after, original_sin_cambios=before == after)
    return item


def main():
    files = sorted((p for p in INPUT.rglob("*") if p.is_file()), key=lambda p: p.as_posix().casefold())
    documents = [inspect_file(path) for path in files if path.suffix.lower() == ".docx"]
    excluded = [{"archivo": p.relative_to(INPUT).as_posix(), "motivo": "Formato distinto de DOCX; no se abrió ni se convirtió."}
                for p in files if p.suffix.lower() != ".docx"]
    report = {"fecha_utc": datetime.now(timezone.utc).isoformat(), "carpeta": INPUT.relative_to(ROOT).as_posix(),
              "criterios": [
                  "Solo diagnóstico técnico; no se evalúa la corrección del contenido.",
                  "Conteos recursivos, incluidas tablas anidadas, formas, celdas, encabezados, pies, notas y comentarios.",
                  "Totales únicos por parte y ruta XML: encabezados/pies heredados no duplican conteos.",
                  "Filas y celdas físicas del XML; las combinaciones no se expanden.",
                  "Vacío significa texto extraído vacío o compuesto de espacios; puede contener imágenes o campos.",
                  "Títulos identificados por nivel de esquema; no se infieren por apariencia o significado.",
                  "Encabezados y pies se enumeran por sección y variante; pueden estar vacíos o no activos.",
                  "No extraídos: párrafos/tablas/filas/celdas presentes en word/*.xml sin representación en el resultado; incluye partes fuera del alcance del lector.",
                  "Advertencias del lector se conservan tal como se emitieron y pueden repetirse por encabezados heredados.",
                  "No extraídos, advertencias y vacíos pueden solaparse; no son una suma de errores.",
              ], "documentos": documents, "archivos_excluidos": excluded}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "reporte.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Reporte técnico de lectura de CRF", "", f"Fecha UTC: {report['fecha_utc']}", ""]
    lines.extend(f"- {criterion}" for criterion in report["criterios"])
    lines.extend(["", "| Documento | Abierto | Párrafos | Tablas | Filas | Celdas | Títulos | Vacíos | No extraídos | Advertencias lector | Errores |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for item in documents:
        c = item.get("conteos", {})
        values = [item["archivo"], "Sí" if item["abierto"] else "No"]
        values += [str(c.get(kind, "—")) for kind in KINDS.values()]
        values += [str(len(item.get(key, []))) for key in ("titulos_identificados", "elementos_vacios", "elementos_no_extraidos", "advertencias_lector", "errores_tecnicos")]
        lines.append("| " + " | ".join(values) + " |")
        # No texto de párrafos ni encabezados en la terminal.
        print(json.dumps({"archivo": item["archivo"], "abierto": item["abierto"], "conteos": c,
                          "titulos": len(item.get("titulos_identificados", [])),
                          "vacios": item.get("conteos_vacios", {}), "no_extraidos": item.get("resumen_no_extraidos", {}),
                          "advertencias_lector": item.get("resumen_advertencias_lector", {}),
                          "advertencias_python": len(item["advertencias_python"]),
                          "errores": [{"etapa": e["etapa"], "tipo": e["tipo"]} for e in item["errores_tecnicos"]],
                          "original_sin_cambios": item["original_sin_cambios"]}, ensure_ascii=True))
    for item in documents:
        lines.extend(["", f"## {item['archivo']}", "",
                      f"Extracción completada: {item['extraccion_completada']}. Original sin cambios (SHA-256): {item['original_sin_cambios']}.",
                      f"Conteos del cuerpo: `{json.dumps(item.get('conteos_cuerpo', {}), ensure_ascii=False)}`.",
                      f"Vacíos por tipo: `{json.dumps(item.get('conteos_vacios', {}), ensure_ascii=False)}`.",
                      f"No extraídos por tipo: `{json.dumps(item.get('resumen_no_extraidos', {}), ensure_ascii=False)}`.",
                      f"Advertencias del lector por elemento: `{json.dumps(item.get('resumen_advertencias_lector', {}), ensure_ascii=False)}`.",
                      "", "Títulos identificados:", ""])
        for heading in item.get("titulos_identificados", []):
            title = " ".join(heading["texto"].split()).replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"- Nivel {heading['nivel']}, `{heading['id']}`: {title}")
        if not item.get("titulos_identificados"):
            lines.append("Ninguno detectado por nivel de esquema; no implica ausencia de títulos visuales.")
        lines.extend(["", "Encabezados y pies:", ""])
        for story in item.get("encabezados_y_pies", []):
            lines.append(f"- `{story['id']}`: parte `{story['parte']}`, heredado={story['heredado']}, conteos={story['conteos']}.")
        if not item.get("encabezados_y_pies"):
            lines.append("Ninguno registrado.")
        lines.extend(["", "Errores técnicos:", ""])
        lines.extend(f"- {e['etapa']}: {e['tipo']}: {e['mensaje']}" for e in item["errores_tecnicos"])
        if not item["errores_tecnicos"]:
            lines.append("Ninguno.")
        for warning in item["advertencias_python"]:
            lines.append(f"- Advertencia de biblioteca: {warning['tipo']}: {warning['mensaje']}")
    lines.extend(["", "## Archivos excluidos", ""])
    lines.extend(f"- {item['archivo']}: {item['motivo']}" for item in excluded)
    lines.extend(["", "El JSON adjunto contiene los identificadores y ubicaciones de elementos vacíos, no extraídos y advertencias; no contiene el texto completo de las CRF."])
    (OUTPUT / "reporte.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"docx": len(documents), "abiertos": sum(d["abierto"] for d in documents),
                      "extracciones_completadas": sum(d["extraccion_completada"] for d in documents),
                      "errores_tecnicos": sum(len(d["errores_tecnicos"]) for d in documents),
                      "originales_sin_cambios": all(d["original_sin_cambios"] for d in documents),
                      "archivos_excluidos": len(excluded)}))


if __name__ == "__main__":
    main()
