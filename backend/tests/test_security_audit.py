"""Unit tests for the Python security scanner (scripts/security_audit.py).

Verifies fail-closed behavior on:
- Execution failures and non-zero exit codes with no output
- Empty stdout or malformed JSON
- Missing expected schema fields
- Direct critical vulnerability detection (CVSS >= 9.0 or CRITICAL rating)
- Fail-safe rejection when reliable severity information is unavailable
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.security_audit import (
    audit_python_requirements,
    extract_cvss_score_from_vector,
    resolve_vulnerability_severity,
)


def test_audit_requirements_file_not_found_fails_closed(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.txt"
    code, findings = audit_python_requirements(non_existent)
    assert code == 1
    assert findings == []


def test_audit_subprocess_execution_failure_fails_closed(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi==0.111.0\n", encoding="utf-8")

    with patch("subprocess.run", side_effect=FileNotFoundError("pip-audit not installed")):
        code, findings = audit_python_requirements(req_file)
        assert code == 1
        assert findings == []


def test_audit_empty_output_fails_closed(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi==0.111.0\n", encoding="utf-8")

    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "Fatal error in pip_audit"

    with patch("subprocess.run", return_value=mock_proc):
        code, findings = audit_python_requirements(req_file)
        assert code == 1
        assert findings == []


def test_audit_invalid_json_fails_closed(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi==0.111.0\n", encoding="utf-8")

    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = "This is plain text, not JSON"
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        code, findings = audit_python_requirements(req_file)
        assert code == 1
        assert findings == []


def test_audit_missing_dependencies_key_fails_closed(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("fastapi==0.111.0\n", encoding="utf-8")

    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({"unexpected_key": []})
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        code, findings = audit_python_requirements(req_file)
        assert code == 1
        assert findings == []


def test_audit_direct_critical_vulnerability_detected(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("vulnerable-pkg==1.0.0\n", encoding="utf-8")

    payload = {
        "dependencies": [
            {
                "name": "vulnerable-pkg",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "GHSA-crit-0001",
                        "severity": "CRITICAL",
                        "description": "Remote arbitrary code execution",
                        "fix_versions": ["1.0.1"],
                    }
                ],
            }
        ]
    }

    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 1
    mock_proc.stdout = json.dumps(payload)
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        code, findings = audit_python_requirements(req_file)
        assert code == 1
        assert len(findings) == 1
        assert findings[0]["id"] == "GHSA-crit-0001"
        assert findings[0]["severity"] == "CRITICAL"


def test_audit_unreliable_severity_fails_safely(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("unknown-pkg==1.0.0\n", encoding="utf-8")

    payload = {
        "dependencies": [
            {
                "name": "unknown-pkg",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "UNKNOWN-VULN-999",
                        "description": "Some vulnerability without severity",
                        "fix_versions": ["1.0.1"],
                    }
                ],
            }
        ]
    }

    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 1
    mock_proc.stdout = json.dumps(payload)
    mock_proc.stderr = ""

    with (
        patch("subprocess.run", return_value=mock_proc),
        patch("scripts.security_audit.fetch_osv_record", return_value=None),
    ):
        code, findings = audit_python_requirements(req_file)
        # Fails safely because severity is unverifiable
        assert code == 1
        assert len(findings) == 1
        assert findings[0]["id"] == "UNKNOWN-VULN-999"


def test_audit_non_critical_severity_passes(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("moderate-pkg==1.0.0\n", encoding="utf-8")

    payload = {
        "dependencies": [
            {
                "name": "moderate-pkg",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "GHSA-mod-0001",
                        "severity": "MODERATE",
                        "description": "Mild information disclosure",
                        "fix_versions": ["1.0.1"],
                    }
                ],
            }
        ]
    }

    mock_proc = MagicMock(spec=subprocess.CompletedProcess)
    mock_proc.returncode = 1
    mock_proc.stdout = json.dumps(payload)
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        code, findings = audit_python_requirements(req_file)
        assert code == 0
        assert findings == []


def test_extract_cvss_score_and_resolution() -> None:
    crit_vec = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    score = extract_cvss_score_from_vector(crit_vec)
    assert score is not None
    assert score >= 9.0

    sev, is_reliable = resolve_vulnerability_severity(
        {
            "id": "TEST-1",
            "severity": [{"type": "CVSS_V3", "score": crit_vec}],
        }
    )
    assert sev == "CRITICAL"
    assert is_reliable is True
