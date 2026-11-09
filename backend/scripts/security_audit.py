"""Automated dependency vulnerability scanner and security gate.

Audits production Python requirements using pip-audit:
- Enforces fail-closed semantics on execution errors, empty output, and invalid JSON.
- Evaluates vulnerability severity using authoritative CVSS v3.0/v3.1 equations and trusted security sources.
- Does not rely on heuristic description keyword matching.
- Precludes lower textual ratings from overriding higher authoritative CVSS scores.
- Fails safely if reliable severity metadata is unavailable.
- Exits with non-zero code if critical vulnerabilities or unverifiable advisories are detected.
"""

from __future__ import annotations

import functools
import json
import math
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OSV_API_URL = "https://api.osv.dev/v1/vulns"


def _cvss_roundup(input_val: float) -> float:
    """Standard FIRST CVSS v3.1 roundup function."""
    int_input = round(input_val * 100000)
    if int_input % 10000 == 0:
        return int_input / 100000.0
    return (math.floor(int_input / 10000) + 1) / 10.0


def calculate_cvss_v3_score(vector: str) -> float | None:
    """Calculate the exact CVSS v3.0/v3.1 base score from a vector string.

    Follows the official FIRST CVSS v3.1 specification equations.
    Supports Scope Unchanged (S:U) and Scope Changed (S:C).
    """
    if not isinstance(vector, str):
        return None

    clean = vector.strip()
    for prefix in ("CVSS:3.1/", "CVSS:3.0/"):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :]
            break

    try:
        metrics = dict(part.split(":", 1) for part in clean.split("/") if ":" in part)
        required = {"AV", "AC", "PR", "UI", "S", "C", "I", "A"}
        if not required.issubset(metrics.keys()):
            return None

        av_map = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
        ac_map = {"L": 0.77, "H": 0.44}
        ui_map = {"N": 0.85, "R": 0.62}
        scope = metrics["S"]

        if scope == "U":
            pr_map = {"N": 0.85, "L": 0.62, "H": 0.27}
        elif scope == "C":
            pr_map = {"N": 0.85, "L": 0.68, "H": 0.50}
        else:
            return None

        c_map = {"H": 0.56, "L": 0.22, "N": 0.0}
        i_map = {"H": 0.56, "L": 0.22, "N": 0.0}
        a_map = {"H": 0.56, "L": 0.22, "N": 0.0}

        av = av_map[metrics["AV"]]
        ac = ac_map[metrics["AC"]]
        pr = pr_map[metrics["PR"]]
        ui = ui_map[metrics["UI"]]
        c = c_map[metrics["C"]]
        i = i_map[metrics["I"]]
        a = a_map[metrics["A"]]

        iss = 1.0 - ((1.0 - c) * (1.0 - i) * (1.0 - a))
        if scope == "U":
            impact = 6.42 * iss
        else:
            impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)

        exploitability = 8.22 * av * ac * pr * ui

        if impact <= 0:
            return 0.0

        if scope == "U":
            return _cvss_roundup(min(impact + exploitability, 10.0))
        else:
            return _cvss_roundup(min(1.08 * (impact + exploitability), 10.0))
    except Exception:
        return None


def cvss_score_to_severity(score: float) -> str:
    """Map numeric CVSS score to qualitative severity rating."""
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MODERATE"
    if score > 0.0:
        return "LOW"
    return "NONE"


@functools.lru_cache(maxsize=512)
def fetch_osv_record(vuln_id: str, timeout: float = 6.0) -> dict[str, Any] | None:
    """Fetch vulnerability metadata from the official OSV database API with caching and retry."""
    url = f"{OSV_API_URL}/{vuln_id}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-HR-Security-Audit/2.0", "Accept": "application/json"},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None
    return None


