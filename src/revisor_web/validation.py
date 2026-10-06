"""Validación estricta de documentos DOCX para la web interna."""

from __future__ import annotations

import zipfile
from pathlib import Path

ZIP_MAGIC_BYTES = b"PK\x03\x04"
MAX_UNCOMPRESSED_RATIO = 100  # Mitigación de Zip Bomb: ratio máximo descomprimido/comprimido
MAX_UNCOMPRESSED_TOTAL_BYTES = 250 * 1024 * 1024  # 250 MB máximo descomprimido


class ValidationError(Exception):
    """Error de validación del documento."""


class InvalidExtensionError(ValidationError):
    """El archivo no tiene extensión .docx."""


class FileTooLargeError(ValidationError):
    """El archivo excede el tamaño máximo permitido."""


class InvalidSignatureError(ValidationError):
    """El archivo no presenta la firma mágica ZIP/OOXML esperada."""


class CorruptDocumentError(ValidationError):
    """El archivo DOCX está dañado o no contiene la estructura requerida."""


def validate_filename(filename: str | None) -> str:
    """Verifica que el nombre de archivo tenga extensión .docx."""
    if not filename or not filename.strip():
        raise InvalidExtensionError("No se proporcionó un nombre de archivo válido.")
    name = Path(filename).name
    if not name.lower().endswith(".docx"):
        raise InvalidExtensionError("Solo se admiten documentos con extensión .docx.")
    return name


def validate_header_signature(header: bytes) -> None:
    """Verifica la firma mágica ZIP de un DOCX."""
    if not header.startswith(ZIP_MAGIC_BYTES):
        raise InvalidSignatureError(
            "El archivo no es un documento DOCX válido (firma ZIP no encontrada)."
        )


def validate_docx_archive(path: Path | str) -> None:
    """Valida la integridad del archivo ZIP y la presencia de partes críticas de Word.

    La mitigación de bombas ZIP se evalúa primero leyendo únicamente las cabeceras
    del catálogo central (infolist) ANTES de ejecutar cualquier descompresión
    o comprobación de CRC (testzip).
    """
    file_path = Path(path)
    if not file_path.exists():
        raise CorruptDocumentError("El archivo no existe en el almacenamiento temporal.")

    try:
        with zipfile.ZipFile(file_path, "r") as archive:
            # 1. Mitigación preventiva de Zip Bomb leyendo solo cabeceras centrales (sin descomprimir)
            infolist = archive.infolist()
            total_uncompressed = sum(info.file_size for info in infolist)
            total_compressed = sum(info.compress_size for info in infolist) or 1

            if total_uncompressed > MAX_UNCOMPRESSED_TOTAL_BYTES:
                raise FileTooLargeError(
                    "El contenido descomprimido del documento excede el límite de seguridad (250 MB)."
                )

            if (total_uncompressed / total_compressed) > MAX_UNCOMPRESSED_RATIO:
                raise CorruptDocumentError(
                    "El documento presenta un ratio de compresión anómalo y fue rechazado por seguridad."
                )

            # 2. Comprobación de partes esenciales de un paquete Word OOXML
            namelist = archive.namelist()
            if "word/document.xml" not in namelist or "[Content_Types].xml" not in namelist:
                raise CorruptDocumentError(
                    "El archivo no tiene la estructura OOXML requerida para un documento Word."
                )

            # 3. Comprobación de integridad CRC (descompresión segura, ya acotada por paso 1)
            bad_file = archive.testzip()
            if bad_file:
                raise CorruptDocumentError(
                    f"El archivo ZIP está corrupto (error de integridad en parte interna)."
                )

    except zipfile.BadZipFile as exc:
        raise CorruptDocumentError("El archivo no es un archivo ZIP o está dañado.") from exc
    except (KeyError, RuntimeError) as exc:
        raise CorruptDocumentError("Error al inspeccionar la estructura del DOCX.") from exc

