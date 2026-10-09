"""Servicio de orquestación y control de concurrencia para revisiones CRF."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from revisor_crf.commented_docx import export_commented_docx
from revisor_crf.html_report import export_html
from revisor_crf.reader import export_json
from revisor_crf.review import review_document

from .config import WebConfig
from .storage import JobStorage
from .telemetry import PilotTelemetry

logger = logging.getLogger("revisor_web.service")


class ServerBusyError(Exception):
    """El servidor ha alcanzado su límite de concurrencia y cola."""


class ReviewService:
    """Gestiona el encolado y procesamiento determinístico de documentos."""

    def __init__(self, config: WebConfig, storage: JobStorage, telemetry: PilotTelemetry | None = None) -> None:
        self.config = config
        self.storage = storage
        self.telemetry = telemetry or PilotTelemetry()
        self._semaphore = asyncio.Semaphore(config.max_concurrent_jobs)
        self._active_jobs: int = 0
        self._queued_jobs: int = 0

    @property
    def is_saturated(self) -> bool:
        """Determina si el servidor no puede aceptar nuevos trabajos."""
        total = self._active_jobs + self._queued_jobs
        return total >= (self.config.max_concurrent_jobs + self.config.max_queue_size)

    def enqueue_job(self, job_id: str, input_path: Path, file_size: int) -> None:
        """Registra el trabajo y lanza su ejecución asíncrona controlada."""
        if self.is_saturated:
            raise ServerBusyError(
                "El servidor se encuentra ocupado procesando solicitudes. Por favor intente más tarde."
            )

        self._queued_jobs += 1
        asyncio.create_task(self._process_job_task(job_id, input_path, file_size))

    async def _process_job_task(self, job_id: str, input_path: Path, file_size: int) -> None:
        """Adquiere la ranura de concurrencia y ejecuta el motor en un hilo secundario."""
        try:
            async with self._semaphore:
                self._queued_jobs = max(0, self._queued_jobs - 1)
                self._active_jobs += 1
                try:
                    await asyncio.to_thread(self._run_review_sync, job_id, input_path, file_size)
                finally:
                    self._active_jobs = max(0, self._active_jobs - 1)
        except Exception as exc:
            logger.error("Error no controlado en la tarea del trabajo %s: %s", job_id, type(exc).__name__)

    def _run_review_sync(self, job_id: str, input_path: Path, file_size: int) -> None:
        """Ejecuta el flujo síncrono del motor determinístico y exporta los artefactos."""
        logger.info("Iniciando revisión determinística para trabajo %s (tamaño: %d bytes)", job_id, file_size)
        self.storage.update_job(job_id, status="procesando")

        start_time = time.perf_counter()
        try:
            # Reutilización de la API pública existente de revisor_crf
            # Ollama y LanguageTool están estrictamente deshabilitados en este MVP
            result = review_document(
                input_path,
                mode="final",
                catalog_path=None,
                semantic=False,
                editorial=False,
            )

            paths = self.storage.get_output_paths(job_id)

            # Exportación de los 3 formatos solicitados (conforme a la CLI):
            # 1. Generar primero el DOCX comentado e incorporar commented_copy a result
            result["commented_copy"] = export_commented_docx(
                input_path, result, paths["docx"]
            )
            # 2. Exportar JSON y HTML después para que incluyan commented_copy
            export_json(result, paths["json"])
            export_html(result, paths["html"])

            duration = time.perf_counter() - start_time

            # Resumen técnico sin contener texto confidencial de los párrafos
            summary = {
                "schema_version": result.get("schema_version"),
                "alerts_count": len(result.get("alerts", [])),
                "warnings_count": len(result.get("warnings", [])),
                "rules_executed": result.get("rules_executed", []),
                "by_rule": result.get("summary", {}).get("by_rule", {}),
                "by_severity": result.get("summary", {}).get("by_severity", {}),
                "evaluated": result.get("summary", {}).get("evaluated", 0),
                "excluded": result.get("summary", {}).get("excluded", 0),
                "sha256": result.get("source", {}).get("sha256", ""),
                "duration_seconds": round(duration, 3),
            }

            completed_meta = self.storage.update_job(job_id, status="terminado", summary=summary)
            self.telemetry.record(
                "job_completed",
                job_id=job_id,
                identity=completed_meta.get("owner"),
                status="terminado",
                duration_seconds=duration,
            )
            logger.info(
                "Trabajo %s completado con éxito en %.2f s (alertas detectadas: %d)",
                job_id,
                duration,
                summary["alerts_count"],
            )

        except Exception as exc:
            duration = time.perf_counter() - start_time
            # Se registra únicamente el tipo de excepción; nunca el texto del documento
            logger.error("Fallo al procesar trabajo %s tras %.2f s: %s", job_id, duration, type(exc).__name__)
            clean_error = f"Error durante la revisión determinística: {type(exc).__name__}"
            failed_meta = self.storage.update_job(job_id, status="fallido", error=clean_error)
            self.telemetry.record(
                "job_failed",
                job_id=job_id,
                identity=failed_meta.get("owner"),
                status="fallido",
                duration_seconds=duration,
            )
