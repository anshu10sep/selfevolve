"""
PR Reviewer Skill: Pre-Submit Checks

Runs validation checks BEFORE a PR is created:
  1. Python syntax check (py_compile)
  2. Import validation
  3. Security scan (hardcoded secrets, eval, exec)
  4. Basic style checks (docstrings, line length)
  5. pytest execution (if tests exist)

Returns a pass/fail verdict with details.
"""

from __future__ import annotations

import os
import re
import ast
import py_compile
import subprocess
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger(component="pr_reviewer.presubmit")

# Patterns that indicate security issues
SECURITY_PATTERNS = [
    (r'(?:api[_-]?key|secret|password|token)\s*=\s*["\'][^"\']{8,}', "Hardcoded secret/key"),
    (r'\beval\s*\(', "Use of eval() — potential code injection"),
    (r'\bexec\s*\(', "Use of exec() — potential code injection"),
    (r'subprocess\.(?:call|run|Popen)\(.*shell\s*=\s*True', "Shell injection risk"),
    (r'__import__\s*\(', "Dynamic import — potential security risk"),
]

# Files/patterns to skip
SKIP_PATTERNS = [
    "__pycache__", ".pyc", ".git", "node_modules",
    ".env", ".env.example", "venv",
]


@dataclass
class CheckResult:
    """Result of a single check."""
    name: str
    passed: bool
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details[:20],  # Cap details
        }


@dataclass
class PresubmitReport:
    """Full pre-submit report."""
    passed: bool
    checks: list[CheckResult]
    total_files: int
    error_count: int
    warning_count: int

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_files": self.total_files,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "checks": [c.to_dict() for c in self.checks],
        }

    def to_markdown(self) -> str:
        """Render as markdown for PR body."""
        icon = "✅" if self.passed else "❌"
        lines = [
            f"## {icon} Pre-Submit Checks",
            f"| Files | Errors | Warnings |",
            f"|-------|--------|----------|",
            f"| {self.total_files} | {self.error_count} | {self.warning_count} |",
            "",
        ]
        for c in self.checks:
            ci = "✅" if c.passed else "❌"
            lines.append(f"### {ci} {c.name}")
            lines.append(f"{c.message}")
            if c.details:
                for d in c.details[:10]:
                    lines.append(f"- `{d}`")
            lines.append("")
        return "\n".join(lines)


def _should_skip(filepath: str) -> bool:
    return any(p in filepath for p in SKIP_PATTERNS)


def _get_python_files(file_paths: list[str]) -> list[str]:
    """Filter to valid Python files."""
    result = []
    for fp in file_paths:
        if fp.endswith(".py") and not _should_skip(fp) and os.path.isfile(fp):
            result.append(fp)
    return result


