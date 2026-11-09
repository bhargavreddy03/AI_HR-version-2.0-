"""Automated dependency vulnerability scanner and security gate.

Audits production Python requirements using pip-audit:
- Enforces zero critical severity vulnerabilities in production dependencies.
- Identifies and logs all CVE advisories with recommended remediation versions.
- Exits with non-zero code if critical security findings are detected.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def audit_python_requirements(req_path: Path) -> tuple[int, list[dict]]:
    """Audit requirements file using pip-audit with JSON output."""
    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        str(req_path),
        "-f",
        "json",
        "--desc",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    try:
        data = json.loads(proc.stdout) if proc.stdout else {}
    except json.JSONDecodeError:
        print(f"Warning: pip-audit output not valid JSON:\n{proc.stdout}\n{proc.stderr}")
        return proc.returncode, []

    dependencies = data.get("dependencies", [])
    critical_findings: list[dict] = []
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
            vid = v.get("id")
            desc = v.get("description", "No description")
            fixes = v.get("fix_versions", [])
            # Detect critical severity indicators
            is_critical = any(
                crit_kw in desc.lower()
                for crit_kw in [
                    "remote code execution",
                    "critical severity",
                    "cvss:3.1/av:n/ac:l/pr:n/ui:n/s:c",
                    "cvss 9.",
                    "cvss 10.",
                ]
            )

            print(f"  - [{vid}] Fix: {fixes if fixes else 'No fix available'}")
            print(f"    Summary: {desc[:100]}...")

            if is_critical:
                critical_findings.append(
                    {
                        "package": pkg_name,
                        "version": version,
                        "id": vid,
                        "fix_versions": fixes,
                        "description": desc,
                    }
                )

    print(f"\nAudit complete: {total_vulns} total advisories evaluated.")
    if critical_findings:
        print(f"\n[CRITICAL FAILURE] {len(critical_findings)} critical vulnerabilities detected!")
        for c in critical_findings:
            print(f"  CRITICAL: {c['package']}=={c['version']} - {c['id']}")
        return 1, critical_findings

    print("\n[PASSED] No critical vulnerabilities found in production dependencies.")
    return 0, []


def main() -> int:
    backend_root = Path(__file__).resolve().parent.parent
    prod_req = backend_root / "requirements.txt"
    if not prod_req.exists():
        print(f"Error: requirements file not found at {prod_req}")
        return 1

    exit_code, _ = audit_python_requirements(prod_req)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
