"""Lectura local y estructurada de DOCX."""

from .reader import export_json, read_docx
from .review import review_document

__all__ = ["read_docx", "export_json", "review_document"]
