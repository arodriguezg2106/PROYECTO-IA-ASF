"""Documento exclusivamente sintético para demostración y pruebas."""

import argparse
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION_START


def create_sample(path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    document.sections[0].header.paragraphs[0].text = "ENCABEZADO SINTÉTICO"
    document.sections[0].footer.paragraphs[0].text = "PIE SINTÉTICO"
    document.add_heading("1. Revisión sintética", level=1)
    document.add_paragraph("Texto de prueba: áéíóú, ñ y 漢字.\tDato\nSegunda línea.")
    table = document.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "Concepto"
    table.cell(0, 1).text = "Valor"
    table.cell(1, 0).text = "Dato inventado"
    table.cell(1, 1).text = "100"
    nested = table.cell(1, 1).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "Detalle anidado"
    document.add_paragraph("Después de la tabla.")
    merged = document.add_table(rows=3, cols=2)
    merged.cell(0, 0).merge(merged.cell(0, 1)).text = "Combinación horizontal"
    merged.cell(1, 0).merge(merged.cell(2, 0)).text = "Combinación vertical"
    document.add_section(WD_SECTION_START.NEW_PAGE)
    document.add_heading("2. Otra sección", level=1)
    document.add_paragraph("Fin del documento sintético.")
    document.save(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera un DOCX sintético, sin datos reales.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    create_sample(args.output)
