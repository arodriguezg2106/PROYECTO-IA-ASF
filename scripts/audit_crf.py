"""Auditoría sin contenido textual: inventario XML, cobertura y formato."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

from revisor_crf import read_docx
from format_stats import analyze_formats

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "CRF-sinteticas"
OUT = ROOT / "results" / "auditoria_crf"


def own_nodes(paragraph):
    for node in paragraph.iterdescendants():
        ancestors = list(node.iterancestors())
        if any(a.tag in {qn("w:pPr"), qn("w:rPr"), qn("w:sdtPr")} for a in ancestors):
            continue
        if next((a for a in ancestors if a.tag == qn("w:p")), None) is paragraph:
            yield node


def xml_text(paragraph):
    parts = []
    for node in own_nodes(paragraph):
        if node.tag in {qn("w:t"), qn("w:delText")}:
            parts.append(node.text or "")
        elif node.tag == qn("w:tab"):
            parts.append("\t")
        elif node.tag in {qn("w:br"), qn("w:cr")}:
            parts.append("\n")
        elif node.tag == qn("w:noBreakHyphen"):
            parts.append("‑")
        elif node.tag == qn("w:softHyphen"):
            parts.append("\u00ad")
    return "".join(parts)


def walk(blocks):
    for block in blocks:
        yield block
        yield from walk(block.get("blocks", []))
        for row in block.get("rows", []):
            yield row
            for cell in row["cells"]:
                yield cell
                yield from walk(cell["blocks"])


def output_elements(result):
    yield from walk(result["blocks"])
    for section in result["sections"]:
        for story in section["headers_and_footers"]:
            yield from walk(story["blocks"])
    for story in result.get("supplementary_parts", []):
        yield from walk(story["blocks"])


def local(node):
    return etree.QName(node).localname


def classify(p):
    ancestors = [a for a in p.iterancestors()]
    tags = [local(a) for a in ancestors]
    categories = []
    if "sdtContent" in tags:
        categories.append("control_contenido")
    if any(t in tags for t in ("txbxContent", "textbox", "shape", "wsp")):
        categories.append("cuadro_texto_o_forma")
    if any(t in tags for t in ("ins", "del", "moveFrom", "moveTo")):
        categories.append("cambios_controlados")
    if tags.count("tbl") > 1:
        categories.append("tabla_anidada")
    if not categories:
        categories.append("otros_contenedores")
    return categories, "/".join(reversed(tags))


def inventory(path):
    entries = []
    with ZipFile(path) as package:
        for name in package.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            root = etree.fromstring(package.read(name), etree.XMLParser(resolve_entities=False, no_network=True))
            for p in root.iter(qn("w:p")):
                text = xml_text(p)
                categories, container = classify(p)
                own = list(own_nodes(p))
                entries.append({"parte": "/" + name, "ruta_xml": p.getroottree().getpath(p),
                                "categorias": categories, "contenedor": container,
                                "con_texto": bool(text.strip()), "longitud_texto": len(text),
                                "sha256_texto": hashlib.sha256(text.encode()).hexdigest(),
                                "instrucciones_campo_longitud": sum(len(n.text or "") for n in own if n.tag == qn("w:instrText")),
                                "elementos_internos": dict(Counter(local(n) for n in own if n.tag in {
                                    qn("w:ins"), qn("w:del"), qn("w:moveFrom"), qn("w:moveTo"),
                                    qn("w:sdt"), qn("w:fldSimple"), qn("w:fldChar"), qn("w:hyperlink"),
                                    qn("w:separator"), qn("w:continuationSeparator")})),
                                "tipo_nota": next((a.get(qn("w:type")) for a in p.iterancestors()
                                                   if a.tag in {qn("w:footnote"), qn("w:endnote")}), None)})
    return entries


def structure_check(filename, elements):
    locations = Counter((e["source"]["part"], e["source"]["xml_path"]) for e in elements)
    issues = []
    with ZipFile(filename) as package:
        for name in package.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            root = etree.fromstring(package.read(name), etree.XMLParser(resolve_entities=False, no_network=True))
            ranks = {n.getroottree().getpath(n): i for i, n in enumerate(root.iter()) if n.tag in {
                qn("w:p"), qn("w:tbl"), qn("w:tr"), qn("w:tc")}}
            output_paths = [e["source"]["xml_path"] for e in elements if e["source"]["part"] == "/" + name]
            positions = [ranks[p] for p in output_paths if p in ranks]
            if positions != sorted(positions):
                issues.append({"parte": "/" + name, "tipo": "orden_xml"})
            for p in output_paths:
                if p not in ranks:
                    issues.append({"parte": "/" + name, "ruta_xml": p, "tipo": "origen_no_encontrado"})
    return {"duplicados_elementos": [{"parte": key[0], "ruta_xml": key[1], "repeticiones": n}
                                      for key, n in locations.items() if n > 1], "errores_orden_origen": issues}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("antes", "despues"))
    args = parser.parse_args()
    if args.phase == "antes" and (OUT / "antes.json").exists():
        parser.error("La línea base ya existe; se conserva para la comparación histórica.")
    documents = []
    for path in sorted(INPUT.glob("*.docx")):
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        data = {"archivo": path.name, "errores": []}
        try:
            entries = inventory(path)
            result = read_docx(path, mode="all")
            elements = list(output_elements(result))
            paragraphs = [e for e in elements if e["type"] == "paragraph"]
            found = {}
            for e in paragraphs:
                found.setdefault((e["source"]["part"], e["source"]["xml_path"]), []).append(e)
            for p in entries:
                matches = found.get((p["parte"], p["ruta_xml"]), [])
                p["ids_extraidos"] = [e["id"] for e in matches]
                p["extraido"] = bool(matches)
                p["texto_completo"] = bool(matches) and all(hashlib.sha256(e["text"].encode()).hexdigest() == p["sha256_texto"] for e in matches)
            missing = [p for p in entries if not p["extraido"]]
            text_entries = [p for p in entries if p["con_texto"]]
            complete = sum(p["texto_completo"] for p in text_entries)
            data.update(parrafos=entries, total_xml=len(entries), con_texto=len(text_entries),
                        extraidos=len(found), con_texto_no_extraidos=sum(p["con_texto"] for p in missing),
                        texto_parcial=sum(p["extraido"] and not p["texto_completo"] for p in text_entries),
                        cobertura_texto=100 * complete / len(text_entries) if text_entries else 100,
                        no_extraidos=len(missing), vacios_no_extraidos=sum(not p["con_texto"] for p in missing),
                        contenedores_no_extraidos=dict(Counter(p["contenedor"] for p in missing)),
                        duplicados_ubicacion=[{"parte": key[0], "ruta_xml": key[1], "ids": [e["id"] for e in values]}
                                              for key, values in found.items() if len(values) > 1],
                        ids_duplicados=[key for key, n in Counter(e["id"] for e in elements).items() if n > 1],
                        advertencias_lector=dict(Counter(w["element"] for w in result["warnings"])))
            data["formatos"] = analyze_formats(path)
            data.update(structure_check(path, elements))
        except Exception as exc:
            data["errores"].append({"tipo": type(exc).__name__})
        data["sha256_original"] = before
        data["original_sin_cambios"] = before == hashlib.sha256(path.read_bytes()).hexdigest()
        documents.append(data)
        print(json.dumps({k: v for k, v in data.items() if k not in {"parrafos", "formatos", "sha256_original", "duplicados_ubicacion", "ids_duplicados"}}, ensure_ascii=True))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.phase}.json").write_text(json.dumps({"documentos": documents}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
