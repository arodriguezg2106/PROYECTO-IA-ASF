"""Recorrido del XML en orden, sin reconstruir el documento por páginas."""

import json
from decimal import Decimal
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from lxml import etree
from .revisions import MODES, included, revision_status


def _value(element, path, default=None):
    node = element.find(path)
    return node.get(qn("w:val"), default) if node is not None else default


def _style(style):
    return {"id": style.style_id, "name": style.name} if style is not None else None


def _heading_level(paragraph):
    level = _value(paragraph._p, "./" + qn("w:pPr") + "/" + qn("w:outlineLvl"))
    style = paragraph.style
    visited = set()
    while level is None and style is not None and style.style_id not in visited:
        visited.add(style.style_id)
        level = _value(style.element, "./" + qn("w:pPr") + "/" + qn("w:outlineLvl"))
        style = style.base_style
    return int(level) + 1 if level is not None and 0 <= int(level) <= 8 else None


_PROPERTIES = {qn(f"w:{name}") for name in (
    "pPr", "rPr", "tcPr", "trPr", "tblPr", "tblGrid", "sectPr", "sdtPr", "sdtEndPr")}
_REVISIONS = {qn(f"w:{name}") for name in ("ins", "del", "moveFrom", "moveTo")}


def _frontier(container, tags):
    """Descend through wrappers, stopping at the first structural element."""
    for child in container:
        if child.tag in tags:
            yield child
        elif child.tag not in _PROPERTIES:
            yield from _frontier(child, tags)


def _revisions(node):
    ancestors = list(reversed(list(node.iterancestors()))) + [node]
    result = []
    for a in ancestors:
        if a.tag in _REVISIONS:
            result.append({"type": etree.QName(a).localname, "id": a.get(qn("w:id"))})
        # Row/cell revision properties apply to their contents. Paragraph mark
        # deletion, in contrast, does not imply deletion of its entire text.
        property_tag = {qn("w:tr"): "trPr", qn("w:tc"): "tcPr"}.get(a.tag)
        if property_tag:
            props = a.find(qn("w:" + property_tag))
            if props is not None:
                for marker in props:
                    if marker.tag in _REVISIONS | {qn("w:cellIns"), qn("w:cellDel")}:
                        result.append({"type": etree.QName(marker).localname, "id": marker.get(qn("w:id"))})
    if node.tag in {qn("w:delText"), qn("w:delInstrText")} and not result:
        result.append({"type": "del", "id": None})
    return result


def _paragraph_content(element, revision_lookup=_revisions):
    """Own text only; embedded blocks are references, never copied into text."""
    content = []

    def visit(node):
        if node.tag in _PROPERTIES:
            return
        if node.tag in {qn("w:p"), qn("w:tbl")}:
            content.append({"type": "block", "xml_path": node.getroottree().getpath(node), "revisions": revision_lookup(node)})
            return
        value = None
        if node.tag in {qn("w:t"), qn("w:delText")}:
            value = node.text or ""
        elif node.tag == qn("w:tab"):
            value = "\t"
        elif node.tag in {qn("w:br"), qn("w:cr")}:
            value = "\n"
        elif node.tag == qn("w:noBreakHyphen"):
            value = "‑"
        elif node.tag == qn("w:softHyphen"):
            value = "\u00ad"
        if value is not None:
            content.append({"type": "text", "text": value, "revisions": revision_lookup(node)})
        elif node.tag in {qn("w:instrText"), qn("w:delInstrText")}:
            content.append({"type": "field_instruction", "instruction": node.text or "", "revisions": revision_lookup(node)})
        elif node.tag in {qn("w:footnoteReference"), qn("w:endnoteReference"), qn("w:commentReference"),
                          qn("w:commentRangeStart"), qn("w:commentRangeEnd")}:
            content.append({"type": "reference", "kind": etree.QName(node).localname,
                            "xml_id": node.get(qn("w:id")), "revisions": revision_lookup(node)})
        else:
            for child in node:
                visit(child)

    for child in element:
        visit(child)
    return content


