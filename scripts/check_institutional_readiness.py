"""Valida la compuerta institucional previa a SQL Server y producción."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "institutional-readiness-1.0"
APPROVALS = ("it", "cybersecurity", "privacy", "records_management")


def evaluate_readiness(data: dict) -> dict:
    blockers: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        blockers.append(f"schema_version debe ser {SCHEMA_VERSION}")

    approvals = data.get("approvals") or {}
    for name in APPROVALS:
        if approvals.get(name) is not True:
            blockers.append(f"falta aprobación formal: {name}")

    sql = data.get("sql_server") or {}
    for key in ("version", "database", "auth_mode"):
        if not str(sql.get(key) or "").strip():
            blockers.append(f"falta sql_server.{key}")
    if sql.get("tls_certificate_validated") is not True:
        blockers.append("SQL Server no tiene TLS institucional validado")
    if sql.get("odbc_driver_18") is not True:
        blockers.append("ODBC Driver 18 no está confirmado")

    identity = data.get("identity") or {}
    if identity.get("mode") != "wia":
        blockers.append("identity.mode debe ser wia para este despliegue")
    if identity.get("required_attributes_confirmed") is not True:
        blockers.append("no están confirmados username, nombre y correo")
    if identity.get("role_mapping_confirmed") is not True:
        blockers.append("no está confirmado el mapeo de roles")
    if identity.get("retention_approved") is not True:
        blockers.append("la política de retención no está aprobada")

    perimeter = data.get("perimeter") or {}
    if perimeter.get("proxy") != "iis":
        blockers.append("perimeter.proxy debe ser iis")
    for key, message in (
        ("anti_spoofing_confirmed", "IIS no tiene anti-spoofing confirmado"),
        ("https_certificate_assigned", "el certificado HTTPS no está asignado"),
        ("multipart_25mb_allowed", "el proxy/WAF no confirma cargas de 25 MB"),
        ("timeout_120s_allowed", "el proxy/WAF no confirma timeout de 120 s"),
    ):
        if perimeter.get(key) is not True:
            blockers.append(message)

    storage = data.get("storage") or {}
    if not str(storage.get("jobs_path") or "").strip():
        blockers.append("falta storage.jobs_path")
    try:
        free_gb = float(storage.get("free_gb", 0))
    except (TypeError, ValueError):
        free_gb = 0
    if free_gb < 20:
        blockers.append("el almacenamiento efímero debe tener al menos 20 GB libres")
    if storage.get("antivirus_reviewed") is not True:
        blockers.append("falta revisión de antivirus/EDR para la carpeta temporal")

    return {
        "schema_version": SCHEMA_VERSION,
        "ready_for_sql_implementation": not blockers,
        "ready_for_production": not blockers,
        "blockers": blockers,
        "blocker_count": len(blockers),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("responses", help="JSON de respuestas y aprobaciones institucionales")
    parser.add_argument("--output", help="Ruta opcional para guardar el dictamen JSON")
    args = parser.parse_args(argv)
    try:
        source = Path(args.responses)
        data = json.loads(source.read_text(encoding="utf-8"))
        result = evaluate_readiness(data)
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    if result["ready_for_production"]:
        print("Compuerta institucional aprobada: puede iniciar la implementación SQL.")
        return 0
    print(f"Compuerta pendiente: {result['blocker_count']} bloqueo(s).")
    for blocker in result["blockers"]:
        print(f"- {blocker}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
