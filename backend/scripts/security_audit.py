"""Automated dependency vulnerability scanner and security gate.

Audits production Python requirements using pip-audit:
- Enforces fail-closed semantics on execution errors, empty output, and invalid JSON.
- Evaluates vulnerability severity using reliable security metadata from OSV / PyPA / GHSA.
- Does not rely on heuristic description keyword matching.
- Fails safely if reliable severity metadata is unavailable.
- Exits with non-zero code if critical vulnerabilities or unverifiable advisories are detected.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OSV_API_URL = "https://api.osv.dev/v1/vulns"
CVSS_SCORE_REGEX = re.compile(r"/AV:[NALP]/AC:[LH]/PR:[NLH]/UI:[NR]/S:[UC]/C:[NLH]/I:[NLH]/A:[NLH]")


def extract_cvss_score_from_vector(vector: str) -> float | None:
    """Extract or estimate CVSS v3 score from a CVSS vector string."""
    # Common high/critical indicator check in vector
    # E.g., CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H has base score 9.8 (CRITICAL)
    if "C:H/I:H/A:H" in vector and ("PR:N" in vector or "PR:L" in vector) and "AC:L" in vector:
        return 9.8
    if "C:H/I:H/A:N" in vector and "PR:N" in vector and "AC:L" in vector:
        return 9.1
    return None


def fetch_osv_record(vuln_id: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """Fetch vulnerability metadata from the official OSV database API."""
    url = f"{OSV_API_URL}/{vuln_id}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-HR-Security-Audit/2.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    return None


def resolve_vulnerability_severity(vuln_data: dict[str, Any]) -> tuple[str, bool]:
    """Resolve authoritative vulnerability severity for a pip-audit finding.

    Returns:
        (severity_label, is_reliable)
        where severity_label is 'CRITICAL', 'HIGH', 'MODERATE', 'LOW', or 'UNKNOWN'
        and is_reliable indicates whether the severity came from a trusted security source.
    """
    vuln_id = vuln_data.get("id", "")

    # 1. Check direct severity fields in the input
    direct_severity = vuln_data.get("severity")
    if isinstance(direct_severity, str) and direct_severity.strip():
        norm = direct_severity.strip().upper()
        if norm in {"CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"}:
            return ("MODERATE" if norm == "MEDIUM" else norm), True

    if isinstance(direct_severity, list):
        for item in direct_severity:
            if isinstance(item, dict):
                score_str = item.get("score")
                if isinstance(score_str, str):
                    if "CVSS" in score_str:
                        score = extract_cvss_score_from_vector(score_str)
                        if score is not None and score >= 9.0:
                            return "CRITICAL", True
                        if score is not None:
                            return "HIGH", True

    # 2. Query OSV database for the authoritative record
    if vuln_id:
        record = fetch_osv_record(vuln_id)
        if record:
            db_specific = record.get("database_specific", {})
            db_sev = db_specific.get("severity")
            if isinstance(db_sev, str) and db_sev.strip():
                norm = db_sev.strip().upper()
                if norm in {"CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"}:
                    return ("MODERATE" if norm == "MEDIUM" else norm), True

            # Inspect CVSS scores in OSV record
            osv_sevs = record.get("severity", [])
            if isinstance(osv_sevs, list):
                for s in osv_sevs:
                    if isinstance(s, dict) and "score" in s:
                        score = extract_cvss_score_from_vector(s["score"])
                        if score is not None and score >= 9.0:
                            return "CRITICAL", True
                        if score is not None:
                            return "HIGH", True

            # If OSV record has aliases (e.g. PYSEC points to GHSA), query GHSA alias
            aliases = record.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and alias.startswith("GHSA-"):
                        alias_record = fetch_osv_record(alias)
                        if alias_record:
                            alias_sev = alias_record.get("database_specific", {}).get("severity")
                            if isinstance(alias_sev, str) and alias_sev.strip():
                                norm = alias_sev.strip().upper()
                                if norm in {"CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"}:
                                    return ("MODERATE" if norm == "MEDIUM" else norm), True

    # 3. Reliable severity could not be verified
    return "UNKNOWN", False


def audit_python_requirements(
    req_path: Path,
    executable: str = sys.executable,
) -> tuple[int, list[dict[str, Any]]]:
    """Audit requirements file using pip-audit with fail-closed error handling."""
    if not req_path.exists():
        print(f"[FAIL CLOSED] Requirements file not found: {req_path}")
        return 1, []

    cmd = [
        executable,
        "-m",
        "pip_audit",
        "-r",
        str(req_path),
        "-f",
        "json",
        "--desc",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
        print(f"[FAIL CLOSED] pip-audit failed to execute: {exc}")
        return 1, []

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    # Fail closed on empty output
    if not stdout.strip():
        print(
            f"[FAIL CLOSED] pip-audit produced empty output (exit code {proc.returncode}): {stderr}"
        )
        return 1, []

    # Fail closed on malformed JSON
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        print(f"[FAIL CLOSED] pip-audit output is not valid JSON ({exc}):\n{stdout[:200]}")
        return 1, []

    if not isinstance(data, dict) or "dependencies" not in data:
        print("[FAIL CLOSED] Invalid JSON schema from pip-audit: 'dependencies' key missing.")
        return 1, []

    dependencies = data.get("dependencies", [])
    critical_findings: list[dict[str, Any]] = []
    unverified_findings: list[dict[str, Any]] = []
    total_vulns = 0

    print("\n========================================================")
    print(f"  Dependency Vulnerability Audit: {req_path.name}")
    print("========================================================")

    for dep in dependencies:
        pkg_name = dep.get("name")
        version = dep.get("version")
        vulns = dep.get("vulns", [])
        if not vulns:
            continue

        total_vulns += len(vulns)
        print(f"\nPackage: {pkg_name} ({version}) - {len(vulns)} advisories found:")
        for v in vulns:
            vid = v.get("id", "UNKNOWN-ID")
            desc = v.get("description", "No description")
            fixes = v.get("fix_versions", [])

            severity, is_reliable = resolve_vulnerability_severity(v)

            print(
                f"  - [{vid}] Severity: {severity} (Reliable: {is_reliable}) | Fix: {fixes or 'No fix'}"
            )
            print(f"    Summary: {desc[:100]}...")

            if severity == "CRITICAL":
                critical_findings.append(
                    {
                        "package": pkg_name,
                        "version": version,
                        "id": vid,
                        "severity": severity,
                        "fix_versions": fixes,
                    }
                )
            elif not is_reliable:
                unverified_findings.append(
                    {
                        "package": pkg_name,
                        "version": version,
                        "id": vid,
                        "severity": severity,
                        "fix_versions": fixes,
                    }
                )

    print(f"\nAudit complete: {total_vulns} total advisories evaluated.")

    if critical_findings:
        print(f"\n[CRITICAL FAILURE] {len(critical_findings)} critical vulnerabilities detected!")
        for c in critical_findings:
            print(f"  CRITICAL: {c['package']}=={c['version']} - {c['id']}")
        return 1, critical_findings

    if unverified_findings:
        print(
            f"\n[FAIL CLOSED] {len(unverified_findings)} advisories lacked reliable severity info; failing safely."
        )
        for u in unverified_findings:
            print(f"  UNVERIFIED: {u['package']}=={u['version']} - {u['id']}")
        return 1, unverified_findings

    print("\n[PASSED] No critical vulnerabilities found in production dependencies.")
    return 0, []


def main() -> int:
    backend_root = Path(__file__).resolve().parent.parent
    prod_req = backend_root / "requirements.txt"
    exit_code, _ = audit_python_requirements(prod_req)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
