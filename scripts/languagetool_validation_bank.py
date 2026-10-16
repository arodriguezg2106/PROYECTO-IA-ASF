"""Genera un banco sintético pareado para evaluar LanguageTool sin datos reales."""

from __future__ import annotations

import json
from pathlib import Path


PAIRS = [
    ("spelling", "El área entregó la documentazión completa para integrar el expediente solicitado.", "El área entregó la documentación completa para integrar el expediente solicitado."),
    ("spelling", "La unidad realizó la fiscalisación conforme al programa anual aprobado.", "La unidad realizó la fiscalización conforme al programa anual aprobado."),
    ("spelling", "El informe incluyó una recomendazión dirigida a la entidad fiscalizada.", "El informe incluyó una recomendación dirigida a la entidad fiscalizada."),
    ("spelling", "La documentación fue remitida para su revición por el área responsable.", "La documentación fue remitida para su revisión por el área responsable."),
    ("spelling", "La entidad presentó los comprobantes requerídos durante la auditoría practicada.", "La entidad presentó los comprobantes requeridos durante la auditoría practicada."),
    ("spelling", "El expediente contiene la informasión financiera correspondiente al ejercicio revisado.", "El expediente contiene la información financiera correspondiente al ejercicio revisado."),
    ("spelling", "La observación fue atendida mediante la acláración documental presentada oportunamente.", "La observación fue atendida mediante la aclaración documental presentada oportunamente."),
    ("spelling", "El grupo auditor verificó la existensia de controles internos suficientes.", "El grupo auditor verificó la existencia de controles internos suficientes."),
    ("spelling", "La cédula muestra el prosedimiento aplicado durante la revisión documental.", "La cédula muestra el procedimiento aplicado durante la revisión documental."),
    ("spelling", "La entidad justificó la diferensia identificada en los registros contables.", "La entidad justificó la diferencia identificada en los registros contables."),
    ("grammar", "Las áreas responsables presentó la información solicitada durante la auditoría.", "Las áreas responsables presentaron la información solicitada durante la auditoría."),
    ("grammar", "Los contratos revisados fue integrados correctamente en el expediente correspondiente.", "Los contratos revisados fueron integrados correctamente en el expediente correspondiente."),
    ("grammar", "La documentación comprobatoria fueron entregada dentro del plazo establecido originalmente.", "La documentación comprobatoria fue entregada dentro del plazo establecido originalmente."),
    ("grammar", "El área responsable remitieron los informes finales para su análisis.", "El área responsable remitió los informes finales para su análisis."),
    ("grammar", "Las observaciones determinada fueron comunicadas formalmente a la entidad fiscalizada.", "Las observaciones determinadas fueron comunicadas formalmente a la entidad fiscalizada."),
    ("grammar", "Cada una de las unidades entregaron su informe técnico correspondiente.", "Cada una de las unidades entregó su informe técnico correspondiente."),
    ("grammar", "La relación de contratos revisados contienen los importes efectivamente pagados.", "La relación de contratos revisados contiene los importes efectivamente pagados."),
    ("grammar", "Los resultados de la auditoría fue presentado ante el comité técnico.", "Los resultados de la auditoría fueron presentados ante el comité técnico."),
    ("grammar", "La entidad y el proveedor presentó documentación adicional durante la revisión.", "La entidad y el proveedor presentaron documentación adicional durante la revisión."),
    ("grammar", "Ninguna de las aclaraciones fueron suficiente para solventar la observación.", "Ninguna de las aclaraciones fue suficiente para solventar la observación."),
    ("punctuation", "La entidad presentó el informe , pero omitió los anexos requeridos.", "La entidad presentó el informe, pero omitió los anexos requeridos."),
    ("punctuation", "El área revisó los contratos;sin embargo, faltaron dos expedientes.", "El área revisó los contratos; sin embargo, faltaron dos expedientes."),
    ("punctuation", "La auditoría verificó  los registros y documentó los resultados obtenidos.", "La auditoría verificó los registros y documentó los resultados obtenidos."),
    ("punctuation", "La entidad informó que entregaría los anexos,sin precisar una fecha.", "La entidad informó que entregaría los anexos, sin precisar una fecha."),
    ("punctuation", "El expediente contiene contratos , facturas y comprobantes de pago.", "El expediente contiene contratos, facturas y comprobantes de pago."),
    ("institutional_noise", "La ASF revizó el oficio ASF-2026-001 y confirmó el importe de $1,250.00.", "La ASF revisó el oficio ASF-2026-001 y confirmó el importe de $1,250.00."),
    ("institutional_noise", "La UAA verificó el 25.0% y documéntó el resultado el 01/02/2026.", "La UAA verificó el 25.0% y documentó el resultado el 01/02/2026."),
    ("institutional_noise", "El artículo 12 del Reglamento fue análizado por el equipo auditor.", "El artículo 12 del Reglamento fue analizado por el equipo auditor."),
    ("institutional_noise", "La SHCP informó que el monto de $3,131,988.77 estaba concíliado.", "La SHCP informó que el monto de $3,131,988.77 estaba conciliado."),
    ("institutional_noise", "El CRF número 2026-15 fue intégrado al expediente de auditoría.", "El CRF número 2026-15 fue integrado al expediente de auditoría."),
]


def generate(path: str | Path) -> dict:
    cases = []
    for number, (category, incorrect, correct) in enumerate(PAIRS, 1):
        pair_id = f"LT-SYN-{number:03d}"
        cases.extend([
            {"case_id": f"{pair_id}-before", "pair_id": pair_id, "category": category,
             "fragment": incorrect, "expected_finding": True},
            {"case_id": f"{pair_id}-after", "pair_id": pair_id, "category": category,
             "fragment": correct, "expected_finding": False},
        ])
    payload = {
        "schema_version": "languagetool-evaluation-bank-1.0",
        "synthetic": True,
        "privacy": {"contains_raw_institutional_text": False, "safe_for_version_control": True},
        "summary": {"pairs": len(PAIRS), "cases": len(cases)},
        "cases": cases,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = generate(Path(__file__).resolve().parents[1] / "tests" / "data" / "languagetool_synthetic.json")
    print(json.dumps(result["summary"], ensure_ascii=False))
