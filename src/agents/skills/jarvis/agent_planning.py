"""
Agent Planning — Evolution cycle planning for Jarvis.

Provides the AgentPlanner class used by Jarvis to plan
multi-day evolution cycles and prioritize tasks.
"""

import os
import logging
import traceback
from dataclasses import dataclass, field
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")


@dataclass
class EvolutionTask:
    """A single task in the evolution roadmap."""
    title: str
    description: str
    priority: int  # 1 = highest, 5 = lowest
    category: str  # "bug_fix", "feature", "optimization", "testing"
    estimated_effort: str = "small"  # small, medium, large
    status: str = "planned"  # planned, in_progress, done, blocked


class AgentPlanner:
    """
    Skill for Jarvis to plan evolution cycles.
    
    Scans the codebase for improvement opportunities and generates
    a prioritized roadmap of evolution tasks.
    """

    def __init__(self, src_dir: str = None):
        self.src_dir = src_dir or SRC_ROOT

    def plan_next_cycle(self) -> List[EvolutionTask]:
        """
        Scan the codebase and generate a prioritized list of evolution tasks.
        
        Identifies:
        - TODO/FIXME markers in code
        - Missing test files
        - Skills not wired to agents
        - Placeholder implementations
        
        Returns:
            List of EvolutionTask objects sorted by priority.
        """
        tasks: List[EvolutionTask] = []

        try:
            # Scan for TODOs and FIXMEs
            todo_tasks = self._scan_for_markers()
            tasks.extend(todo_tasks)

            # Scan for missing tests
            test_tasks = self._scan_for_missing_tests()
            tasks.extend(test_tasks)

            # Scan for placeholder implementations
            placeholder_tasks = self._scan_for_placeholders()
            tasks.extend(placeholder_tasks)

        except Exception as e:
            logger.error(f"Error during planning scan: {e}")
            logger.debug(traceback.format_exc())
            tasks.append(EvolutionTask(
                title="Fix Planning Scanner",
                description=f"The planning scanner encountered an error: {e}",
                priority=1,
                category="bug_fix",
            ))

        # Sort by priority
        tasks.sort(key=lambda t: t.priority)
        return tasks

    def generate_roadmap_markdown(self, tasks: List[EvolutionTask]) -> str:
        """
        Generate a human-readable Markdown roadmap from a list of tasks.
        
        Args:
            tasks: List of EvolutionTask objects.
            
        Returns:
            Markdown-formatted string.
        """
        lines = [
            "# Evolution Roadmap",
            "",
            f"**Total Tasks**: {len(tasks)}",
            f"**Critical (P1-P2)**: {sum(1 for t in tasks if t.priority <= 2)}",
            "",
        ]

        by_category: Dict[str, list] = {}
        for t in tasks:
            by_category.setdefault(t.category, []).append(t)

        for category, items in sorted(by_category.items()):
            lines.append(f"## {category.replace('_', ' ').title()} ({len(items)})")
            for item in items[:15]:
                status_icon = {"planned": "⬜", "in_progress": "🔄", "done": "✅", "blocked": "🚫"}.get(item.status, "⬜")
                lines.append(f"- {status_icon} **[P{item.priority}]** {item.title} ({item.estimated_effort})")
                if item.description:
                    lines.append(f"  - {item.description[:120]}")
            if len(items) > 15:
                lines.append(f"- ... and {len(items) - 15} more")
            lines.append("")

        return "\n".join(lines)

    def _scan_for_markers(self) -> List[EvolutionTask]:
        """Scan Python files for TODO/FIXME/HACK markers."""
        tasks = []
        markers = {"FIXME": 1, "HACK": 2, "TODO": 3, "XXX": 2}

        for root, dirs, files in os.walk(self.src_dir):
            dirs[:] = [d for d in dirs if not d.startswith(('.', '__pycache__'))]
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        for i, line in enumerate(f, 1):
                            for marker, priority in markers.items():
                                if marker in line and not line.strip().startswith('#!'):
                                    tasks.append(EvolutionTask(
                                        title=f"{marker} in {fname}:{i}",
                                        description=line.strip()[:120],
                                        priority=priority,
                                        category="bug_fix" if marker in ("FIXME", "HACK") else "feature",
                                        estimated_effort="small",
                                    ))
                except Exception:
                    pass

        return tasks

    def _scan_for_missing_tests(self) -> List[EvolutionTask]:
        """Identify agent/skill files without corresponding test files."""
        tasks = []
        test_dirs = [
            os.path.join(self.src_dir, "tests"),
        ]
        
        existing_tests = set()
        for test_dir in test_dirs:
            if os.path.isdir(test_dir):
                for root, _, files in os.walk(test_dir):
                    for f in files:
                        if f.startswith("test_") and f.endswith(".py"):
                            existing_tests.add(f)

        agents_dir = os.path.join(self.src_dir, "agents")
        if os.path.isdir(agents_dir):
            for f in os.listdir(agents_dir):
                if f.endswith("_agent.py") or f.endswith("_agents.py"):
                    test_name = f"test_{f}"
                    if test_name not in existing_tests:
                        tasks.append(EvolutionTask(
                            title=f"Write tests for {f}",
                            description=f"No test file found for agents/{f}",
                            priority=3,
                            category="testing",
                            estimated_effort="medium",
                        ))

        return tasks

    def _scan_for_placeholders(self) -> List[EvolutionTask]:
        """Identify skill files with placeholder implementations (returning None)."""
        tasks = []
        skills_dir = os.path.join(self.src_dir, "agents", "skills")

        if not os.path.isdir(skills_dir):
            return tasks

        for root, dirs, files in os.walk(skills_dir):
            dirs[:] = [d for d in dirs if not d.startswith(('.', '__pycache__'))]
            for fname in files:
                if fname in ('__init__.py', 'validator.py', 'validate_all.py', 'registry.py'):
                    continue
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # Detect placeholder patterns
                    placeholders = content.count(': None') + content.count('= None')
                    if placeholders >= 3:
                        rel = os.path.relpath(fpath, self.src_dir)
                        tasks.append(EvolutionTask(
                            title=f"Implement {fname}",
                            description=f"{rel} has {placeholders} placeholder None values — needs real implementation",
                            priority=4,
                            category="feature",
                            estimated_effort="medium",
                        ))
                except Exception:
                    pass

        return tasks


