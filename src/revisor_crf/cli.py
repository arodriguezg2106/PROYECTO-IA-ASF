"""Interfaz de línea de comandos."""

import argparse
import sys

from .reader import export_json, read_docx


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extrae o revisa un DOCX CRF con reglas y semántica local opcional.")
    parser.add_argument("input", help="Documento DOCX de entrada")
    parser.add_argument("-o", "--output", required=True, help="Archivo JSON de salida")
    parser.add_argument("--mode", choices=("final", "original", "all"), default="final")
    parser.add_argument("--numbers", action="store_true", help="Exporta solo el inventario numérico y sus metadatos")
    parser.add_argument("--review", action="store_true", help="Ejecuta el motor de validaciones determinísticas")
    parser.add_argument("--semantic-review", action="store_true",
                        help="Añade asociación semántica local de alta precisión (requiere --review)")
    parser.add_argument("--semantic-config", help="Configuración JSON o TOML de la revisión semántica")
    parser.add_argument("--html", help="Reporte HTML autónomo (solo con --review)")
    parser.add_argument("--commented-docx", help="Copia DOCX con comentarios de orientación (solo con --review)")
    parser.add_argument("--editorial-review", action="store_true", help="Ejecuta la revisión editorial ASF")
    parser.add_argument("--editorial-ollama", action="store_true", help="Añade revisión editorial contextual con Ollama")
    parser.add_argument("--editorial-experimental-model", action="store_true", help="Permite evaluar explícitamente un modelo editorial no aprobado")
    parser.add_argument("--editorial-language-tool", action="store_true", help="Añade LanguageTool local en modo experimental")
    parser.add_argument("--editorial-experimental-provider", action="store_true", help="Autoriza explícitamente proveedores editoriales experimentales")
    parser.add_argument("--editorial-config", help="Configuración JSON o TOML editorial")
    parser.add_argument("--markdown", help="Reporte Markdown (solo con --review)")
    parser.add_argument("--sarif", help="Reporte interoperable SARIF 2.1.0 (solo con --review)")
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
        if args.semantic_review and not args.review:
            raise ValueError("--semantic-review requiere --review.")
        if args.semantic_config and not args.semantic_review:
            raise ValueError("--semantic-config requiere --semantic-review.")
        if (args.editorial_review or args.editorial_ollama or args.editorial_config) and not args.review:
            raise ValueError("La revisión editorial requiere --review.")
        if args.editorial_ollama and not args.editorial_review:
            raise ValueError("--editorial-ollama requiere --editorial-review.")
        if args.editorial_experimental_model and not args.editorial_ollama:
            raise ValueError("--editorial-experimental-model requiere --editorial-ollama.")
        if args.editorial_language_tool and not args.editorial_review:
            raise ValueError("--editorial-language-tool requiere --editorial-review.")
        if args.editorial_language_tool and not args.editorial_experimental_provider:
            raise ValueError("--editorial-language-tool requiere --editorial-experimental-provider.")
        if args.editorial_experimental_provider and not args.editorial_language_tool:
            raise ValueError("--editorial-experimental-provider requiere --editorial-language-tool.")
        if args.markdown and not args.review:
            raise ValueError("--markdown requiere --review.")
        if args.sarif and not args.review:
            raise ValueError("--sarif requiere --review.")
        if args.review:
            from .html_report import export_html
            from .review import review_document
            result = review_document(
                args.input, mode=args.mode, catalog_path=args.rules,
                semantic=args.semantic_review, semantic_config_path=args.semantic_config,
                editorial=args.editorial_review, editorial_config_path=args.editorial_config,
                editorial_ollama=args.editorial_ollama,
                editorial_experimental_model=args.editorial_experimental_model,
                editorial_language_tool=args.editorial_language_tool,
                editorial_experimental_provider=args.editorial_experimental_provider,
            )
            if args.commented_docx:
                from .commented_docx import export_commented_docx
                result["commented_copy"] = export_commented_docx(
                    args.input, result, args.commented_docx
                )
            if args.html:
                export_html(result, args.html)
            if args.markdown:
                from .editorial_report import export_markdown
                export_markdown(result, args.markdown)
            if args.sarif:
                from .sarif_report import export_sarif
                export_sarif(result, args.sarif)
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
    if args.review and args.markdown:
        outputs.append(f"Markdown guardado en {args.markdown}")
    if args.review and args.sarif:
        outputs.append(f"SARIF guardado en {args.sarif}")
    suffix = "; " + "; ".join(outputs) if outputs else ""
    print(f"JSON guardado en {args.output}{suffix} ({len(result.get('warnings', []))} advertencias)")
    return 0
