"""Carga controlada de la web con un DOCX sintético; emite sólo métricas agregadas."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx


async def run(base_url: str, document: Path, requests: int, output: Path) -> dict:
    payload = document.read_bytes()
    started = time.perf_counter()
    accepted: list[str] = []
    saturated = 0
    rate_limited = 0
    async with httpx.AsyncClient(base_url=base_url, timeout=180) as client:
        async def submit() -> None:
            nonlocal saturated, rate_limited
            response = await client.post(
                "/api/jobs",
                files={"file": ("sintetico.docx", payload, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                headers={"Origin": base_url},
            )
            if response.status_code == 202:
                accepted.append(response.json()["job_id"])
            elif response.status_code == 503:
                saturated += 1
            elif response.status_code == 429:
                rate_limited += 1
            else:
                response.raise_for_status()

        await asyncio.gather(*(submit() for _ in range(requests)))
        durations: list[float] = []
        failures = 0
        for job_id in accepted:
            job_started = time.perf_counter()
            while True:
                response = await client.get(f"/api/jobs/{job_id}")
                response.raise_for_status()
                status = response.json()["status"]
                if status in {"terminado", "fallido"}:
                    durations.append(time.perf_counter() - job_started)
                    failures += int(status == "fallido")
                    break
                await asyncio.sleep(0.25)
    ordered = sorted(durations)
    p95 = ordered[max(0, int(len(ordered) * 0.95 + 0.999) - 1)] if ordered else 0.0
    success_rate = ((len(accepted) - failures) / len(accepted)) if accepted else 0.0
    result = {
        "schema_version": "web-load-test-1.0",
        "synthetic_only": True,
        "requested": requests,
        "accepted": len(accepted),
        "saturated_503": saturated,
        "rate_limited_429": rate_limited,
        "failed": failures,
        "success_rate": round(success_rate, 4),
        "p95_seconds": round(p95, 3),
        "median_seconds": round(statistics.median(durations), 3) if durations else 0.0,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "acceptance": {"success_rate_gte_0_95": success_rate >= 0.95, "p95_lte_30": p95 <= 30},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("results/demo/load-test.json"))
    args = parser.parse_args()
    if args.requests < 1 or not args.document.is_file():
        parser.error("El documento debe existir y --requests debe ser positivo.")
    result = asyncio.run(run(args.url.rstrip("/"), args.document, args.requests, args.output))
    print(json.dumps(result, indent=2))
    return 0 if all(result["acceptance"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