class _Reader:
    def __init__(self, source, mode):
        self.source = source
        self.mode = mode
        self.warnings = []
        self._range_roots = set()
        self._range_revisions = {}

    def _prepare_ranges(self, root):
        if root in self._range_roots:
            return
        self._range_roots.add(root)
        starts = {qn(f"w:{kind}RangeStart"): kind for kind in ("moveFrom", "moveTo")}
        ends = {qn(f"w:{kind}RangeEnd"): kind for kind in ("moveFrom", "moveTo")}
        active = {}
        for node in root.iter():
            if node.tag in starts:
                kind = starts[node.tag]
                active[(kind, node.get(qn("w:id")))] = {"type": kind, "id": node.get(qn("w:id")), "source": "range"}
            elif node.tag in ends:
                active.pop((ends[node.tag], node.get(qn("w:id"))), None)
            if active:
                self._range_revisions[node] = list(active.values())

    def revisions(self, node):
        return _revisions(node) + self._range_revisions.get(node, [])

    def _base(self, element, kind, identifier, parent_id, part, context):
        return {
            "id": identifier,
            "type": kind,
            "parent_id": parent_id,
            "section_id": context["section_id"],
            "headings": [dict(h) for h in context["headings"]],
            "xml_containers": [etree.QName(a).localname for a in reversed(list(element.iterancestors()))],
            "revisions": self.revisions(element),
            "revision_status": revision_status(self.revisions(element)),
            "included": included(revision_status(self.revisions(element)), self.mode),
            "source": {
                "file": self.source,
                "part": part,
                "xml_path": element.getroottree().getpath(element),
            },
        }

    def blocks(self, container, parent, prefix, part, context, body=False):
        self._prepare_ranges(container.getroottree().getroot())
        blocks = []
        for special in _frontier(container, {qn("w:p"), qn("w:tbl"), qn("w:altChunk")}):
            if special.tag == qn("w:altChunk"):
                self.warnings.append({"part": part, "xml_path": special.getroottree().getpath(special),
                                      "element": "altChunk", "message": "Contenido externo incrustado no interpretado."})
        for child in _frontier(container, {qn("w:p"), qn("w:tbl")}):
            tag = etree.QName(child).localname
            identifier = f"{prefix}/b{len(blocks) + 1:04d}"
            if child.tag == qn("w:p"):
                paragraph = Paragraph(child, parent)
                content = _paragraph_content(child, self.revisions)
                offset = 0
                for index, fragment in enumerate(content, 1):
                    fragment["id"] = f"{identifier}/f{index:04d}"
                    fragment["revision_status"] = revision_status(fragment.get("revisions", []))
                    fragment["included"] = included(fragment["revision_status"], self.mode)
                    if fragment["type"] == "text":
                        fragment["source_start"] = offset
                        offset += len(fragment["text"])
                        fragment["source_end"] = offset
                paragraph_text = "".join(c["text"] for c in content if c["type"] == "text" and c["included"])
                text_all = "".join(c["text"] for c in content if c["type"] == "text")
                level = _heading_level(paragraph)
                if level is not None and paragraph_text.strip():
                    context["headings"] = [h for h in context["headings"] if h["level"] < level]
                    context["headings"].append({"id": identifier, "level": level, "text": paragraph_text})
                item = self._base(child, "paragraph", identifier, prefix, part, context)
                local_context = {"section_id": context["section_id"], "headings": list(context["headings"])}
                embedded = self.blocks(child, parent, identifier, part, local_context)
                block_ids = {b["source"]["xml_path"]: b["id"] for b in embedded}
                for fragment in content:
                    if fragment["type"] == "block":
                        fragment["id"] = block_ids[fragment.pop("xml_path")]
                item.update(text=paragraph_text, style=_style(paragraph.style), heading_level=level,
                            text_all=text_all, content=content, blocks=embedded)
                states = {c["revision_status"] for c in content if c["type"] == "text" and c["text"]}
                if states:
                    item["revision_status"] = next(iter(states)) if len(states) == 1 else "unknown"
                    item["revision_status_reason"] = "mixed_fragments" if len(states) > 1 else "uniform"
                    item["included"] = any(c["included"] for c in content if c["type"] == "text" and c["text"])
                blocks.append(item)
                for special in child.iter():
                    if next((a for a in special.iterancestors() if a.tag == qn("w:p")), None) is not child:
                        continue
                    if special.tag in {qn("w:drawing"), qn("w:pict"), qn("w:object"), qn("w:fldChar"), qn("w:fldSimple"), qn("w:altChunk"), qn("w:sym")}:
                        self.warnings.append({"id": identifier, "element": etree.QName(special).localname,
                                              "message": "Texto XML conservado cuando existe; no se evalúan campos, imágenes ni objetos."})
                if body and child.find("./" + qn("w:pPr") + "/" + qn("w:sectPr")) is not None:
                    context["section_id"] = f"section-{int(context['section_id'].split('-')[1]) + 1:04d}"
            elif child.tag == qn("w:tbl"):
                blocks.append(self.table(child, parent, identifier, prefix, part, context))
        return blocks

    def table(self, element, parent, identifier, parent_id, part, context):
        table = Table(element, parent)
        item = self._base(element, "table", identifier, parent_id, part, context)
        item.update(style=_style(table.style), rows=[])
        for row_index, row_xml in enumerate(_frontier(element, {qn("w:tr")}), 1):
            row_id = f"{identifier}/r{row_index:04d}"
            row = self._base(row_xml, "row", row_id, identifier, part, context)
            before = int(_value(row_xml, "./" + qn("w:trPr") + "/" + qn("w:gridBefore"), "0"))
            after = int(_value(row_xml, "./" + qn("w:trPr") + "/" + qn("w:gridAfter"), "0"))
            row.update(index=row_index, grid_before=before, grid_after=after, cells=[])
            header_marker = row_xml.find("./" + qn("w:trPr") + "/" + qn("w:tblHeader"))
            row["is_header"] = header_marker is not None and header_marker.get(qn("w:val"), "1") not in {"0", "false", "off"}
            column = before + 1
            for cell_index, cell_xml in enumerate(_frontier(row_xml, {qn("w:tc")}), 1):
                cell_id = f"{row_id}/c{cell_index:04d}"
                cell = self._base(cell_xml, "cell", cell_id, row_id, part, context)
                span = int(_value(cell_xml, "./" + qn("w:tcPr") + "/" + qn("w:gridSpan"), "1"))
                merge = cell_xml.find("./" + qn("w:tcPr") + "/" + qn("w:vMerge"))
                cell.update(index=cell_index, grid_column=column, column_span=span,
                            vertical_merge=None if merge is None else merge.get(qn("w:val"), "continue"))
                local_context = {"section_id": context["section_id"], "headings": list(context["headings"])}
                cell["blocks"] = self.blocks(cell_xml, _Cell(cell_xml, table), cell_id, part, local_context)
                cell["text"] = "\n".join(block["text"] for block in cell["blocks"])
                cell["text_all"] = "\n".join(block["text_all"] for block in cell["blocks"])
                row["cells"].append(cell)
                column += span
            row["text"] = "\t".join(cell["text"] for cell in row["cells"])
            row["text_all"] = "\t".join(cell["text_all"] for cell in row["cells"])
            item["rows"].append(row)
        item["text"] = "\n".join(row["text"] for row in item["rows"])
        item["text_all"] = "\n".join(row["text_all"] for row in item["rows"])
        return item


