"""Genera una copia DOCX con comentarios de revisión sin tocar el original."""

from __future__ import annotations

import hashlib
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL = R + "/comments"
COMMENTS_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"


def _q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _value(value) -> str:
    if value is None:
        return "no disponible"
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _comment_lines(alert: dict) -> list[str]:
    operation = alert.get("operation", {})
    location = alert.get("where_to_review", {})
    origin = "híbrido" if alert.get("origin") == "hybrid" else "determinístico"
    lines = [
        f"IA-ASF · Posible hallazgo {origin} ({alert['id']})",
        alert["message"],
        f"Dónde revisar: {location.get('ruta') or 'consulte la evidencia del reporte'}",
    ]
    if alert.get("semantic"):
        lines.append(
            f"Relación semántica: caso {alert['semantic'].get('case_id')}; "
            f"confianza {alert['semantic'].get('confidence')}."
        )
    if operation.get("type") not in {"manual_review", "not_evaluable"}:
        lines.append(
            "Valores: declarado {declared}; calculado/relacionado {calculated}; diferencia {difference}; "
            "unidad {unit}; escala {scale}.".format(
                declared=_value(operation.get("declarado")),
                calculated=_value(operation.get("calculado")),
                difference=_value(operation.get("diferencia")),
                unit=_value(operation.get("unidad")),
                scale=_value(operation.get("escala")),
            )
        )
    if alert.get("not_evaluable_reason"):
        lines.append(f"Motivo de no evaluación: {alert['not_evaluable_reason']}")
    lines.append(f"Acción sugerida: {alert.get('review_instruction', 'Revisar la evidencia antes de decidir.')}")
    lines.append("Este comentario no modifica ni corrige automáticamente el contenido del CRF.")
    return lines


def _comment_element(comment_id: int, alerts: list[dict], author: str) -> etree._Element:
    comment = etree.Element(_q(W, "comment"))
    comment.set(_q(W, "id"), str(comment_id))
    comment.set(_q(W, "author"), author)
    comment.set(_q(W, "initials"), "IA")
    comment.set(_q(W, "date"), datetime.now(timezone.utc).isoformat())
    lines = []
    for index, alert in enumerate(alerts):
        if index:
            lines.append("—")
        lines.extend(_comment_lines(alert))
    for line in lines:
        paragraph = etree.SubElement(comment, _q(W, "p"))
        run = etree.SubElement(paragraph, _q(W, "r"))
        text = etree.SubElement(run, _q(W, "t"))
        text.text = line
    return comment


def _anchor(paragraph: etree._Element, comment_id: int) -> None:
    start = etree.Element(_q(W, "commentRangeStart"))
    start.set(_q(W, "id"), str(comment_id))
    position = 1 if len(paragraph) and paragraph[0].tag == _q(W, "pPr") else 0
    paragraph.insert(position, start)
    end = etree.SubElement(paragraph, _q(W, "commentRangeEnd"))
    end.set(_q(W, "id"), str(comment_id))
    reference_run = etree.SubElement(paragraph, _q(W, "r"))
    properties = etree.SubElement(reference_run, _q(W, "rPr"))
    style = etree.SubElement(properties, _q(W, "rStyle"))
    style.set(_q(W, "val"), "CommentReference")
    reference = etree.SubElement(reference_run, _q(W, "commentReference"))
    reference.set(_q(W, "id"), str(comment_id))


def _ensure_relationships(data: bytes) -> bytes:
    root = etree.fromstring(data)
    if not any(rel.get("Type") == COMMENTS_REL for rel in root):
        used = {rel.get("Id") for rel in root}
        number = 1
        while f"rId{number}" in used:
            number += 1
        rel = etree.SubElement(root, _q(PR, "Relationship"))
        rel.set("Id", f"rId{number}")
        rel.set("Type", COMMENTS_REL)
        rel.set("Target", "comments.xml")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _ensure_content_type(data: bytes) -> bytes:
    root = etree.fromstring(data)
    if not any(item.get("PartName") == "/word/comments.xml" for item in root):
        override = etree.SubElement(root, _q(CT, "Override"))
        override.set("PartName", "/word/comments.xml")
        override.set("ContentType", COMMENTS_TYPE)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _target_groups(report: dict) -> tuple[dict[str, list[dict]], list[str]]:
    groups = defaultdict(list)
    skipped = []
    for alert in report.get("alerts", []):
        if alert.get("operation", {}).get("type") == "not_evaluable":
            continue
        origin = (alert.get("evidence") or [{}])[0].get("ubicacion", {}).get("origen") or {}
        if origin.get("part") != "/word/document.xml" or not origin.get("xml_path"):
            skipped.append(alert["id"])
            continue
        groups[origin["xml_path"]].append(alert)
    return groups, skipped


