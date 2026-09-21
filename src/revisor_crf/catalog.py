"""Catálogo versionado y configurable de las reglas determinísticas."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path


DEFAULT_CATALOG = {
    "version": "2026.2",
    "total_labels": [
        r"^total$",
        r"^suma$",
        r"^importe total$",
        r"^total observado$",
        r"^subtotal(?:\s+.+)?$",
    ],
    "observation_positive": [
        r"\bcon observaci[oó]n(?:es)?\b",
        r"\bse (?:determin[oó]|determinaron) observaci[oó]n(?:es)?\b",
        r"\bse (?:identificaron|detectaron|determinaron) irregularidades\b",
        r"\bpresenta(?:n)? irregularidades\b",
    ],
    "observation_negative": [
        r"\bsin observaci[oó]n(?:es)?\b",
        r"\bno se (?:determin[oó]|determinaron) observaci[oó]n(?:es)?\b",
        r"\bsin (?:identificar )?irregularidades\b",
        r"\bno se identificaron irregularidades\b",
        r"\bno presenta(?:n)? irregularidades\b",
    ],
    "conclusion_markers": [r"\bconclusi[oó]n\b", r"\bse concluye\b", r"\bdictamen\b"],
    "scope_markers": [r"\bresultado\s+(?:n[uú]m(?:ero)?\.?\s*)?\d+\b"],
}


def load_catalog(path: str | Path | None = None) -> dict:
    """Carga un catálogo completo; los campos omitidos conservan los valores seguros."""
    catalog = deepcopy(DEFAULT_CATALOG)
    if path is None:
        return catalog
    source = Path(path)
    try:
        custom = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se pudo leer el catálogo de reglas: {source}") from exc
    if not isinstance(custom, dict):
        raise ValueError("El catálogo de reglas debe ser un objeto JSON.")
    for key, value in custom.items():
        if key not in catalog:
            raise ValueError(f"Campo desconocido en el catálogo: {key}")
        if key == "version":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("La versión del catálogo debe ser texto no vacío.")
        elif not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"El campo {key} debe ser una lista de expresiones regulares.")
        catalog[key] = value
    for key, patterns in catalog.items():
        if key == "version":
            continue
        try:
            for pattern in patterns:
                re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Expresión regular inválida en {key}: {exc}") from exc
    return catalog