def resolve_vulnerability_severity(vuln_data: dict[str, Any]) -> tuple[str, bool, float | None]:
    """Resolve authoritative vulnerability severity and CVSS score.

    Evaluates:
    1. Direct CVSS vectors in finding payload
    2. Primary OSV database record
    3. Alias records (GHSA, CVE)

    Enforces that authoritative CVSS scores take precedence and lower textual
    ratings never override higher calculated base scores.

    Returns:
        (severity_label, is_reliable, cvss_score)
    """
    vuln_id = vuln_data.get("id", "")
    discovered_scores: list[float] = []
    discovered_ratings: list[str] = []

    # 1. Inspect direct attributes in finding
    direct_severity = vuln_data.get("severity")
    if isinstance(direct_severity, str) and direct_severity.strip():
        norm = direct_severity.strip().upper()
        if norm in {"CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"}:
            discovered_ratings.append("MODERATE" if norm == "MEDIUM" else norm)
    elif isinstance(direct_severity, list):
        for item in direct_severity:
            if isinstance(item, dict):
                score_val = item.get("score")
                if isinstance(score_val, int | float):
                    discovered_scores.append(float(score_val))
                elif isinstance(score_val, str):
                    if "CVSS" in score_val:
                        calc = calculate_cvss_v3_score(score_val)
                        if calc is not None:
                            discovered_scores.append(calc)

    # 2. Inspect OSV record if available
    record = fetch_osv_record(vuln_id) if vuln_id else None
    aliases: list[str] = []
    if record:
        db_sev = record.get("database_specific", {}).get("severity")
        if isinstance(db_sev, str) and db_sev.strip():
            norm = db_sev.strip().upper()
            if norm in {"CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"}:
                discovered_ratings.append("MODERATE" if norm == "MEDIUM" else norm)

        for s_item in record.get("severity", []):
            if isinstance(s_item, dict):
                s_score = s_item.get("score")
                if isinstance(s_score, int | float):
                    discovered_scores.append(float(s_score))
                elif isinstance(s_score, str) and "CVSS" in s_score:
                    calc = calculate_cvss_v3_score(s_score)
                    if calc is not None:
                        discovered_scores.append(calc)

        aliases = [a for a in record.get("aliases", []) if isinstance(a, str)]

    # 3. Inspect aliases (preferring GHSA records which reliably specify CVSS/severity)
    for alias in aliases:
        if alias.startswith("GHSA-") or alias.startswith("CVE-"):
            alias_rec = fetch_osv_record(alias)
            if not alias_rec:
                continue
            a_sev = alias_rec.get("database_specific", {}).get("severity")
            if isinstance(a_sev, str) and a_sev.strip():
                norm = a_sev.strip().upper()
                if norm in {"CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW"}:
                    discovered_ratings.append("MODERATE" if norm == "MEDIUM" else norm)

            for a_item in alias_rec.get("severity", []):
                if isinstance(a_item, dict):
                    a_score = a_item.get("score")
                    if isinstance(a_score, int | float):
                        discovered_scores.append(float(a_score))
                    elif isinstance(a_score, str) and "CVSS" in a_score:
                        calc = calculate_cvss_v3_score(a_score)
                        if calc is not None:
                            discovered_scores.append(calc)

    # 4. Resolve final severity
    # Rule: Authoritative numeric CVSS score takes absolute precedence
    if discovered_scores:
        max_score = max(discovered_scores)
        return cvss_score_to_severity(max_score), True, max_score

    # Fallback to trusted textual ratings if no numeric score was found
    if discovered_ratings:
        rating_priority = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}
        highest_rating = max(discovered_ratings, key=lambda r: rating_priority.get(r, 0))
        return highest_rating, True, None

    # Unverifiable severity
    return "UNKNOWN", False, None


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

            severity, is_reliable, cvss_score = resolve_vulnerability_severity(v)
            score_info = f"CVSS {cvss_score:.1f}" if cvss_score is not None else "No CVSS"

            print(
                f"  - [{vid}] Severity: {severity} ({score_info}, Reliable: {is_reliable}) | Fix: {fixes or 'No fix'}"
            )
            print(f"    Summary: {desc[:100]}...")

            if severity == "CRITICAL":
                critical_findings.append(
                    {
                        "package": pkg_name,
                        "version": version,
                        "id": vid,
                        "severity": severity,
                        "cvss_score": cvss_score,
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
            score_str = f" (CVSS {c['cvss_score']})" if c.get("cvss_score") else ""
            print(f"  CRITICAL: {c['package']}=={c['version']} - {c['id']}{score_str}")
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
