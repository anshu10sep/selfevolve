"""
Auditor Agent Skills

Provides system auditing capabilities: code quality checks,
security scans, and compliance verification.
"""

class AuditorSkills:
    """Skills for the Auditor agent."""

    def audit_code_quality(self, filepath: str) -> dict:
        """Check a Python file for code quality issues."""
        import os
        if not os.path.exists(filepath):
            return {"status": "ERROR", "message": f"File not found: {filepath}"}

        with open(filepath) as f:
            lines = f.readlines()

        issues = []
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                issues.append({"line": i, "issue": "Line too long", "length": len(line)})
            if "TODO" in line or "FIXME" in line:
                issues.append({"line": i, "issue": "TODO/FIXME found", "text": line.strip()})

        return {
            "filepath": filepath,
            "total_lines": len(lines),
            "issues": len(issues),
            "details": issues[:10],
        }

    def check_docstrings(self, filepath: str) -> dict:
        """Check if all functions/classes have docstrings."""
        import ast, os
        if not os.path.exists(filepath):
            return {"status": "ERROR"}

        with open(filepath) as f:
            tree = ast.parse(f.read())

        missing = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not ast.get_docstring(node):
                    missing.append({"name": node.name, "line": node.lineno})

        return {"filepath": filepath, "missing_docstrings": missing, "count": len(missing)}
