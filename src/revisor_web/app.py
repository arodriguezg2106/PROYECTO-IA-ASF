"""Aplicación FastAPI y endpoints REST de la web interna de revisor-crf."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from .config import WebConfig, config as default_config
from .service import ReviewService, ServerBusyError
from .storage import JobStorage
from .telemetry import PilotTelemetry
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


ALLOWED_DECISION_STATUSES = {
    "confirmed",
    "rejected",
    "not_evaluable",
    "audit_team_review",
}


class FindingDecision(BaseModel):
    """Decision humana; nunca modifica el hallazgo ni el documento."""

    status: str
    comment: str | None = Field(default=None, max_length=500)


def _validated_identity(raw_identity: str | None) -> str | None:
    if raw_identity is None:
        return None
    identity = raw_identity.strip()
    if not identity or len(identity) > 256 or "," in identity:
        return None
    if not re.fullmatch(r"[A-Za-z0-9._@\\\-]+", identity):
        return None
    return identity.casefold()


def _is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.casefold() == "localhost"


def create_app(cfg: WebConfig | None = None) -> FastAPI:
    """Fábrica de la aplicación web interna."""
    app_config = cfg or default_config
    if app_config.demo_mode and not _is_loopback_host(app_config.host):
        raise ValueError("El modo demo sólo puede configurarse en un host loopback.")
    demo_identity = _validated_identity(app_config.demo_identity)
    if app_config.demo_mode and demo_identity is None:
        raise ValueError("La identidad del modo demo no es válida.")
    storage = JobStorage(app_config.jobs_dir)
    telemetry = PilotTelemetry()
    service = ReviewService(app_config, storage, telemetry)

    cleanup_task: asyncio.Task | None = None

    async def _periodic_cleanup_loop():
        while True:
            try:
                await asyncio.sleep(app_config.cleanup_interval_seconds)
                deleted = storage.cleanup_expired_jobs(app_config.job_ttl_seconds)
                if deleted:
                    telemetry.record("job_purged", count=len(deleted))
                    logger.info("Limpieza por TTL: eliminados %d trabajos expirados", len(deleted))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error durante ciclo de limpieza: %s", type(exc).__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        recovered = storage.recover_interrupted_jobs()
        if recovered:
            telemetry.record("job_recovered", status="fallido", count=len(recovered))
            logger.warning("Recuperacion inicial: marcados como fallidos %d trabajos interrumpidos", len(recovered))
        deleted = storage.cleanup_expired_jobs(app_config.job_ttl_seconds)
        if deleted:
            telemetry.record("job_purged", count=len(deleted))
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
    app.state.telemetry = telemetry

    templates_dir = Path(__file__).parent / "templates"
    index_html_path = templates_dir / "index.html"

    @app.middleware("http")
    async def authentication_and_security_headers(request: Request, call_next):
        """Confia en WIA solo cuando la conexion procede del proxy configurado."""
        is_public_asset = request.url.path in ("/api/health", "/favicon.ico") or request.url.path.startswith("/static/")
        if not is_public_asset and app_config.demo_mode:
            # El modo demo sólo puede crearse con host loopback y no confía en
            # ninguna identidad proporcionada por el navegador.
            peer = request.client.host if request.client else ""
            if not _is_loopback_host(peer):
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "La demostración sólo admite conexiones locales."},
                )
            else:
                request.state.identity = demo_identity
                response = await call_next(request)
                response.headers["X-Revisor-Demo"] = "local-only"
        elif not is_public_asset:
            peer = request.client.host if request.client else ""
            raw_identity = request.headers.get(app_config.identity_header)
            if peer not in app_config.trusted_proxy_hosts:
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "La solicitud no procede de un proxy confiable."},
                )
            else:
                identity = _validated_identity(raw_identity)
                if identity is None:
                    response = JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Se requiere identidad institucional autenticada."},
                        headers={"WWW-Authenticate": "Negotiate"},
                    )
                else:
                    request.state.identity = identity
                    response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'",
        )
        return response

    def _owned_job(job_id: str, identity: str) -> dict:
        meta = storage.get_job(job_id)
        if not meta or meta.get("owner") != identity:
            # 404 evita revelar a otro usuario que el UUID existe.
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajo no encontrado.")
        return meta

    @app.get("/", response_class=HTMLResponse)
    async def index_view():
        """Página principal de la interfaz accesible."""
        if not index_html_path.exists():
            raise HTTPException(status_code=500, detail="Plantilla no encontrada.")
        content = index_html_path.read_text(encoding="utf-8")
        banner = ""
        if app_config.demo_mode:
            banner = (
                '<div class="alert alert-warning" role="status">'
                '<strong>Demostración local:</strong> acceso limitado a esta computadora; '
                'sin SQL Server, Ollama ni servicios externos.'
                '</div>'
            )
        return HTMLResponse(content=content.replace("<!-- DEMO_BANNER -->", banner))

    static_dir = Path(__file__).parent / "static"

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        fav_path = static_dir / "favicon.ico"
        if fav_path.exists():
            return FileResponse(fav_path, media_type="image/x-icon")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/static/logo_asf.png", include_in_schema=False)
    async def logo_asf():
        logo_path = static_dir / "logo_asf_128.png"
        if not logo_path.exists():
            logo_path = static_dir / "logo_asf.png"
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

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
    async def create_job(request: Request, file: UploadFile = File(...)):
        """Carga un documento DOCX, valida su integridad y encola la revisión determinística."""
        if service.is_saturated:
            telemetry.record("job_saturated", identity=request.state.identity, status="rechazado")
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

        meta = storage.create_job(safe_filename, bytes_read, owner=request.state.identity)
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
        telemetry.record("job_uploaded", job_id=job_id, identity=request.state.identity, status="recibido")
        return {
            "job_id": job_id,
            "status": "recibido",
            "original_filename": safe_filename,
            "file_size": bytes_read,
            "created_at": meta["created_at"],
        }

    @app.get("/api/jobs/{job_id}")
    async def get_job_status(job_id: str, request: Request):
        """Consulta el estado actual, métricas o error de un trabajo."""
        meta = _owned_job(job_id, request.state.identity)
        telemetry.record(
            "job_status_viewed", job_id=job_id, identity=request.state.identity, status=meta.get("status")
        )
        return meta

    @app.get("/api/jobs/{job_id}/download/{artifact}")
    async def download_artifact(job_id: str, artifact: str, request: Request):
        """Descarga los entregables generados (json, html, docx)."""
        artifact_lower = artifact.lower()
        if artifact_lower not in {"json", "html", "docx"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de archivo no válido.")

        meta = _owned_job(job_id, request.state.identity)

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

        telemetry.record(
            "artifact_downloaded", job_id=job_id, identity=request.state.identity, status=artifact_lower
        )

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=download_name,
        )

    @app.get("/api/jobs/{job_id}/view/html", response_class=HTMLResponse)
    async def view_html_report(job_id: str, request: Request):
        """Permite visualizar en el navegador el reporte interactivo.

        Aplica una política estricta de aislamiento (connect-src 'none')
        que impide que scripts internos del reporte ejecuten llamadas de red
        hacia otros endpoints o servicios externos.
        """
        meta = _owned_job(job_id, request.state.identity)

        if meta.get("status") != "terminado":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El reporte aún no está disponible.",
            )

        file_path = storage.get_artifact_path(job_id, "html")
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado.")

        html_content = file_path.read_text(encoding="utf-8")
        telemetry.record("report_viewed", job_id=job_id, identity=request.state.identity, status="html")
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

    @app.post("/api/jobs/{job_id}/findings/{finding_id}/decision")
    async def save_finding_decision(
        job_id: str, finding_id: str, payload: FindingDecision, request: Request
    ):
        """Registra una decision del propietario sin alterar la evidencia original."""
        _owned_job(job_id, request.state.identity)
        if payload.status not in ALLOWED_DECISION_STATUSES:
            raise HTTPException(status_code=422, detail="Estado de decision no permitido.")

        report_path = storage.get_artifact_path(job_id, "json")
        if report_path is None:
            raise HTTPException(status_code=409, detail="Los hallazgos aun no estan disponibles.")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise HTTPException(status_code=500, detail="No se pudo validar el hallazgo.")
        valid_ids = {
            item.get("id")
            for key in ("alerts", "editorial_findings", "semantic_suggestions")
            for item in report.get(key, [])
            if isinstance(item, dict) and item.get("id")
        }
        if finding_id not in valid_ids:
            raise HTTPException(status_code=404, detail="Hallazgo no encontrado.")
        try:
            record = storage.save_decision(
                job_id,
                finding_id,
                {
                    "status": payload.status,
                    "comment": payload.comment,
                    "reviewer": request.state.identity,
                },
            )
        except (OSError, ValueError):
            raise HTTPException(status_code=500, detail="No se pudo guardar la decision.")
        telemetry.record(
            "decision_saved", job_id=job_id, identity=request.state.identity, status=payload.status
        )
        return record

    return app


app = create_app()
