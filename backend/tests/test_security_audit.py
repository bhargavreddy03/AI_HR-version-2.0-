"""Unit tests for the Python security scanner (scripts/security_audit.py).

Verifies fail-closed behavior, authoritative CVSS v3 calculation, and severity precedence:
- Execution failures, empty stdout, invalid JSON, missing schema
- Authoritative calculation of CVSS 8.8, 9.1, 9.8 across scope, privilege, and attack vectors
- Guarantee that lower textual ratings do not override higher CVSS scores
- Guarantee that high textual ratings do not falsely inflate non-critical CVSS scores
- Fail-safe rejection when reliable severity information is unavailable
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.security_audit import (
    audit_python_requirements,
    calculate_cvss_v3_score,
    cvss_score_to_severity,
    resolve_vulnerability_severity,
)


def test_calculate_cvss_v3_score_standards_compliance() -> None:
    # 8.8: Network, Low complexity, None privileges, Required UI, Scope Unchanged, All High impacts
    vec_88 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"
    score_88 = calculate_cvss_v3_score(vec_88)
    assert score_88 == 8.8
    assert cvss_score_to_severity(score_88) == "HIGH"

    # 9.1: Network, Low complexity, None privileges, No UI, Scope Unchanged, Conf & Integ High, Avail None
    vec_91 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N"
    score_91 = calculate_cvss_v3_score(vec_91)
    assert score_91 == 9.1
    assert cvss_score_to_severity(score_91) == "CRITICAL"

    # 9.8: Network, Low complexity, None privileges, No UI, Scope Unchanged, All High impacts
    vec_98 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    score_98 = calculate_cvss_v3_score(vec_98)
    assert score_98 == 9.8
    assert cvss_score_to_severity(score_98) == "CRITICAL"

    # 9.9: Scope Changed (S:C), Low privileges (PR:L)
    vec_99 = "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H"
    score_99 = calculate_cvss_v3_score(vec_99)
    assert score_99 == 9.9
    assert cvss_score_to_severity(score_99) == "CRITICAL"

    # 8.1: High Attack Complexity (AC:H)
    vec_81 = "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H"
    score_81 = calculate_cvss_v3_score(vec_81)
    assert score_81 == 8.1
    assert cvss_score_to_severity(score_81) == "HIGH"

    # 7.2: High Privileges (PR:H)
    vec_72 = "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H"
    score_72 = calculate_cvss_v3_score(vec_72)
    assert score_72 == 7.2
    assert cvss_score_to_severity(score_72) == "HIGH"

    # 6.8: Physical Attack Vector (AV:P)
    vec_68 = "CVSS:3.1/AV:P/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    score_68 = calculate_cvss_v3_score(vec_68)
    assert score_68 == 6.8
    assert cvss_score_to_severity(score_68) == "MODERATE"


def test_cvss_precedence_over_textual_ratings() -> None:
    # Scenario A: Textual rating says 'HIGH', but CVSS vector calculates to 9.1 (CRITICAL)
    # The higher authoritative CVSS score must NOT be overridden by a lower textual label
    finding_crit = {
        "id": "GHSA-override-test-01",
        "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N"}  # 9.1
        ],
    }
    with patch(
        "scripts.security_audit.fetch_osv_record",
        return_value={"database_specific": {"severity": "HIGH"}},
    ):
        sev, reliable, score = resolve_vulnerability_severity(finding_crit)
        assert sev == "CRITICAL"
        assert reliable is True
        assert score == 9.1

    # Scenario B: Textual rating says 'CRITICAL', but CVSS vector calculates to 8.8 (HIGH)
    # The authoritative CVSS calculation must NOT be misclassified as CRITICAL
    finding_high = {
        "id": "GHSA-override-test-02",
        "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"}  # 8.8
        ],
    }
    with patch(
        "scripts.security_audit.fetch_osv_record",
        return_value={"database_specific": {"severity": "CRITICAL"}},
    ):
        sev, reliable, score = resolve_vulnerability_severity(finding_high)
        assert sev == "HIGH"
        assert reliable is True
        assert score == 8.8


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
                        "severity": [
                            {
                                "type": "CVSS_V3",
                                "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                            }  # 9.8
                        ],
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
        assert findings[0]["cvss_score"] == 9.8


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
                        "severity": [
                            {
                                "type": "CVSS_V3",
                                "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H",
                            }  # 8.8 (HIGH)
                        ],
                        "description": "Information disclosure",
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
        # 8.8 is HIGH, not CRITICAL; should pass
        assert code == 0
        assert findings == []
