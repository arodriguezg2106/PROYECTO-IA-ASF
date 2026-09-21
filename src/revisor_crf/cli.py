"""Interfaz de línea de comandos."""

import argparse
import sys

from .reader import export_json, read_docx


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extrae o revisa determinísticamente un DOCX CRF.")
    parser.add_argument("input", help="Documento DOCX de entrada")
    parser.add_argument("-o", "--output", required=True, help="Archivo JSON de salida")
    parser.add_argument("--mode", choices=("final", "original", "all"), default="final")
    parser.add_argument("--numbers", action="store_true", help="Exporta solo el inventario numérico y sus metadatos")
    parser.add_argument("--review", action="store_true", help="Ejecuta el motor de validaciones determinísticas")
    parser.add_argument("--html", help="Reporte HTML autónomo (solo con --review)")
    parser.add_argument("--commented-docx", help="Copia DOCX con comentarios de orientación (solo con --review)")
    parser.add_argument("--rules", help="Catálogo JSON opcional de expresiones (solo con --review)")
    args = parser.parse_args(argv)
    try:
        if args.numbers and args.review:
            raise ValueError("--numbers y --review no pueden utilizarse juntos.")
        if args.html and not args.review:
            raise ValueError("--html requiere --review.")
        if args.rules and not args.review:
            raise ValueError("--rules requiere --review.")
        if args.commented_docx and not args.review:
            raise ValueError("--commented-docx requiere --review.")
        if args.review:
            from .html_report import export_html
            from .review import review_document
            result = review_document(args.input, mode=args.mode, catalog_path=args.rules)
            if args.commented_docx:
                from .commented_docx import export_commented_docx
                result["commented_copy"] = export_commented_docx(
                    args.input, result, args.commented_docx
                )
            if args.html:
                export_html(result, args.html)
        else:
            result = read_docx(args.input, mode=args.mode)
        if args.numbers:
            from .numbers import extract_numbers
            result = extract_numbers(result)
        export_json(result, args.output)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    outputs = []
    if args.review and args.html:
        outputs.append(f"HTML guardado en {args.html}")
    if args.review and args.commented_docx:
        outputs.append(f"copia comentada guardada en {args.commented_docx}")
    suffix = "; " + "; ".join(outputs) if outputs else ""
    print(f"JSON guardado en {args.output}{suffix} ({len(result.get('warnings', []))} advertencias)")
    return 0
