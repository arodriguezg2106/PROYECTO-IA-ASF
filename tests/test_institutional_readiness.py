from check_institutional_readiness import evaluate_readiness


def _ready():
    return {
        "schema_version": "institutional-readiness-1.0",
        "approvals": {"it": True, "cybersecurity": True, "privacy": True, "records_management": True},
        "sql_server": {
            "version": "2022",
            "database": "BD_AUDITORIA_CRF",
            "auth_mode": "gMSA",
            "tls_certificate_validated": True,
            "odbc_driver_18": True,
        },
        "identity": {
            "mode": "wia",
            "required_attributes_confirmed": True,
            "role_mapping_confirmed": True,
            "retention_approved": True,
        },
        "perimeter": {
            "proxy": "iis",
            "anti_spoofing_confirmed": True,
            "https_certificate_assigned": True,
            "multipart_25mb_allowed": True,
            "timeout_120s_allowed": True,
        },
        "storage": {
            "jobs_path": "D:/runtime/jobs",
            "free_gb": 20,
            "antivirus_reviewed": True,
        },
    }


def test_complete_gate_allows_sql_and_production():
    result = evaluate_readiness(_ready())
    assert result["ready_for_sql_implementation"] is True
    assert result["ready_for_production"] is True
    assert result["blockers"] == []


def test_incomplete_gate_lists_all_material_blockers():
    data = _ready()
    data["approvals"]["privacy"] = False
    data["perimeter"]["anti_spoofing_confirmed"] = False
    data["storage"]["free_gb"] = 19.9
    result = evaluate_readiness(data)
    assert result["ready_for_production"] is False
    assert result["blocker_count"] == 3
    assert any("privacy" in item for item in result["blockers"])
    assert any("anti-spoofing" in item for item in result["blockers"])
    assert any("20 GB" in item for item in result["blockers"])