def read_docx(path, mode="final"):
    """Extrae cuerpo, secciones, encabezados y pies; no modifica la entrada."""
    if mode not in MODES:
        raise ValueError(f"Modo de lectura inválido: {mode}")
    source = Path(path)
    if source.suffix.lower() != ".docx":
        raise ValueError("La entrada debe tener extensión .docx.")
    if not source.is_file():
        raise FileNotFoundError(f"No existe el archivo: {source}")
    try:
        document = Document(source)
    except (PackageNotFoundError, BadZipFile, etree.XMLSyntaxError, KeyError) as exc:
        raise ValueError(f"DOCX inválido o dañado: {source.name}") from exc
    reader = _Reader(source.name, mode)
    context = {"section_id": "section-0001", "headings": []}
    result = {"schema_version": "1.2", "reading_mode": mode, "source": {"file": source.name},
              "blocks": reader.blocks(document.element.body, document, "body", "/word/document.xml", context, body=True),
              "sections": [], "supplementary_parts": [], "warnings": reader.warnings}
    story_definitions = {}
    for index, section in enumerate(document.sections, 1):
        section_id = f"section-{index:04d}"
        info = {"id": section_id, "start_type": section.start_type.name,
                "different_first_page": section.different_first_page_header_footer,
                "headers_and_footers": []}
        for name in ("header", "first_page_header", "even_page_header", "footer", "first_page_footer", "even_page_footer"):
            story = getattr(section, name)
            # Consultar la definición heredada sin crear partes ausentes en el DOCX.
            resolved = story
            while resolved is not None and not resolved._has_definition:
                resolved = resolved._prior_headerfooter
            if resolved is None:
                continue
            definition = resolved._definition
            story_id = f"{section_id}/{name}"
            partname = str(definition.partname)
            reference = story_definitions.get(partname)
            story_blocks = [] if reference else reader.blocks(
                definition.element, story, story_id, partname, {"section_id": section_id, "headings": []})
            story_definitions.setdefault(partname, story_id)
            info["headers_and_footers"].append({
                "id": story_id, "kind": name, "linked_to_previous": story.is_linked_to_previous,
                "part": partname, "content_ref": reference, "blocks": story_blocks,
            })
        result["sections"].append(info)
    result["even_and_odd_headers"] = document.settings.odd_and_even_pages_header_footer
    for part in sorted(document.part.package.parts, key=lambda p: str(p.partname)):
        if not str(part.partname).endswith(".xml"):
            continue
        if not any(part.content_type.endswith(f".{kind}+xml") for kind in ("comments", "footnotes", "endnotes")):
            continue
        root = parse_xml(part.blob)
        for index, container in enumerate(root, 1):
            kind = etree.QName(container).localname
            story_id = f"supplementary/{Path(str(part.partname)).stem}/{kind}-{index:04d}"
            result["supplementary_parts"].append({
                "id": story_id, "kind": kind, "xml_id": container.get(qn("w:id")),
                "note_type": container.get(qn("w:type")), "part": str(part.partname),
                "blocks": reader.blocks(container, document, story_id, str(part.partname),
                                        {"section_id": None, "headings": []}),
            })
    return result


def export_json(result, path):
    """Guarda JSON UTF-8 legible y crea el directorio de salida si hace falta."""
    target = Path(path)
    if target.suffix.lower() != ".json":
        raise ValueError("La salida debe tener extensión .json.")
    target.parent.mkdir(parents=True, exist_ok=True)
    def serialize(value):
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"Tipo no serializable: {type(value).__name__}")

    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=serialize) + "\n", encoding="utf-8")
