"""Configuración y límites operativos de la web interna de revisor-crf."""

from __future__ import annotations

import ipaddress
import os
import re
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
    # Demostración temporal entre equipos de la misma red privada. El código
    # se conserva únicamente como hash durante la vida del proceso.
    lan_demo_mode: bool = _env_bool("REVISOR_WEB_LAN_DEMO_MODE")
    lan_demo_access_code_sha256: str = os.getenv(
        "REVISOR_WEB_LAN_ACCESS_CODE_SHA256", ""
    ).strip().lower()
    lan_demo_session_ttl_seconds: int = int(
        os.getenv("REVISOR_WEB_LAN_SESSION_TTL_SECONDS", "7200")
    )

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
    # Modo separado para mostrar el modelo rechazado como asistente de alta
    # cobertura. Sólo admite los hashes sintéticos generados para esta demo.
    ollama_research_enabled: bool = _env_bool("REVISOR_WEB_OLLAMA_RESEARCH_ENABLED")
    ollama_research_allow_all_documents: bool = _env_bool(
        "REVISOR_WEB_OLLAMA_RESEARCH_ALLOW_ALL_DOCUMENTS"
    )
    ollama_research_allowed_sha256: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            value.strip().lower()
            for value in os.getenv(
                "REVISOR_WEB_OLLAMA_RESEARCH_ALLOWED_SHA256", ""
            ).split(",")
            if value.strip()
        )
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
        if self.demo_mode and self.lan_demo_mode:
            raise ValueError("Los modos de demostración local y LAN son excluyentes.")
        if self.lan_demo_mode:
            try:
                listen_ip = ipaddress.ip_address(self.host)
            except ValueError as exc:
                raise ValueError("La demo LAN requiere una dirección IP privada explícita.") from exc
            if not listen_ip.is_private or listen_ip.is_loopback or listen_ip.is_unspecified:
                raise ValueError("La demo LAN requiere una dirección IP privada no loopback.")
            if not re.fullmatch(r"[0-9a-f]{64}", self.lan_demo_access_code_sha256):
                raise ValueError("La demo LAN requiere el hash SHA-256 de un código temporal.")
            if self.lan_demo_session_ttl_seconds < 60:
                raise ValueError("La sesión de demo LAN debe durar al menos 60 segundos.")
        if self.language_tool_enabled and (self.ollama_enabled or self.ollama_research_enabled):
            raise ValueError("Sólo puede activarse un proveedor lingüístico a la vez.")
        if self.ollama_enabled and self.ollama_research_enabled:
            raise ValueError("El Ollama aprobado y el asistente experimental son excluyentes.")
        if self.ollama_research_allow_all_documents and not self.ollama_research_enabled:
            raise ValueError("La apertura experimental requiere habilitar el asistente de investigación.")
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
            if profile.synthetic_only and not (self.demo_mode or self.lan_demo_mode):
                raise ValueError("Un perfil sintético de Ollama sólo puede usarse en modo demostración.")
            from revisor_crf.semantic import SemanticConfig
            SemanticConfig(
                base_url=self.ollama_url,
                model=profile.model_id,
                timeout_seconds=self.ollama_timeout_seconds,
            ).validate()
        if self.ollama_research_enabled:
            if not (self.demo_mode or self.lan_demo_mode):
                raise ValueError("El asistente experimental sólo puede usarse en modo demostración.")
            if not self.editorial_enabled:
                raise ValueError("El asistente experimental requiere revisión editorial habilitada.")
            if self.max_concurrent_jobs != 1:
                raise ValueError("El asistente experimental requiere un solo trabajador.")
            if (
                not self.ollama_research_allow_all_documents
                and not self.ollama_research_allowed_sha256
            ) or any(
                not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in self.ollama_research_allowed_sha256
            ):
                raise ValueError("El asistente experimental requiere hashes sintéticos válidos.")
            from revisor_crf.ollama_research import MODEL_ID
            from revisor_crf.semantic import SemanticConfig
            SemanticConfig(
                base_url=self.ollama_url,
                model=MODEL_ID,
                timeout_seconds=self.ollama_timeout_seconds,
            ).validate()

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def research_document_allowed(self, sha256: str) -> bool:
        """Autoriza IA experimental por apertura explícita o huella permitida."""
        return self.ollama_research_enabled and (
            self.ollama_research_allow_all_documents
            or sha256 in self.ollama_research_allowed_sha256
        )


config = WebConfig()
