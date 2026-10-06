"""Gestión de almacenamiento temporal por trabajo y limpieza por TTL."""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("revisor_web.storage")


class JobStorage:
    """Administra directorios aislados e información de estado para cada trabajo."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        # Validación de seguridad: el job_id debe ser un UUID hexadecimal estricto
        try:
            val = uuid.UUID(hex=job_id)
            safe_id = val.hex
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Identificador de trabajo inválido: debe ser un UUID hexadecimal.") from exc

        job_dir = (self.base_dir / safe_id).resolve()
        if not job_dir.is_relative_to(self.base_dir) or job_dir == self.base_dir:
            raise ValueError("Ruta de trabajo fuera del directorio permitido.")
        return job_dir

    def delete_job(self, job_id: str) -> bool:
        """Elimina de forma dirigida y segura el directorio correspondiente a un job_id específico."""
        try:
            job_dir = self._job_dir(job_id)
            if job_dir.exists() and job_dir.is_dir():
                shutil.rmtree(job_dir, ignore_errors=True)
                return True
        except ValueError:
            return False
        return False

    def create_job(self, original_filename: str, file_size: int) -> dict:
        """Crea un directorio temporal y registra los metadatos iniciales del trabajo."""
        job_id = uuid.uuid4().hex
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)

        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "job_id": job_id,
            "status": "recibido",
            "created_at": now,
            "updated_at": now,
            "created_timestamp": time.time(),
            "original_filename": Path(original_filename).name,
            "file_size": file_size,
            "error": None,
            "summary": None,
        }
        self._write_meta(job_dir, metadata)
        return metadata

    def save_input_file(self, job_id: str, content: bytes) -> Path:
        """Almacena el archivo DOCX de entrada en el directorio del trabajo."""
        job_dir = self._job_dir(job_id)
        input_path = job_dir / "input.docx"
        input_path.write_bytes(content)
        return input_path

    def get_input_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "input.docx"

    def get_output_paths(self, job_id: str) -> dict[str, Path]:
        job_dir = self._job_dir(job_id)
        return {
            "json": job_dir / "report.json",
            "html": job_dir / "report.html",
            "docx": job_dir / "commented.docx",
        }

    def get_job(self, job_id: str) -> dict | None:
        """Recupera los metadatos del trabajo."""
        try:
            job_dir = self._job_dir(job_id)
            meta_path = job_dir / "meta.json"
            if not meta_path.exists():
                return None
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError, json.JSONDecodeError):
            return None

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
        summary: dict | None = None,
    ) -> dict:
        """Actualiza el estado y metadatos del trabajo."""
        job_dir = self._job_dir(job_id)
        metadata = self.get_job(job_id)
        if metadata is None:
            raise KeyError(f"Trabajo no encontrado: {job_id}")

        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        if status is not None:
            metadata["status"] = status
        if error is not None:
            metadata["error"] = error
        if summary is not None:
            metadata["summary"] = summary

        self._write_meta(job_dir, metadata)
        return metadata

    def get_artifact_path(self, job_id: str, artifact_type: str) -> Path | None:
        """Obtiene la ruta a un archivo de resultado si existe."""
        paths = self.get_output_paths(job_id)
        target = paths.get(artifact_type.lower())
        if target and target.exists() and target.is_file():
            return target
        return None

    def cleanup_expired_jobs(self, ttl_seconds: int) -> list[str]:
        """Elimina directorios de trabajos cuya antigüedad exceda el TTL configurado."""
        now = time.time()
        deleted = []
        if not self.base_dir.exists():
            return deleted

        for item in self.base_dir.iterdir():
            if not item.is_dir():
                continue
            meta_file = item / "meta.json"
            created_timestamp = None
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    created_timestamp = meta.get("created_timestamp")
                except Exception:
                    pass

            # Si no hay timestamp en el JSON, recurrir a la fecha de modificación del directorio
            if created_timestamp is None:
                try:
                    created_timestamp = item.stat().st_mtime
                except OSError:
                    continue

            # NUNCA eliminar trabajos que actualmente se encuentran en procesamiento
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    if meta.get("status") == "procesando":
                        continue
                except Exception:
                    pass

            if now - created_timestamp > ttl_seconds:
                try:
                    shutil.rmtree(item, ignore_errors=True)
                    deleted.append(item.name)
                except Exception as exc:
                    logger.warning("Error al eliminar directorio expirado: %s", type(exc).__name__)

        return deleted

    def _write_meta(self, job_dir: Path, data: dict) -> None:
        meta_path = job_dir / "meta.json"
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

