"""
Jarvis Skill: Agent Planning

Enables Jarvis to plan the next evolution cycle, prioritize tasks,
and create a multi-day roadmap for autonomous system improvement.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog

from agents.skills.jarvis.system_audit import SystemAuditor, AuditReport

logger = structlog.get_logger(component="jarvis.agent_planning")


@dataclass
class EvolutionTask:
    """A single task in the evolution plan."""
    title: str
    description: str
    priority: int  # 1 = highest
    estimated_hours: float
    category: str  # "AGENT", "SKILL", "DAG", "TEST", "INFRA"
    agent_role: Optional[str] = None
    status: str = "PLANNED"  # PLANNED, IN_PROGRESS, DONE, BLOCKED


class AgentPlanner:
    """Plans Jarvis's next evolution cycle based on system gaps."""

    def __init__(self):
        self.auditor = SystemAuditor()

    def plan_next_cycle(self) -> list[EvolutionTask]:
        """
        Analyze the system and create a prioritized task list.
        
        Priority ranking:
        1. CRITICAL audit findings (missing agents, broken tests)
        2. HIGH findings (missing DAGs, no goals)
        3. New skills for existing agents
        4. Performance improvements
        5. Nice-to-have features
        """
        report = self.auditor.full_audit()
        tasks: list[EvolutionTask] = []

        # Priority 1: Critical findings
        for finding in report.findings:
            if finding.severity == "CRITICAL":
                tasks.append(EvolutionTask(
                    title=f"Fix: {finding.description}",
                    description=f"[{finding.category}] at {finding.location}",
                    priority=1,
                    estimated_hours=0.5,
                    category="INFRA",
                ))

        # Priority 2: Missing agent implementations
        for finding in report.findings:
            if finding.category == "MISSING_FILE" and "agents/" in finding.location:
                role = finding.location.split("/")[-1].replace("_agent.py", "")
                tasks.append(EvolutionTask(
                    title=f"Implement {role.upper()} agent",
                    description=f"Create full agent implementation with skills",
                    priority=2,
                    estimated_hours=1.0,
                    category="AGENT",
                    agent_role=role,
                ))

        # Priority 3: Missing orchestration DAGs
        for finding in report.findings:
            if finding.category == "MISSING_FILE" and "orchestration/" in finding.location:
                dag_name = finding.location.split("/")[-1]
                tasks.append(EvolutionTask(
                    title=f"Build {dag_name}",
                    description=f"Create orchestration DAG for {dag_name}",
                    priority=3,
                    estimated_hours=1.5,
                    category="DAG",
                ))

        # Priority 4: Missing data pipelines
        for finding in report.findings:
            if finding.category == "MISSING_FILE" and "data/" in finding.location:
                tasks.append(EvolutionTask(
                    title=f"Build {finding.location.split('/')[-1]}",
                    description=finding.description,
                    priority=4,
                    estimated_hours=1.0,
                    category="INFRA",
                ))

        # Priority 5: Agents without skills (beyond goals.md)
        skills_dir = os.path.join(self.auditor.src_root, "agents", "skills")
        for role in self.auditor.EXPECTED_AGENT_ROLES:
            role_dir = os.path.join(skills_dir, role)
            if os.path.isdir(role_dir):
                py_files = [f for f in os.listdir(role_dir) if f.endswith(".py") and f != "__init__.py"]
                if not py_files:
                    tasks.append(EvolutionTask(
                        title=f"Create first skill for {role}",
                        description=f"Agent {role} has goals but no skill implementations",
                        priority=5,
                        estimated_hours=0.5,
                        category="SKILL",
                        agent_role=role,
                    ))

        # Sort by priority
        tasks.sort(key=lambda t: t.priority)

        logger.info("evolution_plan_created", total_tasks=len(tasks))
        return tasks

    def generate_roadmap_markdown(self, tasks: list[EvolutionTask]) -> str:
        """Generate a human-readable roadmap."""
        lines = [
            "# Jarvis Evolution Roadmap",
            f"",
            f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Total Tasks**: {len(tasks)}",
            f"**Estimated Hours**: {sum(t.estimated_hours for t in tasks):.1f}",
            f"",
        ]

        current_priority = None
        priority_labels = {
            1: "🔴 Priority 1 — Critical",
            2: "🟠 Priority 2 — High",
            3: "🟡 Priority 3 — Medium",
            4: "🔵 Priority 4 — Normal",
            5: "⚪ Priority 5 — Low",
        }

        for task in tasks:
            if task.priority != current_priority:
                current_priority = task.priority
                label = priority_labels.get(current_priority, f"Priority {current_priority}")
                lines.append(f"## {label}")
                lines.append("")

            status_icon = {"PLANNED": "⬜", "IN_PROGRESS": "🔄", "DONE": "✅", "BLOCKED": "🚫"}.get(task.status, "⬜")
            lines.append(f"- {status_icon} **{task.title}** ({task.estimated_hours:.1f}h) [{task.category}]")
            lines.append(f"  - {task.description}")

        lines.append("")
        return "\n".join(lines)
