"""Resolución conservadora de formato OOXML efectivo."""
from __future__ import annotations
from dataclasses import dataclass
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import parse_xml
from docx.text.paragraph import Paragraph
from lxml import etree

@dataclass(frozen=True)
class EffectiveValue:
    value: object
    source: str

def _chain(style):
    seen=set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id); yield style; style=style.base_style

def effective(paragraph, group, attribute):
    if group=="font":
        explicit=[getattr(run.font,attribute,None) for run in paragraph.runs if run.text and getattr(run.font,attribute,None) is not None]
        direct=explicit[0] if explicit and all(value==explicit[0] for value in explicit) else None
    else:
        direct=getattr(getattr(paragraph,group),attribute,None)
    if direct is not None:return EffectiveValue(direct,"direct")
    for style in _chain(paragraph.style):
        value=getattr(getattr(style,group),attribute,None)
        if value is not None:return EffectiveValue(value,f"style:{style.style_id}")
    defaults=paragraph.part.document.styles.element.find(qn("w:docDefaults"))
    tag="rPrDefault" if group=="font" else "pPrDefault"
    props=defaults.find(qn("w:"+tag)) if defaults is not None else None
    props=next(iter(props),None) if props is not None else None
    if props is not None:
        paths={("font","name"):("rFonts","ascii"),("font","size"):("sz","val"),
          ("paragraph_format","alignment"):("jc","val"),("paragraph_format","line_spacing"):("spacing","line"),
          ("paragraph_format","space_before"):("spacing","before"),("paragraph_format","space_after"):("spacing","after"),
          ("paragraph_format","left_indent"):("ind","left"),("paragraph_format","right_indent"):("ind","right"),
          ("paragraph_format","first_line_indent"):("ind","firstLine")}
        spec=paths.get((group,attribute))
        if spec:
            node=props.find(qn("w:"+spec[0])); raw=node.get(qn("w:"+spec[1])) if node is not None else None
            if raw is not None:return EffectiveValue(raw,"docDefaults")
    return EffectiveValue(None,"unknown")

def _num(value, unit):
    if value is None:return None
    if hasattr(value,unit):return round(getattr(value,unit),3)
    try:return float(value)
    except (TypeError,ValueError):return None

def paragraph_format(paragraph):
    values={k:effective(paragraph,*spec) for k,spec in {
      "font_name":("font","name"),"font_size":("font","size"),"alignment":("paragraph_format","alignment"),
      "line_spacing":("paragraph_format","line_spacing"),"space_before":("paragraph_format","space_before"),
      "space_after":("paragraph_format","space_after"),"left_indent":("paragraph_format","left_indent"),
      "right_indent":("paragraph_format","right_indent"),
      "first_line_indent":("paragraph_format","first_line_indent")}.items()}
    normalized={}
    for key,item in values.items():
        value=item.value
        if item.source=="docDefaults" and value is not None:
            if key in {"font_size","space_before","space_after","left_indent",
                       "right_indent","first_line_indent","line_spacing"}:
                raw=_num(value,"pt")
                if raw is None:value=None
                elif key=="font_size":value=raw/2
                elif key in {"space_before","space_after"}:value=raw/20
                elif key in {"left_indent","right_indent","first_line_indent"}:value=raw/567
                elif key=="line_spacing":value=raw/240
            elif key=="alignment":value=str(value).upper()
        elif key in {"font_size","space_before","space_after"}:value=_num(value,"pt")
        elif key in {"left_indent","right_indent","first_line_indent"}:value=_num(value,"cm")
        elif key=="alignment" and value is not None:value=getattr(value,"name",str(value))
        elif key=="line_spacing" and value is not None:value=_num(value,"pt")
        normalized[key]={"value":value,"source":item.source}
    return normalized

def _walk_doc(container, parent):
    for child in container.iterchildren():
        if child.tag==qn("w:p"):yield Paragraph(child,parent), child
        elif child.tag==qn("w:tbl"):
            for p in child.iter(qn("w:p")):yield Paragraph(p,parent),p

def _border_values(borders, source):
    hits=[]; suppressed=[]
    if borders is None:return hits,suppressed
    for side in ("insideV","left","right","start","end"):
        node=borders.find(qn("w:"+side))
        if node is None:continue
        value=node.get(qn("w:val"),"single")
        item={"side":side,"value":value,"source":source}
        (suppressed if value in {"nil","none"} else hits).append(item)
    return hits,suppressed

