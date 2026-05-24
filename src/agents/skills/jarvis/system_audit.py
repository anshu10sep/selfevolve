"""
Jarvis Skill: System Audit

Scans the codebase for gaps, missing files, TODOs, untested modules,
and agents without skills or goals. Produces actionable gap reports.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger(component="jarvis.system_audit")

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@dataclass
class AuditFinding:
    """A single audit finding."""
    category: str  # "MISSING_FILE", "TODO", "NO_TESTS", "NO_SKILLS", "NO_GOALS", "STUB"
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    location: str
    description: str


@dataclass
class AuditReport:
    """Complete system audit report."""
    timestamp: str = ""
    total_files: int = 0
    total_lines: int = 0
    total_agents: int = 0
    agents_with_skills: int = 0
    agents_with_goals: int = 0
    test_count: int = 0
    findings: list[AuditFinding] = field(default_factory=list)
    readiness_score: float = 0.0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "HIGH")


class SystemAuditor:
    """Audits the SelfEvolve codebase for completeness and quality."""

    EXPECTED_AGENT_ROLES = [
        "jarvis", "cto", "cso", "qa", "developer", "product",
        "fundamental_analyst", "technical_analyst", "sentiment_analyst",
        "macro_analyst", "bull", "bear", "judge", "meta_review",
        "journaling", "auditor", "model_orchestrator",
    ]

    EXPECTED_ORCHESTRATION = [
        "trading_dag.py", "evolution_dag.py", "debate_workflow.py", "morning_briefing.py",
    ]

    EXPECTED_DATA_MODULES = [
        "market_data_daemon.py", "regime_tracker.py", "news_scraper.py", "sec_edgar.py",
    ]

    def __init__(self, src_root: str = SRC_ROOT):
        self.src_root = src_root

    def full_audit(self) -> AuditReport:
        """Run a complete system audit."""
        from datetime import datetime, timezone

        report = AuditReport(timestamp=datetime.now(timezone.utc).isoformat())

        # Count files and lines
        report.total_files, report.total_lines = self._count_files_and_lines()

        # Audit agents
        self._audit_agents(report)

        # Audit skills and goals
        self._audit_skills_and_goals(report)

        # Audit orchestration
        self._audit_orchestration(report)

        # Audit data pipelines
        self._audit_data_pipelines(report)

        # Audit tests
        self._audit_tests(report)

        # Scan for TODOs and stubs
        self._scan_todos(report)

        # Scan for stub methods
        self._scan_stubs(report)

        # Calculate readiness
        report.readiness_score = self._calculate_readiness(report)

        logger.info(
            "audit_complete",
            files=report.total_files,
            lines=report.total_lines,
            findings=len(report.findings),
            critical=report.critical_count,
            readiness=f"{report.readiness_score:.0%}",
        )

        return report

    def _count_files_and_lines(self) -> tuple[int, int]:
        """Count Python files and total lines."""
        total_files = 0
        total_lines = 0
        for root, _, files in os.walk(self.src_root):
            if "__pycache__" in root or ".pytest_cache" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    total_files += 1
                    filepath = os.path.join(root, f)
                    try:
                        with open(filepath) as fh:
                            total_lines += sum(1 for _ in fh)
                    except Exception:
                        pass
        return total_files, total_lines

    def _audit_agents(self, report: AuditReport):
        """Check that all expected agents have implementation files."""
        agents_dir = os.path.join(self.src_root, "agents")
        existing_files = set(os.listdir(agents_dir)) if os.path.isdir(agents_dir) else set()

        # Agent files that should exist
        expected_agent_files = {
            "master_agent.py", "cto_agent.py", "cso_agent.py", "qa_agent.py",
            "developer_agent.py", "product_agent.py", "meta_review_agent.py",
            "journaling_agent.py", "auditor_agent.py", "judge_agent.py",
            "analyst_agents.py", "debate_agents.py", "model_orchestrator.py",
            "base_agent.py",
        }

        for expected in expected_agent_files:
            if expected not in existing_files:
                report.findings.append(AuditFinding(
                    category="MISSING_FILE",
                    severity="HIGH",
                    location=f"agents/{expected}",
                    description=f"Agent implementation file missing: {expected}",
                ))

        report.total_agents = len(self.EXPECTED_AGENT_ROLES)

    def _audit_skills_and_goals(self, report: AuditReport):
        """Check that all agents have skills directories and goals.md."""
        skills_dir = os.path.join(self.src_root, "agents", "skills")

        for role in self.EXPECTED_AGENT_ROLES:
            role_dir = os.path.join(skills_dir, role)
            goals_file = os.path.join(role_dir, "goals.md")

            if not os.path.isdir(role_dir):
                report.findings.append(AuditFinding(
                    category="NO_SKILLS",
                    severity="CRITICAL",
                    location=f"agents/skills/{role}/",
                    description=f"Skills directory missing for {role}",
                ))
            else:
                report.agents_with_skills += 1

            if not os.path.isfile(goals_file):
                report.findings.append(AuditFinding(
                    category="NO_GOALS",
                    severity="HIGH",
                    location=f"agents/skills/{role}/goals.md",
                    description=f"Goals file missing for {role}",
                ))
            else:
                report.agents_with_goals += 1

    def _audit_orchestration(self, report: AuditReport):
        """Check that all expected DAGs exist."""
        orch_dir = os.path.join(self.src_root, "orchestration")
        existing = set(os.listdir(orch_dir)) if os.path.isdir(orch_dir) else set()

        for expected in self.EXPECTED_ORCHESTRATION:
            if expected not in existing:
                report.findings.append(AuditFinding(
                    category="MISSING_FILE",
                    severity="HIGH",
                    location=f"orchestration/{expected}",
                    description=f"Orchestration DAG missing: {expected}",
                ))

    def _audit_data_pipelines(self, report: AuditReport):
        """Check that data pipeline modules exist."""
        data_dir = os.path.join(self.src_root, "data")
        existing = set(os.listdir(data_dir)) if os.path.isdir(data_dir) else set()

        for expected in self.EXPECTED_DATA_MODULES:
            if expected not in existing:
                report.findings.append(AuditFinding(
                    category="MISSING_FILE",
                    severity="MEDIUM",
                    location=f"data/{expected}",
                    description=f"Data pipeline missing: {expected}",
                ))

    def _audit_tests(self, report: AuditReport):
        """Count test files and check coverage."""
        tests_dir = os.path.join(self.src_root, "tests")
        for root, _, files in os.walk(tests_dir):
            for f in files:
                if f.startswith("test_") and f.endswith(".py"):
                    report.test_count += 1

    def _scan_todos(self, report: AuditReport):
        """Scan for TODO/FIXME/HACK comments."""
        for root, _, files in os.walk(self.src_root):
            if "__pycache__" in root or ".pytest_cache" in root:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                filepath = os.path.join(root, f)
                try:
                    with open(filepath) as fh:
                        for lineno, line in enumerate(fh, 1):
                            for marker in ("TODO", "FIXME", "HACK"):
                                if marker in line and not line.strip().startswith("#!"):
                                    rel = os.path.relpath(filepath, self.src_root)
                                    report.findings.append(AuditFinding(
                                        category="TODO",
                                        severity="LOW",
                                        location=f"{rel}:{lineno}",
                                        description=line.strip()[:120],
                                    ))
                except Exception:
                    pass

    def _scan_stubs(self, report: AuditReport):
        """Scan for stub/placeholder methods."""
        stub_pattern = re.compile(r"^\s*(pass|\.\.\.)\s*$")
        for root, _, files in os.walk(self.src_root):
            if "__pycache__" in root or ".pytest_cache" in root or "tests" in root:
                continue
            for f in files:
                if not f.endswith(".py") or f == "__init__.py":
                    continue
                filepath = os.path.join(root, f)
                try:
                    with open(filepath) as fh:
                        lines = fh.readlines()
                    for i, line in enumerate(lines):
                        if stub_pattern.match(line) and i > 0:
                            prev = lines[i - 1].strip() if i > 0 else ""
                            if prev.startswith('"""') or prev.startswith("'''") or prev.startswith("def ") or prev.startswith("async def"):
                                rel = os.path.relpath(filepath, self.src_root)
                                report.findings.append(AuditFinding(
                                    category="STUB",
                                    severity="MEDIUM",
                                    location=f"{rel}:{i+1}",
                                    description=f"Stub implementation found after: {prev[:80]}",
                                ))
                except Exception:
                    pass

    def _calculate_readiness(self, report: AuditReport) -> float:
        """Calculate a 0-1 readiness score."""
        scores = []

        # Agent completeness (weight: 25%)
        if report.total_agents > 0:
            scores.append(0.25 * (report.agents_with_goals / report.total_agents))

        # No critical findings (weight: 30%)
        critical_penalty = min(1.0, report.critical_count * 0.2)
        scores.append(0.30 * (1.0 - critical_penalty))

        # Test coverage (weight: 20%)
        expected_tests = 10  # minimum expected
        scores.append(0.20 * min(1.0, report.test_count / expected_tests))

        # File completeness (weight: 25%)
        missing = sum(1 for f in report.findings if f.category == "MISSING_FILE")
        expected_files = 15  # rough count of expected implementation files
        scores.append(0.25 * max(0, 1.0 - (missing / expected_files)))

        return sum(scores)

    def generate_report_markdown(self, report: AuditReport) -> str:
        """Generate a human-readable Markdown report."""
        lines = [
            f"# System Audit Report",
            f"",
            f"**Timestamp**: {report.timestamp}",
            f"**Readiness Score**: {report.readiness_score:.0%}",
            f"",
            f"## Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Python Files | {report.total_files} |",
            f"| Total Lines | {report.total_lines} |",
            f"| Agents | {report.total_agents} |",
            f"| Agents with Skills | {report.agents_with_skills} |",
            f"| Agents with Goals | {report.agents_with_goals} |",
            f"| Test Files | {report.test_count} |",
            f"| Critical Findings | {report.critical_count} |",
            f"| High Findings | {report.high_count} |",
            f"| Total Findings | {len(report.findings)} |",
            f"",
        ]

        # Group by severity
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            items = [f for f in report.findings if f.severity == severity]
            if items:
                lines.append(f"## {severity} ({len(items)})")
                for item in items:
                    lines.append(f"- **[{item.category}]** `{item.location}`: {item.description}")
                lines.append("")

        return "\n".join(lines)
