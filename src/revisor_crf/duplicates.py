"""Identidad documental y similitud estructural; no compara cifras."""

import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations
from zipfile import ZipFile

from .reader import read_docx


def digest(value):
    return hashlib.sha256(value).hexdigest()


def elements(result):
    def walk(items):
        for block in items:
            yield block
            yield from walk(block.get("blocks", []))
            for row in block.get("rows", []):
                yield row
                for cell in row["cells"]:
                    yield cell
                    yield from walk(cell["blocks"])
    yield from walk(result["blocks"])
    for section in result["sections"]:
        for story in section["headers_and_footers"]:
            yield from walk(story["blocks"])
    for story in result.get("supplementary_parts", []):
        yield from walk(story["blocks"])


def fingerprint(path):
    result = read_docx(path, mode="all")
    sequence, texts = [], []
    for e in elements(result):
        item = {k: e.get(k) for k in ("type", "style", "grid_column", "column_span", "vertical_merge", "is_header")}
        if e["type"] == "paragraph":
            item["text"] = e["text_all"]
            item["revisions"] = [(c.get("revision_status"), c.get("text")) for c in e["content"] if c["type"] == "text"]
            texts.append(re.sub(r"\s+", " ", unicodedata.normalize("NFKC", e["text_all"])).strip())
        sequence.append(digest(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()))
    # Include images/objects/relationships/styles: matching text alone is not identity.
    with ZipFile(path) as package:
        payload = [(name, digest(package.read(name))) for name in sorted(package.namelist()) if name.startswith("word/")]
    return {"documento_id": path.name, "sha256_file": digest(path.read_bytes()),
            "sha256_normalized_text": digest("\n".join(texts).encode()),
            "sha256_element_sequence": digest("\n".join(sequence).encode()),
            "sha256_content_parts": digest(json.dumps(payload).encode()),
            "element_count": len(sequence), "_sequence": sequence}


def analyze_duplicates(paths):
    records = [fingerprint(p) for p in sorted(paths, key=lambda p: p.name.casefold())]
    parents = list(range(len(records)))

    def find(i):
        while parents[i] != i:
            i = parents[i]
        return i

    pairs = []
    for i, j in combinations(range(len(records)), 2):
        a, b = records[i], records[j]
        same_bytes = a["sha256_file"] == b["sha256_file"]
        same_text = a["sha256_normalized_text"] == b["sha256_normalized_text"]
        same_sequence = a["sha256_element_sequence"] == b["sha256_element_sequence"]
        identical = same_bytes or (same_text and same_sequence and a["sha256_content_parts"] == b["sha256_content_parts"])
        similarity = 100 * SequenceMatcher(None, a["_sequence"], b["_sequence"], autojunk=False).ratio()
        pairs.append({"documento_a": a["documento_id"], "documento_b": b["documento_id"],
                      "sha256_file_igual": same_bytes, "texto_normalizado_igual": same_text,
                      "secuencia_igual": same_sequence, "similitud_secuencia_pct": round(similarity, 4), "identicos": identical})
        if identical:
            parents[find(j)] = find(i)
    for i, record in enumerate(records):
        members = [j for j in range(len(records)) if find(j) == find(i)]
        canonical = records[min(members)]
        record.update(duplicate_group_id="dup-" + canonical["sha256_content_parts"][:16] if len(members) > 1 else None,
                      canonical_document_id=canonical["documento_id"], included_in_aggregates=i == min(members))
        record.pop("_sequence")
    return {"metodo": "Identidad: SHA-256 de archivo igual, o texto y secuencia iguales más igualdad de todas las partes word/ (incluye imágenes). Similitud: SequenceMatcher sobre firmas estructurales, sin umbral de eliminación. El texto normalizado usa NFKC y espacios colapsados, conservando mayúsculas y números.",
            "documentos": records, "pares": pairs}