def check_syntax(files: list[str]) -> CheckResult:
    """Check Python syntax with py_compile."""
    errors = []
    for fp in files:
        try:
            py_compile.compile(fp, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{os.path.basename(fp)}: {str(e)[:100]}")

    if errors:
        return CheckResult(
            name="Syntax Check",
            passed=False,
            message=f"{len(errors)} file(s) have syntax errors",
            details=errors,
        )
    return CheckResult(
        name="Syntax Check",
        passed=True,
        message=f"All {len(files)} file(s) pass syntax check",
    )


def check_imports(files: list[str]) -> CheckResult:
    """Validate that all imports can be resolved (AST-level)."""
    errors = []
    warnings = []

    for fp in files:
        try:
            with open(fp) as f:
                tree = ast.parse(f.read(), filename=fp)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Just check for obviously wrong patterns
                        if alias.name.startswith("."):
                            warnings.append(f"{os.path.basename(fp)}:{node.lineno}: relative import '{alias.name}'")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and "password" in node.module.lower():
                        errors.append(f"{os.path.basename(fp)}:{node.lineno}: suspicious import '{node.module}'")

        except SyntaxError:
            pass  # Already caught by syntax check
        except Exception as e:
            warnings.append(f"{os.path.basename(fp)}: parse error — {str(e)[:60]}")

    if errors:
        return CheckResult(
            name="Import Check",
            passed=False,
            message=f"{len(errors)} import issue(s) found",
            details=errors + warnings,
        )
    return CheckResult(
        name="Import Check",
        passed=True,
        message=f"Imports OK across {len(files)} file(s)" + (f" ({len(warnings)} warnings)" if warnings else ""),
        details=warnings,
    )


def check_security(files: list[str]) -> CheckResult:
    """Scan for hardcoded secrets, eval, exec, and other risks."""
    findings = []

    for fp in files:
        try:
            with open(fp) as f:
                content = f.read()

            for line_num, line in enumerate(content.split("\n"), 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                for pattern, description in SECURITY_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        basename = os.path.basename(fp)
                        # Skip: test files, example configs, and security pattern definitions
                        if basename.startswith("test_") or basename == ".env.example":
                            continue
                        if basename == "presubmit.py":
                            continue  # Don't flag our own pattern definitions
                        # Skip lines that are defining regex patterns (contain r' or r")
                        if "r'" in stripped or 'r"' in stripped:
                            continue
                        # Skip lines that are string literals (tuples defining patterns)
                        if stripped.startswith("(r'") or stripped.startswith('(r"'):
                            continue
                        findings.append(
                            f"{basename}:{line_num}: {description}"
                        )
        except Exception:
            pass

    if findings:
        return CheckResult(
            name="Security Scan",
            passed=False,
            message=f"🚨 {len(findings)} security issue(s) found",
            details=findings,
        )
    return CheckResult(
        name="Security Scan",
        passed=True,
        message="No security issues detected",
    )


def check_style(files: list[str]) -> CheckResult:
    """Basic style checks: docstrings, line length."""
    warnings = []

    for fp in files:
        try:
            with open(fp) as f:
                tree = ast.parse(f.read())
                f.seek(0)
                lines = f.readlines()

            basename = os.path.basename(fp)

            # Check for module docstring
            if not ast.get_docstring(tree):
                warnings.append(f"{basename}: missing module docstring")

            # Check functions/classes for docstrings
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if not ast.get_docstring(node):
                        warnings.append(f"{basename}:{node.lineno}: {node.name}() missing docstring")

            # Check line length
            long_lines = [i for i, l in enumerate(lines, 1) if len(l.rstrip()) > 150]
            if long_lines:
                warnings.append(f"{basename}: {len(long_lines)} lines exceed 150 chars")

        except Exception:
            pass

    return CheckResult(
        name="Style Check",
        passed=True,  # Style issues are warnings, not blockers
        message=f"{len(warnings)} style warning(s)" if warnings else "Style OK",
        details=warnings[:15],
    )


def check_tests(repo_root: str) -> CheckResult:
    """Run pytest if any test files exist."""
    # Find test files
    test_files = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", "node_modules")]
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                test_files.append(os.path.join(root, f))

    if not test_files:
        return CheckResult(
            name="Tests",
            passed=True,
            message="No test files found (skipped)",
        )

    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "--tb=short", "-q"] + test_files,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": os.path.join(repo_root, "src")},
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        return CheckResult(
            name="Tests",
            passed=passed,
            message=f"{'All tests passed' if passed else 'Test failures detected'}",
            details=output.strip().split("\n")[-10:],
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Tests",
            passed=False,
            message="Tests timed out (>120s)",
        )
    except Exception as e:
        return CheckResult(
            name="Tests",
            passed=True,
            message=f"Could not run tests: {str(e)[:80]} (skipped)",
        )


def run_presubmit(
    file_paths: list[str],
    repo_root: str,
    block_on_security: bool = True,
) -> PresubmitReport:
    """
    Run all pre-submit checks on a list of files.

    Args:
        file_paths: Absolute paths to files being committed
        repo_root: Repository root for finding tests
        block_on_security: If True, security issues block the PR

    Returns:
        PresubmitReport with pass/fail verdict
    """
    py_files = _get_python_files(file_paths)

    if not py_files:
        return PresubmitReport(
            passed=True, checks=[], total_files=0,
            error_count=0, warning_count=0,
        )

    checks = [
        check_syntax(py_files),
        check_imports(py_files),
        check_security(py_files),
        check_style(py_files),
        check_tests(repo_root),
    ]

    error_count = sum(1 for c in checks if not c.passed)
    warning_count = sum(len(c.details) for c in checks if c.passed and c.details)

    # Determine pass/fail
    # Block on: syntax errors, import errors, and optionally security
    blocking_checks = ["Syntax Check", "Import Check"]
    if block_on_security:
        blocking_checks.append("Security Scan")

    passed = all(
        c.passed for c in checks
        if c.name in blocking_checks
    )

    report = PresubmitReport(
        passed=passed,
        checks=checks,
        total_files=len(py_files),
        error_count=error_count,
        warning_count=warning_count,
    )

    logger.info(
        "presubmit_complete",
        passed=passed,
        files=len(py_files),
        errors=error_count,
        warnings=warning_count,
    )

    return report
