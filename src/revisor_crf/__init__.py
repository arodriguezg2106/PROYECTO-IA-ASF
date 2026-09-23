"""Lectura local y estructurada de DOCX."""

from .reader import export_json, read_docx
from .review import review_document
from .semantic import AmountType, SemanticCase, SemanticConfig, SemanticProvider, SemanticRelation

__all__ = [
    "read_docx", "export_json", "review_document", "AmountType", "SemanticCase",
    "SemanticConfig", "SemanticProvider", "SemanticRelation",
]
