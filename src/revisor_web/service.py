"""Servicio de orquestación y control de concurrencia para revisiones CRF."""

from __future__ import annotations

import asyncio
from collections import Counter, deque
import hashlib
import logging
import threading
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
        self._queue: asyncio.Queue = asyncio.Queue(
            maxsize=config.max_concurrent_jobs + config.max_queue_size
        )
        self._admission_lock = asyncio.Lock()
        self._worker_tasks: list[asyncio.Task] = []
        self._pending_ids: deque[str] = deque()
        self._accepted_by_owner: Counter[str] = Counter()
        self._active_jobs: int = 0
        self._queued_jobs: int = 0

    async def start(self) -> None:
        if self._worker_tasks:
            return
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(index), name=f"revisor-worker-{index}")
            for index in range(self.config.max_concurrent_jobs)
        ]

    async def stop(self) -> None:
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

    @property
    def is_saturated(self) -> bool:
        """Determina si el servidor no puede aceptar nuevos trabajos."""
        total = self._active_jobs + self._queued_jobs
        return total >= (self.config.max_concurrent_jobs + self.config.max_queue_size)

    async def enqueue_job(
        self, job_id: str, input_path: Path, file_size: int, owner: str
    ) -> dict:
        """Admite de forma atómica un trabajo en la cola FIFO acotada."""
        if not self._worker_tasks:
            await self.start()
        async with self._admission_lock:
            if self.is_saturated or self._accepted_by_owner[owner] >= self.config.max_jobs_per_user:
                raise ServerBusyError(
                    "El servidor se encuentra ocupado o el usuario alcanzó su límite de trabajos."
                )
            self._queued_jobs += 1
            self._accepted_by_owner[owner] += 1
            self._pending_ids.append(job_id)
            self._queue.put_nowait((job_id, input_path, file_size, owner, time.monotonic()))
            depth = self._queued_jobs
        self.telemetry.record(
            "job_queued", job_id=job_id, identity=owner, queue_depth=depth
        )
        return {"queue_position": self.queue_position(job_id), "queue_depth": depth}

    def queue_position(self, job_id: str) -> int | None:
        try:
            return list(self._pending_ids).index(job_id) + 1
        except ValueError:
            return None

    @property
    def queue_depth(self) -> int:
        return self._queued_jobs

    async def _worker_loop(self, worker_index: int) -> None:
        while True:
            job_id, input_path, file_size, owner, queued_at = await self._queue.get()
            cancel_event = threading.Event()
            async with self._admission_lock:
                try:
                    self._pending_ids.remove(job_id)
                except ValueError:
                    pass
                self._queued_jobs = max(0, self._queued_jobs - 1)
                self._active_jobs += 1
            wait_seconds = time.monotonic() - queued_at
            self.telemetry.record(
                "job_started", job_id=job_id, identity=owner, duration_seconds=wait_seconds
            )
            future = asyncio.create_task(
                asyncio.to_thread(
                    self._run_review_sync, job_id, input_path, file_size, cancel_event, wait_seconds
                )
            )
            timed_out = False
            try:
                await asyncio.wait_for(
                    asyncio.shield(future), timeout=self.config.job_timeout_seconds
                )
            except TimeoutError:
                timed_out = True
                cancel_event.set()
                logger.warning("Trabajo %s excedió el timeout configurado", job_id)
                await future
            except asyncio.CancelledError:
                cancel_event.set()
                raise
            except Exception as exc:
                logger.error(
                    "Error no controlado en worker %d para %s: %s",
                    worker_index, job_id, type(exc).__name__,
                )
            finally:
                if timed_out:
                    meta = self.storage.get_job(job_id)
                    if meta and meta.get("status") not in {"fallido", "terminado"}:
                        self.storage.update_job(
                            job_id,
                            status="fallido",
                            error="El procesamiento excedió el tiempo máximo permitido.",
                        )
                async with self._admission_lock:
                    self._active_jobs = max(0, self._active_jobs - 1)
                    self._accepted_by_owner[owner] -= 1
                    if self._accepted_by_owner[owner] <= 0:
                        del self._accepted_by_owner[owner]
                self._queue.task_done()

    def _run_review_sync(
        self,
        job_id: str,
        input_path: Path,
        file_size: int,
        cancel_event: threading.Event | None = None,
        queue_wait_seconds: float = 0.0,
    ) -> None:
        """Ejecuta el flujo síncrono y respeta la cancelación entre etapas seguras."""
        try:
            logger.info("Iniciando revisión para trabajo %s (tamaño: %d bytes)", job_id, file_size)
            self.storage.update_job(job_id, status="procesando")
            start_time = time.perf_counter()
            # Reutilización de la API pública existente de revisor_crf. Ollama
            # permanece desactivado; LanguageTool sólo opera con perfil aprobado.
            editorial_override = None
            if self.config.editorial_enabled:
                from revisor_crf.editorial import EditorialConfig
                ollama_profile = None
                if self.config.ollama_enabled:
                    from revisor_crf.ollama_profile import load_ollama_profile
                    ollama_profile = load_ollama_profile(self.config.ollama_profile)
                with input_path.open("rb") as source_file:
                    source_sha256 = hashlib.file_digest(source_file, "sha256").hexdigest()
                research_allowed = self.config.research_document_allowed(source_sha256)
                ollama_active = self.config.ollama_enabled or research_allowed
                if research_allowed:
                    from revisor_crf.ollama_research import (
                        CONFIDENCE_THRESHOLD, MAX_SUGGESTIONS, MODEL_DIGEST, MODEL_ID,
                    )
                editorial_override = EditorialConfig(
                    ollama_enabled=ollama_active,
                    experimental_model=ollama_active,
                    model=(MODEL_ID if research_allowed else
                           ollama_profile.model_id if ollama_profile else "qwen3.5:4b"),
                    base_url=self.config.ollama_url,
                    timeout_seconds=self.config.ollama_timeout_seconds,
                    expected_model_digest=(
                        MODEL_DIGEST if research_allowed else
                        ollama_profile.model_digest if ollama_profile else None
                    ),
                    confidence_threshold=(CONFIDENCE_THRESHOLD if research_allowed else 0.8),
                    ollama_prompt_mode=("research_high_recall" if research_allowed else "approved"),
                    ollama_max_suggestions=(MAX_SUGGESTIONS if research_allowed else 200),
                    language_tool_enabled=self.config.language_tool_enabled,
                    language_tool_experimental=False,
                    language_tool_profile_path=(
                        str(self.config.language_tool_profile)
                        if self.config.language_tool_profile else None
                    ),
                    language_tool_url=self.config.language_tool_url,
                )
            result = review_document(
                input_path,
                mode="final",
                catalog_path=None,
                semantic=False,
                editorial=self.config.editorial_enabled,
                editorial_ollama=bool(editorial_override and editorial_override.ollama_enabled),
                editorial_experimental_model=bool(
                    editorial_override and editorial_override.experimental_model
                ),
                editorial_language_tool=self.config.language_tool_enabled,
                editorial_config_override=editorial_override,
            )

            if cancel_event and cancel_event.is_set():
                raise TimeoutError("job_timeout")

            paths = self.storage.get_output_paths(job_id)

            # Exportación de los 3 formatos solicitados (conforme a la CLI):
            # 1. Generar primero el DOCX comentado e incorporar commented_copy a result
            result["commented_copy"] = export_commented_docx(
                input_path, result, paths["docx"]
            )
            if cancel_event and cancel_event.is_set():
                raise TimeoutError("job_timeout")
            # 2. Exportar JSON y HTML después para que incluyan commented_copy
            export_json(result, paths["json"])
            export_html(result, paths["html"])

            duration = time.perf_counter() - start_time

            # Resumen técnico sin contener texto confidencial de los párrafos
            editorial_review = result.get("editorial_review") or {}
            if self.config.ollama_research_enabled and not (
                editorial_override and editorial_override.ollama_enabled
            ):
                editorial_review.setdefault("ollama", {}).update({
                    "enabled": False,
                    "experimental": True,
                    "research_mode": True,
                    "status": "skipped_not_allowlisted",
                    "errors": [],
                    "suggestions": 0,
                    "max_suggestions": 5,
                })
            language_tool = editorial_review.get("language_tool") or {}
            language_tool_profile = language_tool.get("profile") or {}
            summary = {
                "schema_version": result.get("schema_version"),
                "alerts_count": len(result.get("alerts", [])),
                "limitations_count": len(result.get("limitations", [])),
                "warnings_count": len(result.get("warnings", [])),
                "rules_executed": result.get("rules_executed", []),
                "by_rule": result.get("summary", {}).get("by_rule", {}),
                "by_severity": result.get("summary", {}).get("by_severity", {}),
                "limitations_by_rule": result.get("summary", {}).get("limitations_by_rule", {}),
                "evaluated": result.get("summary", {}).get("evaluated", 0),
                "excluded": result.get("summary", {}).get("excluded", 0),
                "sha256": result.get("source", {}).get("sha256", ""),
                "duration_seconds": round(duration, 3),
                "queue_wait_seconds": round(queue_wait_seconds, 3),
                "editorial_findings_count": len(editorial_review.get("findings", [])),
                "language_tool": {
                    "enabled": bool(language_tool.get("enabled")),
                    "status": language_tool.get("status", "disabled"),
                    "provider_version": "6.6" if language_tool.get("enabled") else None,
                    "profile_version": language_tool_profile.get("profile_version"),
                    "duration_seconds": language_tool.get("duration_seconds", 0.0),
                    "calls": language_tool.get("calls", 0),
                    "errors_count": len(language_tool.get("errors") or []),
                },
                "ollama": {
                    "enabled": bool((editorial_review.get("ollama") or {}).get("enabled")),
                    "status": (editorial_review.get("ollama") or {}).get("status", "disabled"),
                    "model": ((editorial_review.get("ollama") or {}).get("model") or {}).get("model_id"),
                    "duration_seconds": (editorial_review.get("ollama") or {}).get("duration_seconds", 0.0),
                    "errors_count": len((editorial_review.get("ollama") or {}).get("errors") or []),
                    "research_mode": bool((editorial_review.get("ollama") or {}).get("research_mode")),
                    "suggestions_count": (editorial_review.get("ollama") or {}).get("suggestions", 0),
                    "max_suggestions": (editorial_review.get("ollama") or {}).get("max_suggestions"),
                    "document_scope": (
                        "all_test_documents"
                        if self.config.ollama_research_allow_all_documents
                        else "allowlisted_synthetic"
                    ) if self.config.ollama_research_enabled else None,
                },
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
            duration = time.perf_counter() - locals().get("start_time", time.perf_counter())
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
