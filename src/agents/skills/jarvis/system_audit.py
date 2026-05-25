import os
import platform
import psutil
from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass
class AuditFinding:
    """A single audit finding."""
    category: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    file_path: str = ""
    line_number: int = 0


@dataclass
class AuditResult:
    """Structured result from a full system audit."""
    readiness_score: float = 0.0
    total_files: int = 0
    total_lines: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    findings: List[AuditFinding] = field(default_factory=list)
    system_health: Dict[str, Any] = field(default_factory=dict)


class SystemAuditor:
    """
    Skill for Jarvis to audit the SelfEvolve codebase and system health.
    
    Provides:
    - full_audit(): comprehensive codebase + system scan
    - generate_report_markdown(): human-readable markdown report
    - perform_system_audit(): hardware/OS health check
    - check_log_directory_health(): log directory analysis
    """

    def __init__(self, src_dir: str = None):
        if src_dir is None:
            self.src_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
        else:
            self.src_dir = src_dir

    def full_audit(self) -> AuditResult:
        """
        Perform a comprehensive audit of the codebase and system.
        
        Scans for:
        - Total file/line counts
        - Missing __init__.py files
        - TODO/FIXME/HACK markers
        - Files without docstrings
        - System resource health
        
        Returns:
            AuditResult with findings, readiness score, and metrics.
        """
        result = AuditResult()
        findings = []
        src_path = os.path.join(self.src_dir, "src")
        
        if not os.path.isdir(src_path):
            src_path = self.src_dir

        # Count files and lines, scan for issues
        for root, dirs, files in os.walk(src_path):
            # Skip __pycache__ and hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith(('.', '__pycache__'))]

            for fname in files:
                if not fname.endswith('.py'):
                    continue

                fpath = os.path.join(root, fname)
                result.total_files += 1

                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    result.total_lines += len(lines)

                    # Check for TODO/FIXME/HACK markers
                    for i, line in enumerate(lines, 1):
                        for marker in ['TODO', 'FIXME', 'HACK', 'XXX']:
                            if marker in line:
                                findings.append(AuditFinding(
                                    category="code_marker",
                                    severity="LOW",
                                    description=f"{marker} found: {line.strip()[:80]}",
                                    file_path=fpath,
                                    line_number=i,
                                ))

                    # Check for module docstring
                    content = ''.join(lines)
                    if not content.strip().startswith(('"""', "'''")):
                        if fname != '__init__.py':
                            findings.append(AuditFinding(
                                category="missing_docstring",
                                severity="LOW",
                                description=f"No module docstring in {fname}",
                                file_path=fpath,
                            ))

                except Exception:
                    findings.append(AuditFinding(
                        category="read_error",
                        severity="MEDIUM",
                        description=f"Failed to read {fpath}",
                        file_path=fpath,
                    ))

            # Check for missing __init__.py
            if any(f.endswith('.py') for f in files) and '__init__.py' not in files:
                findings.append(AuditFinding(
                    category="missing_init",
                    severity="MEDIUM",
                    description=f"Directory missing __init__.py",
                    file_path=root,
                ))

        result.findings = findings
        result.critical_count = sum(1 for f in findings if f.severity == "CRITICAL")
        result.high_count = sum(1 for f in findings if f.severity == "HIGH")
        result.medium_count = sum(1 for f in findings if f.severity == "MEDIUM")
        result.low_count = sum(1 for f in findings if f.severity == "LOW")

        # Calculate readiness score (higher is better)
        total_issues = result.critical_count * 10 + result.high_count * 5 + result.medium_count * 2 + result.low_count
        max_penalty = max(1, result.total_files * 2)
        result.readiness_score = max(0.0, 1.0 - (total_issues / max_penalty))

        # Add system health
        result.system_health = perform_system_audit()

        return result

    def generate_report_markdown(self, audit: AuditResult) -> str:
        """
        Generate a human-readable Markdown report from an AuditResult.
        
        Args:
            audit: The AuditResult to format.
            
        Returns:
            Markdown-formatted string.
        """
        lines = [
            "# System Audit Report",
            "",
            f"**Readiness Score**: {audit.readiness_score:.0%}",
            f"**Codebase**: {audit.total_files} files, {audit.total_lines:,} lines",
            "",
            "## Findings Summary",
            f"- 🔴 Critical: {audit.critical_count}",
            f"- 🟠 High: {audit.high_count}",
            f"- 🟡 Medium: {audit.medium_count}",
            f"- 🟢 Low: {audit.low_count}",
            "",
        ]

        if audit.system_health:
            lines.extend([
                "## System Health",
                f"- OS: {audit.system_health.get('os', '?')} {audit.system_health.get('os_release', '')}",
                f"- Python: {audit.system_health.get('python_version', '?')}",
                f"- Memory: {audit.system_health.get('memory_available_gb', '?')} GB available / {audit.system_health.get('memory_total_gb', '?')} GB total",
                f"- Disk: {audit.system_health.get('disk_free_gb', '?')} GB free / {audit.system_health.get('disk_total_gb', '?')} GB total",
                f"- Status: {audit.system_health.get('status', '?')}",
                "",
            ])

        # Group findings by category
        if audit.findings:
            lines.append("## Detailed Findings")
            by_category: Dict[str, list] = {}
            for f in audit.findings:
                by_category.setdefault(f.category, []).append(f)

            for category, items in sorted(by_category.items()):
                lines.append(f"\n### {category.replace('_', ' ').title()} ({len(items)})")
                for item in items[:10]:  # Limit to 10 per category
                    loc = f" ({item.file_path}:{item.line_number})" if item.line_number else f" ({item.file_path})"
                    lines.append(f"- [{item.severity}] {item.description}{loc}")
                if len(items) > 10:
                    lines.append(f"- ... and {len(items) - 10} more")

        return "\n".join(lines)