def export_commented_docx(source_path: str | Path, report: dict, output_path: str | Path,
                          author: str = "IA-ASF") -> dict:
    """Copia el DOCX y agrega comentarios agrupados en los párrafos de evidencia."""
    source, target = Path(source_path), Path(output_path)
    if target.suffix.lower() != ".docx":
        raise ValueError("La copia comentada debe tener extensión .docx.")
    if source.resolve() == target.resolve():
        raise ValueError("La copia comentada no puede sobrescribir el DOCX original.")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if report.get("source", {}).get("sha256") != original_hash:
        raise ValueError("El reporte no corresponde al DOCX de entrada.")
    groups, skipped = _target_groups(report)
    if not groups:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return {
            "file": target.name,
            "comments_added": 0,
            "alerts_anchored": 0,
            "alerts_skipped": skipped,
            "structural_verification": {"valid": True, "not_applicable": True},
        }
    with ZipFile(source) as archive:
        contents = {info.filename: archive.read(info.filename) for info in archive.infolist()}
        infos = {info.filename: info for info in archive.infolist()}
    document = etree.fromstring(contents["word/document.xml"])
    if "word/comments.xml" in contents:
        comments = etree.fromstring(contents["word/comments.xml"])
    else:
        comments = etree.Element(_q(W, "comments"), nsmap={"w": W})
    existing_ids = [int(value) for value in comments.xpath("//w:comment/@w:id", namespaces={"w": W})
                    if str(value).lstrip("-").isdigit()]
    next_id = max(existing_ids, default=-1) + 1
    added, missing = [], []
    namespaces = {key: value for key, value in document.nsmap.items() if key}
    for xpath, alerts in groups.items():
        matches = document.xpath(xpath, namespaces=namespaces)
        paragraphs = [node for node in matches if node.tag == _q(W, "p")]
        if len(paragraphs) != 1:
            missing.extend(alert["id"] for alert in alerts)
            continue
        comment_id = next_id
        next_id += 1
        _anchor(paragraphs[0], comment_id)
        comments.append(_comment_element(comment_id, alerts, author))
        added.append({"comment_id": comment_id, "alert_ids": [alert["id"] for alert in alerts], "xml_path": xpath})
    contents["word/document.xml"] = etree.tostring(
        document, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    contents["word/comments.xml"] = etree.tostring(
        comments, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    contents["word/_rels/document.xml.rels"] = _ensure_relationships(
        contents["word/_rels/document.xml.rels"]
    )
    contents["[Content_Types].xml"] = _ensure_content_type(contents["[Content_Types].xml"])
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w", ZIP_DEFLATED) as output:
        for name, data in contents.items():
            if name in infos:
                output.writestr(infos[name], data)
            else:
                output.writestr(name, data)
    if hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
        raise RuntimeError("El DOCX original cambió al generar la copia comentada.")
    verification = verify_commented_docx(target, {item["comment_id"] for item in added})
    return {
        "file": target.name,
        "comments_added": len(added),
        "alerts_anchored": sum(len(item["alert_ids"]) for item in added),
        "alerts_skipped": [*skipped, *missing],
        "structural_verification": verification,
    }


def verify_commented_docx(path: str | Path, expected_ids: set[int] | None = None) -> dict:
    """Comprueba comments.xml, relación, tipo de contenido y las tres anclas."""
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        required = {"word/comments.xml", "word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"}
        if not required <= names:
            raise ValueError("La copia comentada no contiene todas las partes requeridas.")
        comments = etree.fromstring(archive.read("word/comments.xml"))
        document = etree.fromstring(archive.read("word/document.xml"))
        relationships = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
        content_types = etree.fromstring(archive.read("[Content_Types].xml"))
    comment_ids = {int(value) for value in comments.xpath("//w:comment/@w:id", namespaces={"w": W})}
    starts = {int(value) for value in document.xpath("//w:commentRangeStart/@w:id", namespaces={"w": W})}
    ends = {int(value) for value in document.xpath("//w:commentRangeEnd/@w:id", namespaces={"w": W})}
    references = {int(value) for value in document.xpath("//w:commentReference/@w:id", namespaces={"w": W})}
    expected = expected_ids if expected_ids is not None else comment_ids
    valid = (expected <= comment_ids and expected <= starts and expected <= ends and expected <= references
             and any(rel.get("Type") == COMMENTS_REL for rel in relationships)
             and any(item.get("PartName") == "/word/comments.xml" for item in content_types))
    if not valid:
        raise ValueError("La estructura de comentarios del DOCX está incompleta.")
    return {"valid": True, "comments": len(comment_ids), "verified_ids": sorted(expected)}
