import json
from decimal import Decimal
from pathlib import Path

import pytest
from revisor_crf import read_docx
from revisor_crf.numbers import detect_numbers, extract_numbers
from synthetic_validation_bank import EXPECTED, generate
from audit_crf import inventory, output_elements

CASES = json.loads((Path(__file__).parent / "data" / "numeric_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_predefined_numeric_case(case):
    number, = detect_numbers(case["text"], case.get("metadata"))
    for field, key in (("tipo", "type"), ("unidad_original", "unit"), ("confidence", "confidence"), ("usable_for_comparison", "usable")):
        assert number[field] == case[key]
    for field, key in (("valor_decimal", "decimal"), ("multiplicador", "multiplier"), ("valor_normalizado", "normalized")):
        actual = number[field]
        expected = case[key]
        if expected is None:
            assert actual is None
        else:
            assert isinstance(actual, Decimal)
            assert actual.as_tuple() == Decimal(expected).as_tuple()
    assert number["reason"]
    if case["confidence"] == "low":
        assert number["classification"] == "ambiguous"


@pytest.fixture(scope="module")
def integration_bank(tmp_path_factory):
    return generate(tmp_path_factory.mktemp("synthetic_bank"))


@pytest.mark.parametrize("name", list(EXPECTED))
def test_five_synthetic_docx(name, integration_bank):
    document = read_docx(integration_bank[name])
    result = extract_numbers(document)
    assert len(result["cifras"]) == len(EXPECTED[name])
    for number, expected in zip(result["cifras"], EXPECTED[name]):
        for key, value in expected.items():
            assert number[key] == (Decimal(value) if key in {"valor_decimal", "multiplicador", "valor_normalizado"} and value is not None else value)
    xml = inventory(integration_bank[name])
    paragraphs = [e for e in output_elements(document) if e["type"] == "paragraph"]
    assert len(xml) == len(paragraphs)
    assert len({(e["source"]["part"], e["source"]["xml_path"]) for e in paragraphs}) == len(xml)
    if name == "tablas":
        assert [n["origin_unit"] for n in result["cifras"]] == ["column_header", "row_header", "table_caption", "table_caption"]
    if name == "revisiones":
        assert result["cifras"][0]["revision_status"] == "inserted"
        assert "100" in document["blocks"][0]["text_all"]


def test_conflicting_headers_are_not_usable():
    number, = detect_numbers("10", {"encabezado_columna": "pesos", "encabezado_fila": "miles de pesos",
                                   "column_header_unambiguous": True, "row_header_unambiguous": True})
    assert number["classification"] == "ambiguous"
    assert number["confidence"] == "low"
    assert not number["usable_for_comparison"]


def test_inline_prefix_is_explicit_not_previous_paragraph():
    number, = detect_numbers("Miles de pesos: 10")
    assert number["origin_unit"] == "explicit"
    assert number["confidence"] == "high"
    assert number["usable_for_comparison"]
