"""Estadísticas de formato XML sin incluir texto de los documentos."""

from collections import Counter
from zipfile import ZipFile

from docx.oxml.ns import qn
from lxml import etree


def val(node, path):
    found = node.find(path) if node is not None else None
    return found.get(qn("w:val"), "1") if found is not None else None


def path(*names):
    return "./" + "/".join(qn("w:" + n) for n in names)


def analyze_formats(filename):
    with ZipFile(filename) as package:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        styles = etree.fromstring(package.read("word/styles.xml"), parser)
        definitions = {s.get(qn("w:styleId")): s for s in styles.findall(qn("w:style"))}
        default_id = next((key for key, s in definitions.items()
                           if s.get(qn("w:type")) == "paragraph" and s.get(qn("w:default")) == "1"), "Normal")

        def chain(style_id):
            seen = set()
            result = []
            while style_id in definitions and style_id not in seen:
                seen.add(style_id)
                style = definitions[style_id]
                result.append(style)
                style_id = val(style, path("basedOn"))
            return list(reversed(result))

        def inherited(p, style_chain, property_name):
            result = val(styles, path("docDefaults", "pPrDefault", "pPr", property_name))
            for node in style_chain + [p]:
                value = val(node, path("pPr", property_name))
                if value is not None:
                    result = value
            return result

        def run_format(p, run, style_chain):
            size = val(styles, path("docDefaults", "rPrDefault", "rPr", "sz"))
            bold_value = val(styles, path("docDefaults", "rPrDefault", "rPr", "b"))
            bold = None if bold_value is None else bold_value not in {"0", "false", "off"}
            char_id = val(run, path("rPr", "rStyle")) if run is not None else None
            for style in style_chain + chain(char_id):
                size = val(style, path("rPr", "sz")) or size
                toggle = val(style, path("rPr", "b"))
                if toggle is not None and toggle not in {"0", "false", "off"}:
                    bold = not bool(bold)
            direct = run.find(qn("w:rPr")) if run is not None else p.find(path("pPr", "rPr"))
            size = val(direct, path("sz")) or size
            direct_bold = val(direct, path("b"))
            if direct_bold is not None:
                bold = direct_bold not in {"0", "false", "off"}
            return float(size) / 2 if size else "no_especificado", "no_especificada" if bold is None else str(bold).lower()

        combinations = Counter()
        usage = Counter()
        outline = Counter()
        direct_outline = Counter()
        for name in package.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            root = etree.fromstring(package.read(name), parser)
            for p in root.iter(qn("w:p")):
                style_id = val(p, path("pPr", "pStyle")) or default_id
                style_chain = chain(style_id)
                style_name = val(definitions.get(style_id), path("name")) or style_id
                usage[(style_id, style_name)] += 1
                outline[inherited(p, style_chain, "outlineLvl") or "ausente"] += 1
                direct_outline[val(p, path("pPr", "outlineLvl")) or "ausente"] += 1
                alignment = inherited(p, style_chain, "jc") or "no_especificada"
                runs = [r for r in p.iter(qn("w:r"))
                        if next((a for a in r.iterancestors() if a.tag == qn("w:p")), None) is p
                        and any((t.text or "").strip() for t in r.iter() if t.tag in {qn("w:t"), qn("w:delText")} )]
                formats = [run_format(p, r, style_chain) for r in runs] or [run_format(p, None, style_chain)]
                sizes = tuple(sorted({f[0] for f in formats}, key=str))
                bolds = tuple(sorted({f[1] for f in formats}))
                combinations[(style_id, style_name, sizes, bolds, alignment)] += 1
        return {
            "niveles_esquema_directos": dict(direct_outline), "niveles_esquema_resueltos": dict(outline),
            "estilos_con_nivel_definido": [{"id": key, "nombre": val(style, path("name")),
                                            "nivel_xml": val(style, path("pPr", "outlineLvl"))}
                                           for key, style in definitions.items() if val(style, path("pPr", "outlineLvl")) is not None],
            "estilos": [{"id": key[0], "nombre": key[1], "frecuencia": n} for key, n in usage.most_common()],
            "combinaciones": [{"estilo_id": key[0], "nombre_estilo": key[1], "tamanos_pt": list(key[2]),
                                "negritas": list(key[3]), "alineacion": key[4], "frecuencia": n}
                               for key, n in combinations.most_common()],
        }
