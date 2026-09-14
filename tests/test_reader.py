import hashlib
import json

import pytest
from docx import Document
from docx.oxml import OxmlElement
from lxml import etree

from revisor_crf import export_json, read_docx
from revisor_crf.cli import main
from revisor_crf.sample import create_sample


@pytest.fixture
def sample(tmp_path):
    return create_sample(tmp_path / "sintetico.docx")


def walk(blocks):
    for block in blocks:
        yield block
        yield from walk(block.get("blocks", []))
        for row in block.get("rows", []):
            yield row
            for cell in row["cells"]:
                yield cell
                yield from walk(cell["blocks"])


def test_order_text_styles_and_sections(sample):
    result = read_docx(sample)
    blocks = result["blocks"]
    assert [b["type"] for b in blocks] == [
        "paragraph", "paragraph", "table", "paragraph", "table", "paragraph", "paragraph", "paragraph"]
    assert blocks[1]["text"] == "Texto de prueba: áéíóú, ñ y 漢字.\tDato\nSegunda línea."
    assert blocks[0]["style"]["id"] == "Heading1"
    assert blocks[2]["style"]["name"] == "Table Grid"
    assert blocks[3]["text"] == "Después de la tabla."
    assert blocks[3]["headings"][0]["id"] == blocks[0]["id"]
    assert blocks[5]["section_id"] == "section-0001"
    assert blocks[6]["section_id"] == "section-0002"
    assert blocks[7]["headings"][0]["text"] == "2. Otra sección"
    assert result["warnings"] == []


def test_nested_tables_and_physical_merged_cells(sample):
    tables = [b for b in read_docx(sample)["blocks"] if b["type"] == "table"]
    nested_blocks = tables[0]["rows"][1]["cells"][1]["blocks"]
    assert [b["type"] for b in nested_blocks] == ["paragraph", "table", "paragraph"]
    assert nested_blocks[1]["rows"][0]["cells"][0]["text"] == "Detalle anidado"
    rows = tables[1]["rows"]
    assert len(rows[0]["cells"]) == 1
    assert rows[0]["cells"][0]["column_span"] == 2
    assert rows[1]["cells"][0]["vertical_merge"] == "restart"
    assert rows[2]["cells"][0]["vertical_merge"] == "continue"
    assert rows[2]["cells"][0]["text"] == ""
    assert tables[1]["text"].count("Combinación vertical") == 1


def test_identifiers_locations_and_no_input_mutation(sample):
    before = hashlib.sha256(sample.read_bytes()).hexdigest()
    result = read_docx(sample)
    elements = list(walk(result["blocks"]))
    document = Document(sample)
    parts = {str(p.partname): p for p in document.part.package.parts}
    for section in result["sections"]:
        for story in section["headers_and_footers"]:
            elements.extend(walk(story["blocks"]))
    ids = [e["id"] for e in elements]
    assert len(ids) == len(set(ids))
    for element in elements:
        source = element["source"]
        assert source["file"] == sample.name
        root = etree.fromstring(parts[source["part"]].blob)
        found = root.xpath(source["xml_path"], namespaces=root.nsmap)
        assert len(found) == 1
        assert etree.QName(found[0]).localname == {"paragraph": "p", "table": "tbl", "row": "tr", "cell": "tc"}[element["type"]]
    assert read_docx(sample) == result
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == before


def test_headers_footers_are_inherited(sample):
    sections = read_docx(sample)["sections"]
    for section in sections[:1]:
        stories = section["headers_and_footers"]
        assert [s["kind"] for s in stories] == ["header", "footer"]
        assert stories[0]["blocks"][0]["text"] == "ENCABEZADO SINTÉTICO"
        assert stories[1]["blocks"][0]["text"] == "PIE SINTÉTICO"
    assert sections[1]["headers_and_footers"][0]["linked_to_previous"] is True
    assert sections[1]["headers_and_footers"][0]["blocks"] == []
    assert sections[1]["headers_and_footers"][0]["content_ref"] == sections[0]["headers_and_footers"][0]["id"]


def test_json_and_cli(sample, tmp_path, capsys):
    output = tmp_path / "results" / "salida.json"
    assert main([str(sample), "-o", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == read_docx(sample)
    assert "Revisión sintética" in output.read_text(encoding="utf-8")
    assert "JSON guardado" in capsys.readouterr().out


@pytest.mark.parametrize("filename,content", [("malo.docx", b"no es un zip"), ("archivo.doc", b"texto")])
def test_invalid_input(tmp_path, filename, content, capsys):
    source = tmp_path / filename
    source.write_bytes(content)
    output = tmp_path / "salida.json"
    assert main([str(source), "-o", str(output)]) == 1
    assert "Error:" in capsys.readouterr().err
    assert not output.exists()


def test_missing_file_and_output_extension(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_docx(tmp_path / "ausente.docx")
    with pytest.raises(ValueError, match=".json"):
        export_json({}, tmp_path / "entrada.docx")


def test_empty_document_and_unsupported_content(tmp_path):
    source = tmp_path / "vacio.docx"
    document = Document()
    document.save(source)
    result = read_docx(source)
    assert result["blocks"] == []
    assert result["sections"][0]["headers_and_footers"] == []
    document.element.body.insert(0, OxmlElement("w:altChunk"))
    document.save(source)
    assert read_docx(source)["warnings"][0]["element"] == "altChunk"