def perform_system_audit() -> Dict[str, Any]:
    """
    Perform a basic system audit to check resources and environment.
    Useful for diagnosing environment-related errors.
    """
    audit_results = {
        "os": platform.system(),
        "os_release": platform.release(),
        "python_version": platform.python_version(),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
        "disk_free_gb": round(psutil.disk_usage('/').free / (1024**3), 2),
        "status": "healthy"
    }
    
    if audit_results["memory_available_gb"] < 1.0:
        audit_results["status"] = "warning"
        audit_results["warning_reason"] = "Low memory available"
        
    if audit_results["disk_free_gb"] < 5.0:
        audit_results["status"] = "warning"
        audit_results["warning_reason"] = "Low disk space"
        
    return audit_results

def check_log_directory_health(log_dir: str) -> Dict[str, Any]:
    """
    Check the health and size of the log directory to ensure logs 
    are not growing uncontrollably due to spamming errors.
    """
    if not os.path.exists(log_dir):
        return {"status": "error", "message": f"Log directory {log_dir} does not exist"}
        
    total_size = 0
    file_count = 0
    
    for root, _, files in os.walk(log_dir):
        for file in files:
            if file.endswith(".log"):
                file_count += 1
                file_path = os.path.join(root, file)
                total_size += os.path.getsize(file_path)
                
    size_mb = round(total_size / (1024 * 1024), 2)
    
    return {
        "status": "healthy" if size_mb < 500 else "warning",
        "log_directory": log_dir,
        "file_count": file_count,
        "total_size_mb": size_mb
    }


# ── LLM Tool-Calling Registration ─────────────────────────────────
from agents.skills.validator import skill


@skill("master")
def run_system_audit() -> str:
    """Run a full system audit of the SelfEvolve codebase and infrastructure.
    Returns a markdown report with readiness score, file counts, line counts,
    critical findings, system resource health, and improvement recommendations.
    Use this to understand the current health and state of the system.

    Returns:
        Markdown-formatted audit report string.
    """
    auditor = SystemAuditor()
    audit = auditor.full_audit()
    return auditor.generate_report_markdown(audit)


@skill("master")
def check_system_resources() -> str:
    """Check current system resource utilization (CPU, memory, disk).
    Use this to diagnose performance issues or resource constraints.

    Returns:
        Formatted string with CPU, memory, disk, and OS information.
    """
    health = perform_system_audit()
    lines = [
        f"OS: {health.get('os', '?')} {health.get('os_release', '')}",
        f"Python: {health.get('python_version', '?')}",
        f"CPUs: {health.get('cpu_count', '?')}",
        f"Memory: {health.get('memory_available_gb', '?')} GB free / {health.get('memory_total_gb', '?')} GB total",
        f"Disk: {health.get('disk_free_gb', '?')} GB free / {health.get('disk_total_gb', '?')} GB total",
        f"Status: {health.get('status', '?')}",
    ]
    if health.get("warning_reason"):
        lines.append(f"⚠️ Warning: {health['warning_reason']}")
    return "\n".join(lines)