def table_vertical_borders(table_xml, styles):
    hits=[]; suppressed=[]
    style_node=table_xml.find("./w:tblPr/w:tblStyle",namespaces=table_xml.nsmap)
    style_id=style_node.get(qn("w:val")) if style_node is not None else None
    seen=set()
    while style_id and style_id not in seen:
        seen.add(style_id); style=styles.get(style_id)
        if style is None:break
        borders=style.find("./w:tblPr/w:tblBorders",namespaces=style.nsmap)
        found,off=_border_values(borders,f"table_style:{style_id}"); hits.extend(found); suppressed.extend(off)
        based=style.find("./w:basedOn",namespaces=style.nsmap); style_id=based.get(qn("w:val")) if based is not None else None
    for owner in (table_xml,*table_xml.iter(qn("w:tc"))):
        props=owner.find(qn("w:tblPr")) if owner.tag==qn("w:tbl") else owner.find(qn("w:tcPr"))
        borders=props.find(qn("w:tblBorders")) if props is not None and owner.tag==qn("w:tbl") else props.find(qn("w:tcBorders")) if props is not None else None
        found,off=_border_values(borders,"table_direct" if owner.tag==qn("w:tbl") else "cell_direct")
        hits.extend(found); suppressed.extend(off)
    suppressed_sides={x["side"] for x in suppressed if x["source"] in {"table_direct","cell_direct"}}
    effective=[x for x in hits if x["side"] not in suppressed_sides]
    return effective,suppressed

def _has_decimal_tab(paragraph):
    if any(tab.alignment.name=="DECIMAL" for tab in paragraph.paragraph_format.tab_stops):return True,"direct"
    for style in _chain(paragraph.style):
        if any(tab.alignment.name=="DECIMAL" for tab in style.paragraph_format.tab_stops):return True,f"style:{style.style_id}"
    return False,"unknown"

def inspect_format(path):
    doc=Document(path); paragraphs=[]
    root=doc.element.body
    for index,(p,node) in enumerate(_walk_doc(root,doc),1):
        if p.text.strip():
          decimal_tab,decimal_tab_source=_has_decimal_tab(p); paragraphs.append({"index":index,"text":p.text,"style_id":p.style.style_id if p.style else None,
          "in_table":bool(list(node.iterancestors(qn("w:tc")))),"format":paragraph_format(p),"xml_path":node.getroottree().getpath(node),
          "has_decimal_tab":decimal_tab,"decimal_tab_source":decimal_tab_source})
    sections=[]
    for i,s in enumerate(doc.sections,1):
        sections.append({"index":i,"orientation":s.orientation.name,"width_inches":round(s.page_width.inches,3),"height_inches":round(s.page_height.inches,3),
          "margins_cm":{"top":round(s.top_margin.cm,3),"bottom":round(s.bottom_margin.cm,3),"inside":round(s.left_margin.cm,3),"outside":round(s.right_margin.cm,3),"gutter":round(s.gutter.cm,3)},
          "header_cm":round(s.header_distance.cm,3),"footer_cm":round(s.footer_distance.cm,3)})
    styles={node.get(qn("w:styleId")):node for node in doc.styles.element.findall(qn("w:style"))}
    tables=[]
    for i,t in enumerate(root.iter(qn("w:tbl")),1):
        effective_borders,suppressed_borders=table_vertical_borders(t,styles)
        tables.append({"index":i,"vertical_borders":effective_borders,"suppressed_vertical_borders":suppressed_borders})
    supplementary=[]
    for part in doc.part.package.parts:
        partname=str(part.partname)
        if not partname.endswith(("footnotes.xml","endnotes.xml")):continue
        root=parse_xml(part.blob)
        for index,node in enumerate(root.iter(qn("w:p")),1):
            paragraph=Paragraph(node,doc)
            if paragraph.text.strip():supplementary.append({"index":index,"text":paragraph.text,"style_id":paragraph.style.style_id if paragraph.style else None,
              "kind":"footnote" if partname.endswith("footnotes.xml") else "endnote","format":paragraph_format(paragraph),"part":partname,
              "xml_path":node.getroottree().getpath(node)})
    return {"sections":sections,"paragraphs":paragraphs,"tables":tables,"supplementary":supplementary}
