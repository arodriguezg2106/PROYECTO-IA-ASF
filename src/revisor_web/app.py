"""Aplicación FastAPI y endpoints REST de la web interna de revisor-crf."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse

from .config import WebConfig, config as default_config
from .service import ReviewService, ServerBusyError
from .storage import JobStorage
from .validation import (
    CorruptDocumentError,
    FileTooLargeError,
    InvalidExtensionError,
    InvalidSignatureError,
    ValidationError,
    validate_docx_archive,
    validate_filename,
    validate_header_signature,
)

# Configuración de registro: Cero texto documental en logs
logger = logging.getLogger("revisor_web")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [revisor_web] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def create_app(cfg: WebConfig | None = None) -> FastAPI:
    """Fábrica de la aplicación web interna."""
    app_config = cfg or default_config
    storage = JobStorage(app_config.jobs_dir)
    service = ReviewService(app_config, storage)

    cleanup_task: asyncio.Task | None = None

    async def _periodic_cleanup_loop():
        while True:
            try:
                await asyncio.sleep(app_config.cleanup_interval_seconds)
                deleted = storage.cleanup_expired_jobs(app_config.job_ttl_seconds)
                if deleted:
                    logger.info("Limpieza por TTL: eliminados %d trabajos expirados", len(deleted))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error durante ciclo de limpieza: %s", type(exc).__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        deleted = storage.cleanup_expired_jobs(app_config.job_ttl_seconds)
        if deleted:
            logger.info("Limpieza inicial: eliminados %d trabajos previos", len(deleted))

        nonlocal cleanup_task
        cleanup_task = asyncio.create_task(_periodic_cleanup_loop())
        logger.info(
            "Servidor web interno iniciado en http://%s:%d (TTL trabajos: %ds, concurrencia máx: %d)",
            app_config.host,
            app_config.port,
            app_config.job_ttl_seconds,
            app_config.max_concurrent_jobs,
        )

        yield

        if cleanup_task and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Servidor web interno detenido.")

    app = FastAPI(
        title="Revisor CRF · Web Interna",
        version="0.1.0",
        description="Interfaz centralizada para la revisión determinística de documentos Word CRF",
        lifespan=lifespan,
    )

    app.state.config = app_config
    app.state.storage = storage
    app.state.service = service

    templates_dir = Path(__file__).parent / "templates"
    index_html_path = templates_dir / "index.html"

    @app.get("/", response_class=HTMLResponse)
    async def index_view():
        """Página principal de la interfaz accesible."""
        if not index_html_path.exists():
            raise HTTPException(status_code=500, detail="Plantilla no encontrada.")
        return HTMLResponse(content=index_html_path.read_text(encoding="utf-8"))

    @app.get("/api/health")
    async def health_check():
        """Estado técnico del servicio."""
        return {
            "status": "ok",
            "version": "0.1.0",
            "host": app_config.host,
            "port": app_config.port,
            "max_concurrent_jobs": app_config.max_concurrent_jobs,
            "max_file_size_mb": app_config.max_file_size_mb,
            "job_ttl_seconds": app_config.job_ttl_seconds,
        }

    @app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
    async def create_job(file: UploadFile = File(...)):
        """Carga un documento DOCX, valida su integridad y encola la revisión determinística."""
        if service.is_saturated:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El servidor se encuentra saturado. Por favor intente más tarde.",
                headers={"Retry-After": "10"},
            )

        try:
            safe_filename = validate_filename(file.filename)
        except InvalidExtensionError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        content_chunks = []
        bytes_read = 0
        max_bytes = app_config.max_file_size_bytes

        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"El archivo excede el límite máximo de {app_config.max_file_size_mb} MB.",
                )
            content_chunks.append(chunk)

        content = b"".join(content_chunks)

        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo proporcionado está vacío.",
            )

        try:
            validate_header_signature(content[:16])
        except InvalidSignatureError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        meta = storage.create_job(safe_filename, bytes_read)
        job_id = meta["job_id"]
        input_path = storage.save_input_file(job_id, content)

        try:
            validate_docx_archive(input_path)
            service.enqueue_job(job_id, input_path, bytes_read)
        except ValidationError as exc:
            storage.delete_job(job_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except ServerBusyError as exc:
            storage.delete_job(job_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
                headers={"Retry-After": "10"},
            )
        except Exception:
            storage.delete_job(job_id)
            raise

        logger.info("Trabajo recibido y encolado: %s (tamaño: %d bytes)", job_id, bytes_read)
        return {
            "job_id": job_id,
            "status": "recibido",
            "original_filename": safe_filename,
            "file_size": bytes_read,
            "created_at": meta["created_at"],
        }

    @app.get("/api/jobs/{job_id}")
    async def get_job_status(job_id: str):
        """Consulta el estado actual, métricas o error de un trabajo."""
        meta = storage.get_job(job_id)
        if not meta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajo no encontrado.")
        return meta

    @app.get("/api/jobs/{job_id}/download/{artifact}")
    async def download_artifact(job_id: str, artifact: str):
        """Descarga los entregables generados (json, html, docx)."""
        artifact_lower = artifact.lower()
        if artifact_lower not in {"json", "html", "docx"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de archivo no válido.")

        meta = storage.get_job(job_id)
        if not meta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajo no encontrado.")

        if meta.get("status") != "terminado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El trabajo aún no ha terminado (estado: {meta.get('status')}).",
            )

        file_path = storage.get_artifact_path(job_id, artifact_lower)
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado.")

        short_id = job_id[:8]
        if artifact_lower == "json":
            media_type = "application/json"
            download_name = f"revision_{short_id}.json"
        elif artifact_lower == "html":
            media_type = "text/html; charset=utf-8"
            download_name = f"revision_{short_id}.html"
        else:
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            download_name = f"revision_{short_id}_comentada.docx"

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=download_name,
        )

    @app.get("/api/jobs/{job_id}/view/html", response_class=HTMLResponse)
    async def view_html_report(job_id: str):
        """Permite visualizar en el navegador el reporte interactivo.

        Aplica una política estricta de aislamiento (connect-src 'none')
        que impide que scripts internos del reporte ejecuten llamadas de red
        hacia otros endpoints o servicios externos.
        """
        meta = storage.get_job(job_id)
        if not meta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajo no encontrado.")

        if meta.get("status") != "terminado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El reporte aún no está disponible.",
            )

        file_path = storage.get_artifact_path(job_id, "html")
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado.")

        html_content = file_path.read_text(encoding="utf-8")
        headers = {
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'none'; img-src 'none'; object-src 'none'; form-action 'none'; "
                "base-uri 'none'; frame-ancestors 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
        }
        return HTMLResponse(content=html_content, headers=headers)

    return app


app = create_app()

