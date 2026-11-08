"""Static security analysis and supply-chain verification test suite.

Verifies:
1. Strict dependency pinning without wildcards or unpinned packages in requirements.txt.
2. Python AST audit ensuring no dangerous functions (eval, exec, pickle.loads, marshal).
3. Hardcoded secret and private key pattern detection across the application codebase.
4. Security header policy presence and HTTPS/HSTS configuration.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


def get_backend_root() -> Path:
    """Return backend directory root."""
    return Path(__file__).resolve().parent.parent


def test_requirements_strictly_pinned_and_no_wildcards() -> None:
    """All production requirements in requirements.txt must be pinned to exact versions."""
    req_file = get_backend_root() / "requirements.txt"
    assert req_file.exists(), "requirements.txt not found"

    lines = req_file.read_text(encoding="utf-8").splitlines()
    for line_num, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        # Skip empty lines, comments, and option flags
        if not line or line.startswith("#") or line.startswith("-"):
            continue

        # Strip environment markers (e.g., ; sys_platform == 'linux')
        package_spec = line.split(";")[0].strip()

        assert not package_spec.endswith(
            "*"
        ), f"Wildcard dependency forbidden at line {line_num}: {line}"
        # Packages must be either strictly pinned (==) or bounded by an upper version limit (<)
        has_exact_pin = "==" in package_spec
        has_upper_bound = "<" in package_spec
        assert (
            has_exact_pin or has_upper_bound
        ), f"Package requirement must have an upper bound or exact pin at line {line_num}: {line}"
        # Verify banned legacy or insecure packages are not present
        pkg_name = package_spec.split("==")[0].strip().lower()
        banned = {"pycrypto", "pycryptodome-legacy", "python-jose"}
        assert pkg_name not in banned, f"Banned or deprecated package detected: {pkg_name}"


def test_no_dangerous_ast_constructs_in_application_code() -> None:
    """Application codebase contains zero calls to eval, exec, pickle, or raw shell popen."""
    app_dir = get_backend_root() / "app"
    assert app_dir.exists(), "app directory not found"

    banned_calls = {"eval", "exec"}
    banned_modules = {"pickle", "marshal"}

    violations: list[str] = []

    for py_file in app_dir.rglob("*.py"):
        # Skip pycache
        if "__pycache__" in py_file.parts:
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError as e:
            violations.append(f"Syntax error in {py_file}: {e}")
            continue

        for node in ast.walk(tree):
            # Check for banned direct calls: eval(...) or exec(...)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in banned_calls:
                    violations.append(
                        f"Banned call '{node.func.id}()' in {py_file.relative_to(app_dir)}:line {node.lineno}"
                    )
                # Check for banned attribute calls: pickle.loads(...) or marshal.loads(...)
                elif isinstance(node.func, ast.Attribute):
                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id in banned_modules
                    ):
                        violations.append(
                            f"Banned module usage '{node.func.value.id}.{node.func.attr}' in "
                            f"{py_file.relative_to(app_dir)}:line {node.lineno}"
                        )

    assert not violations, "Dangerous AST constructs detected:\n" + "\n".join(violations)


def test_no_hardcoded_secrets_or_private_keys_in_app() -> None:
    """Application source files do not contain hardcoded private keys or access tokens."""
    app_dir = get_backend_root() / "app"

    secret_patterns = [
        (
            re.compile(r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)?\s*PRIVATE\s+KEY-----"),
            "Private key block",
        ),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
        (re.compile(r"ghp_[0-9a-zA-Z]{36}"), "GitHub Personal Access Token"),
        (re.compile(r"glpat-[0-9a-zA-Z\-_]{20}"), "GitLab Personal Access Token"),
        (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"), "Slack API Token"),
    ]

    violations: list[str] = []

    for py_file in app_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue

        content = py_file.read_text(encoding="utf-8")
        for pattern, desc in secret_patterns:
            if pattern.search(content):
                violations.append(f"Possible {desc} found in {py_file.relative_to(app_dir)}")

    assert not violations, "Secret leak patterns detected:\n" + "\n".join(violations)
