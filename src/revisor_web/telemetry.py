"""Telemetria sanitaria en memoria para el piloto interno."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
import threading
from collections import Counter


class PilotTelemetry:
    """Registra eventos sin nombres de archivo, comentarios ni texto documental."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("revisor_web.audit")
        self._salt = secrets.token_bytes(32)
        self._lock = threading.Lock()
        self._events: Counter[str] = Counter()
        self._durations: list[float] = []
        self._queue_waits: list[float] = []
        self._max_queue_depth = 0

    def identity_hash(self, identity: str | None) -> str | None:
        if not identity:
            return None
        return hashlib.sha256(self._salt + identity.encode("utf-8")).hexdigest()[:16]

    def record(self, event: str, *, job_id: str | None = None,
               identity: str | None = None, status: str | None = None,
               duration_seconds: float | None = None, count: int = 1,
               queue_depth: int | None = None) -> None:
        with self._lock:
            self._events[event] += count
            if event == "job_completed" and duration_seconds is not None:
                self._durations.append(duration_seconds)
            if event == "job_started" and duration_seconds is not None:
                self._queue_waits.append(duration_seconds)
            if queue_depth is not None:
                self._max_queue_depth = max(self._max_queue_depth, queue_depth)
        payload = {
            "event": event,
            "job_id": job_id,
            "user_hash": self.identity_hash(identity),
            "status": status,
            "duration_seconds": round(duration_seconds, 3) if duration_seconds is not None else None,
            "count": count,
            "queue_depth": queue_depth,
        }
        self._logger.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))

    def snapshot(self) -> dict:
        with self._lock:
            events = dict(self._events)
            durations = sorted(self._durations)
            queue_waits = sorted(self._queue_waits)
            max_queue_depth = self._max_queue_depth
        completed = events.get("job_completed", 0)
        failed = events.get("job_failed", 0)
        total = completed + failed
        percentile_index = max(0, math.ceil(len(durations) * 0.95) - 1)
        queue_percentile_index = max(0, math.ceil(len(queue_waits) * 0.95) - 1)
        return {
            "events": events,
            "success_rate": completed / total if total else None,
            "processing_p95_seconds": durations[percentile_index] if durations else None,
            "queue_wait_p95_seconds": (
                queue_waits[queue_percentile_index] if queue_waits else None
            ),
            "max_queue_depth": max_queue_depth,
            "saturation_rejections": events.get("job_saturated", 0),
            "purged_jobs": events.get("job_purged", 0),
        }
