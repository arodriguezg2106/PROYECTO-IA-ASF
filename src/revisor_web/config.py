"""Configuración y límites operativos de la web interna de revisor-crf."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class WebConfig:
    """Parámetros de configuración del servicio web."""

    # Red y enlace de escucha: solo 127.0.0.1 por defecto
    host: str = os.getenv("REVISOR_WEB_HOST", "127.0.0.1")
    port: int = int(os.getenv("REVISOR_WEB_PORT", "8000"))

    # Límites de carga de archivo (25 MB por defecto)
    max_file_size_mb: int = int(os.getenv("REVISOR_WEB_MAX_FILE_SIZE_MB", "25"))

    # Ciclo de vida y limpieza (TTL de 30 minutos por defecto)
    job_ttl_seconds: int = int(os.getenv("REVISOR_WEB_JOB_TTL_SECONDS", "1800"))
    cleanup_interval_seconds: int = int(os.getenv("REVISOR_WEB_CLEANUP_INTERVAL_SECONDS", "60"))

    # Concurrencia acotada para proteger CPU y memoria del servidor
    max_concurrent_jobs: int = int(os.getenv("REVISOR_WEB_MAX_CONCURRENT_JOBS", "2"))
    max_queue_size: int = int(os.getenv("REVISOR_WEB_MAX_QUEUE_SIZE", "4"))

    # La identidad solo puede ser inyectada por el proxy inverso conectado
    # directamente al backend. No se confia en esta cabecera desde clientes de red.
    identity_header: str = os.getenv(
        "REVISOR_WEB_IDENTITY_HEADER",
        os.getenv("CRF_PROXY_USER_HEADER", "X-Forwarded-User"),
    )
    trusted_proxy_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            host.strip()
            for host in os.getenv(
                "REVISOR_WEB_TRUSTED_PROXY_HOSTS",
                os.getenv("CRF_TRUSTED_PROXY_IPS", "127.0.0.1,::1"),
            ).split(",")
            if host.strip()
        )
    )

    # Directorio de almacenamiento temporal de trabajos
    # Por defecto se utiliza un directorio seguro y excluido por .gitignore
    jobs_dir: Path = Path(
        os.getenv(
            "REVISOR_WEB_JOBS_DIR",
            str(Path("tmp/revisor_web_jobs").resolve()),
        )
    )

    # Integración futura de Ollama: estrictamente interna desde el backend
    # En este MVP permanece desactivada y NUNCA se expone a la red ni al navegador.
    ollama_future_integration_enabled: bool = False

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


config = WebConfig()
