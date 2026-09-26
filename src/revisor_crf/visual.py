"""Contrato desacoplado para una futura verificación visual renderizada."""
from __future__ import annotations
from typing import Protocol

class VisualVerifier(Protocol):
    @property
    def capabilities(self) -> tuple[str, ...]: ...
    def verify(self, path, document) -> dict: ...

class NullVisualVerifier:
    """Implementación predeterminada: nunca requiere Word ni altera el archivo."""
    capabilities = ("pagination", "rendered_borders", "decimal_alignment")
    def verify(self, path, document) -> dict:
        return {
            "provider": "none", "status": "not_configured", "capabilities": list(self.capabilities), "findings": [],
            "limitations": [
                "No se evaluó paginación renderizada.",
                "La alineación visual exacta por punto decimal requiere un renderizador.",
                "La apariencia final de bordes puede diferir por precedencia de estilos de Word.",
            ],
        }
