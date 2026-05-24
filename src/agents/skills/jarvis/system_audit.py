"""
System Auditor — Checks system health and readiness.

Used by continuous_evolution, dashboard, and master_agent to assess
overall system state before making decisions.
"""

import os
import py_compile
from typing import Dict, Any


SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class SystemAuditor:
    """Audits system health: imports, config, agent readiness."""

    def run_audit(self) -> Dict[str, Any]:
        """Run a full system audit and return a readiness report.

        Returns:
            Dict with 'readiness_score' (0.0-1.0), 'components', and 'issues'.
        """
        issues = []
        components = {}

        # 1. Check all Python files compile
        syntax_ok, syntax_total, syntax_errors = self._check_syntax()
        components["syntax"] = {
            "status": "healthy" if syntax_ok == syntax_total else "degraded",
            "files_ok": syntax_ok,
            "files_total": syntax_total,
        }
        issues.extend(syntax_errors)

        # 2. Check critical imports
        import_results = self._check_critical_imports()
        components["imports"] = {
            "status": "healthy" if all(import_results.values()) else "degraded",
            "results": {k: "ok" if v else "failed" for k, v in import_results.items()},
        }
        for name, ok in import_results.items():
            if not ok:
                issues.append(f"Critical import failed: {name}")

        # 3. Check config
        config_ok = self._check_config()
        components["config"] = {
            "status": "healthy" if config_ok else "degraded",
        }
        if not config_ok:
            issues.append("Config validation failed")

        # Calculate readiness score
        total_checks = syntax_total + len(import_results) + 1  # +1 for config
        passed = syntax_ok + sum(1 for v in import_results.values() if v) + (1 if config_ok else 0)
        readiness = passed / max(total_checks, 1)

        return {
            "readiness_score": round(readiness, 3),
            "components": components,
            "issues": issues,
            "overall_status": "healthy" if not issues else "degraded",
        }

    def _check_syntax(self) -> tuple[int, int, list[str]]:
        """Compile all .py files under src/ and count successes."""
        ok = 0
        total = 0
        errors = []
        for root, dirs, files in os.walk(SRC_ROOT):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", "node_modules")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                filepath = os.path.join(root, f)
                total += 1
                try:
                    py_compile.compile(filepath, doraise=True)
                    ok += 1
                except py_compile.PyCompileError as e:
                    rel = os.path.relpath(filepath, SRC_ROOT)
                    errors.append(f"SyntaxError in {rel}: {e}")
        return ok, total, errors

    def _check_critical_imports(self) -> Dict[str, bool]:
        """Test critical import chains."""
        results = {}
        checks = [
            ("evolution.self_evolution", "evolution_engine"),
            ("evolution.bug_worker", "bug_worker"),
            ("persistence.db", "get_open_bugs_sorted"),
        ]
        for module, attr in checks:
            try:
                mod = __import__(module, fromlist=[attr])
                results[f"{module}.{attr}"] = hasattr(mod, attr)
            except Exception:
                results[f"{module}.{attr}"] = False
        return results

    def _check_config(self) -> bool:
        """Check that critical config values are set."""
        try:
            from config.settings import get_settings
            settings = get_settings()
            return bool(settings.gemini_api_key)
        except Exception:
            return False
