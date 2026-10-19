"""Configuración y límites operativos de la web interna de revisor-crf."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


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
    max_jobs_per_user: int = int(os.getenv("REVISOR_WEB_MAX_JOBS_PER_USER", "2"))
    job_timeout_seconds: int = int(os.getenv("REVISOR_WEB_JOB_TIMEOUT_SECONDS", "120"))
    upload_rate_limit_per_minute: int = int(
        os.getenv("REVISOR_WEB_UPLOAD_RATE_LIMIT_PER_MINUTE", "6")
    )
    decision_rate_limit_per_minute: int = int(
        os.getenv("REVISOR_WEB_DECISION_RATE_LIMIT_PER_MINUTE", "60")
    )

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
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            value.strip().rstrip("/")
            for value in os.getenv("REVISOR_WEB_ALLOWED_ORIGINS", "").split(",")
            if value.strip()
        )
    )

    # Exclusivo para demostración presencial en la misma computadora. La
    # aplicación rechaza este modo si el host configurado no es loopback.
    demo_mode: bool = _env_bool("REVISOR_WEB_DEMO_MODE")
    demo_identity: str = os.getenv("REVISOR_WEB_DEMO_IDENTITY", "demo.local")

    # Directorio de almacenamiento temporal de trabajos
    # Por defecto se utiliza un directorio seguro y excluido por .gitignore
    jobs_dir: Path = Path(
        os.getenv(
            "REVISOR_WEB_JOBS_DIR",
            str(Path("tmp/revisor_web_jobs").resolve()),
        )
    )

    # Revisión editorial central. LanguageTool requiere lista blanca aprobada y
    # queda desactivado hasta superar su compuerta reproducible.
    editorial_enabled: bool = _env_bool("REVISOR_WEB_EDITORIAL_ENABLED")
    language_tool_enabled: bool = _env_bool("REVISOR_WEB_LANGUAGETOOL_ENABLED")
    language_tool_profile: Path | None = (
        Path(os.environ["REVISOR_WEB_LANGUAGETOOL_PROFILE"])
        if os.getenv("REVISOR_WEB_LANGUAGETOOL_PROFILE") else None
    )
    language_tool_url: str = os.getenv(
        "REVISOR_WEB_LANGUAGETOOL_URL", "http://127.0.0.1:8081/v2"
    )

    # Ollama es opcional y requiere un perfil emitido por la compuerta de
    # evaluación. Un perfil sólo sintético se limita al modo demostración.
    ollama_enabled: bool = _env_bool("REVISOR_WEB_OLLAMA_ENABLED")
    ollama_url: str = os.getenv("REVISOR_WEB_OLLAMA_URL", "http://127.0.0.1:11434/api")
    ollama_model: str = os.getenv("REVISOR_WEB_OLLAMA_MODEL", "")
    ollama_profile: Path | None = (
        Path(os.environ["REVISOR_WEB_OLLAMA_PROFILE"])
        if os.getenv("REVISOR_WEB_OLLAMA_PROFILE") else None
    )
    ollama_timeout_seconds: float = float(
        os.getenv("REVISOR_WEB_OLLAMA_TIMEOUT_SECONDS", "120")
    )

    def __post_init__(self) -> None:
        if min(
            self.max_concurrent_jobs,
            self.max_jobs_per_user,
            self.job_timeout_seconds,
            self.upload_rate_limit_per_minute,
            self.decision_rate_limit_per_minute,
        ) < 1 or self.max_queue_size < 0:
            raise ValueError("Los límites operativos web deben ser positivos.")
        if not self.trusted_proxy_hosts or any(
            value in {"*", "0.0.0.0", "::"} for value in self.trusted_proxy_hosts
        ):
            raise ValueError("La lista de proxies confiables no admite comodines.")
        if self.language_tool_enabled and self.ollama_enabled:
            raise ValueError("Sólo puede activarse un proveedor lingüístico a la vez.")
        if self.language_tool_enabled:
            if not self.editorial_enabled:
                raise ValueError("LanguageTool web requiere revisión editorial habilitada.")
            if self.max_concurrent_jobs != 1:
                raise ValueError("LanguageTool web requiere REVISOR_WEB_MAX_CONCURRENT_JOBS=1.")
            if self.language_tool_profile is None:
                raise ValueError("LanguageTool web requiere un perfil aprobado.")
            from revisor_crf.language_tool import LanguageToolProvider
            from revisor_crf.language_tool_profile import load_language_tool_profile
            LanguageToolProvider(self.language_tool_url)
            load_language_tool_profile(self.language_tool_profile)
        if self.ollama_enabled:
            if not self.editorial_enabled:
                raise ValueError("Ollama web requiere revisión editorial habilitada.")
            if self.max_concurrent_jobs != 1:
                raise ValueError("Ollama web requiere REVISOR_WEB_MAX_CONCURRENT_JOBS=1.")
            if self.ollama_profile is None:
                raise ValueError("Ollama web requiere un perfil de evaluación válido.")
            from revisor_crf.ollama_profile import load_ollama_profile
            profile = load_ollama_profile(self.ollama_profile)
            if self.ollama_model and self.ollama_model != profile.model_id:
                raise ValueError("El modelo configurado no coincide con el perfil de Ollama.")
            if profile.synthetic_only and not self.demo_mode:
                raise ValueError("Un perfil sintético de Ollama sólo puede usarse en modo demostración.")
            from revisor_crf.semantic import SemanticConfig
            SemanticConfig(
                base_url=self.ollama_url,
                model=profile.model_id,
                timeout_seconds=self.ollama_timeout_seconds,
            ).validate()

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


config = WebConfig()