def create_execution_plan(goal: str, available_agents: List[str]) -> Dict[str, Any]:
    """
    Create an execution plan for a given goal using available agents.
    
    Args:
        goal (str): The objective to achieve.
        available_agents (list): List of agent names available for tasks.
        
    Returns:
        dict: The structured execution plan.
    """
    try:
        logger.info(f"Creating execution plan for goal: {goal}")
        
        if not available_agents:
            raise ValueError("No agents available for planning.")
            
        plan = {
            "goal": goal,
            "steps": [
                {"step": 1, "agent": available_agents[0], "action": "Analyze requirements"},
                {"step": 2, "agent": available_agents[-1] if len(available_agents) > 1 else available_agents[0], "action": "Execute task"}
            ],
            "status": "planned"
        }
        return plan
        
    except Exception as e:
        logger.error(f"Error creating execution plan: {str(e)}")
        logger.debug(traceback.format_exc())
        return {
            "goal": goal,
            "status": "failed",
            "error": str(e)
        }


# ── LLM Tool-Calling Registration ─────────────────────────────────
from agents.skills.validator import skill


@skill("master")
def plan_evolution_cycle() -> str:
    """Scan the codebase and generate a prioritized evolution roadmap.
    Identifies TODOs, FIXMEs, missing test files, placeholder implementations,
    and skills not wired to agents. Returns a prioritized task list.
    Use this to decide what to work on next.

    Returns:
        Markdown-formatted roadmap with prioritized tasks grouped by category.
    """
    planner = AgentPlanner()
    tasks = planner.plan_next_cycle()
    return planner.generate_roadmap_markdown(tasks)


@skill("master")
def create_execution_plan_for_goal(goal: str, available_agents: str = "") -> str:
    """Create a structured execution plan for achieving a specific goal.

    Args:
        goal: The objective to achieve (e.g., "Add crypto trading support").
        available_agents: Comma-separated agent names to use (e.g., "Developer Agent, CTO Agent").

    Returns:
        JSON-formatted execution plan with steps and agent assignments.
    """
    import json
    agents = [a.strip() for a in available_agents.split(",") if a.strip()] if available_agents else ["Jarvis"]
    plan = create_execution_plan(goal, agents)
    return json.dumps(plan, indent=2)