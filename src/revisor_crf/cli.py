"""Interfaz de línea de comandos."""

import argparse
import sys

from .reader import export_json, read_docx


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extrae párrafos y tablas de un DOCX a JSON.")
    parser.add_argument("input", help="Documento DOCX de entrada")
    parser.add_argument("-o", "--output", required=True, help="Archivo JSON de salida")
    parser.add_argument("--mode", choices=("final", "original", "all"), default="final")
    parser.add_argument("--numbers", action="store_true", help="Exporta solo el inventario numérico y sus metadatos")
    args = parser.parse_args(argv)
    try:
        result = read_docx(args.input, mode=args.mode)
        if args.numbers:
            from .numbers import extract_numbers
            result = extract_numbers(result)
        export_json(result, args.output)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"JSON guardado en {args.output} ({len(result.get('warnings', []))} advertencias)")
    return 0
