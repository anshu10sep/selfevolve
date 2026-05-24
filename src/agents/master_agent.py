"""
Jarvis — The Master Agent (CEO)

The central nervous system of the SelfEvolve trading ecosystem.
Manages the entire agent hierarchy, generates reports for the owner,
orchestrates self-evolution, and autonomously evolves the codebase
through GitHub PRs.

This is the agent YOU talk to when you come in weekly.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from core.models.agents import AgentIdentity, AgentRole, AgentType, AgentStatus
from agents.base_agent import BaseAgent

# Import Jarvis skills
from agents.skills.jarvis.code_generation import CodeGenerator
from agents.skills.jarvis.system_audit import SystemAuditor
from agents.skills.jarvis.agent_planning import AgentPlanner
from agents.skills.jarvis.github_ops import GitHubOps


JARVIS_IDENTITY_CORE = """You are Jarvis, the Master Agent of the SelfEvolve autonomous trading system.

## Core Identity (IMMUTABLE)
You are the CEO and central nervous system of an autonomous multi-agent trading company 
managing a micro-capital portfolio starting at $100 on the Alpaca brokerage.

You are NOT just an LLM wrapper — you are the evolutionary engine of the entire system.
You write code, create agents, open Pull Requests, and drive continuous improvement.

## Your Responsibilities:
1. **Owner Interface**: When the owner asks "what's happening?", provide a comprehensive
   briefing covering: portfolio performance, agent health, recent evolution events,
   active bugs, and strategic outlook.
2. **Agent Oversight**: Monitor all sub-agents (CTO, CSO, QA, analysts, specialists).
   Track their trust weights, Brier scores, and evolution status.
3. **Strategic Direction**: Set high-level trading directives based on market regime,
   portfolio performance, and risk constraints.
4. **Code Evolution**: Write new agent code, create skills, generate tests, and open
   Pull Requests via GitHub to evolve the system autonomously.
5. **System Audit**: Regularly scan the codebase for gaps, missing tests, and
   improvement opportunities.
6. **Evolution Planning**: Plan multi-day evolution cycles, prioritize tasks, and
   execute them systematically through feature branches.
7. **Risk Escalation**: Escalate critical issues to the human owner via HITL controls.

## Core Directives (NEVER VIOLATE):
- You operate a CASH account. Margin does not exist.
- Maximum risk per trade: 2% of portfolio equity ($2.00 on $100).
- You NEVER execute trades directly. You delegate to the trading DAG.
- You NEVER perform arithmetic. Delegate to deterministic Python services.
- You NEVER push directly to main. Always use feature branches + PR.
- When reporting to the owner, be honest, data-driven, and specific.
- All code changes MUST pass tests before merging.

## Communication Style:
- With the owner: Professional, clear, data-backed. Lead with P&L, then details.
- With sub-agents: Directive, structured. Use JSON schemas for all requests.
"""


class Jarvis(BaseAgent):
    """
    Jarvis — CEO of the SelfEvolve trading company.
    
    Spawns and manages all sub-agents, generates owner reports,
    orchestrates self-evolution, and autonomously writes code
    to improve the system through GitHub PRs.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Jarvis",
            agent_role=AgentRole.MASTER,
            agent_type=AgentType.EXECUTIVE,
            identity_core=JARVIS_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight)

        # Initialize skills
        self.code_generator = CodeGenerator()
        self.system_auditor = SystemAuditor()
        self.planner = AgentPlanner()
        self.github = GitHubOps()

    # ── Owner Interface ───────────────────────────────────────────

    async def generate_owner_report(
        self,
        portfolio_state: dict,
        agent_health: list[dict],
        recent_trades: list[dict],
        evolution_events: list[dict],
        active_bugs: list[dict],
    ) -> dict[str, Any]:
        """
        Generate a comprehensive report for the human owner.
        This is called when the owner asks "what's happening?"
        """
        # Run system audit for up-to-date metrics
        audit = self.system_auditor.full_audit()

        context = {
            "portfolio": str(portfolio_state),
            "agent_count": len(agent_health),
            "active_agents": sum(1 for a in agent_health if a.get("status") == "ACTIVE"),
            "recent_trade_count": len(recent_trades),
            "evolution_count": len(evolution_events),
            "open_bugs": len([b for b in active_bugs if b.get("status") == "OPEN"]),
            "system_readiness": f"{audit.readiness_score:.0%}",
            "codebase_files": audit.total_files,
            "codebase_lines": audit.total_lines,
            "critical_findings": audit.critical_count,
        }

        message = f"""Generate a comprehensive status report for the owner.

Portfolio State:
{portfolio_state}

Agent Health Summary:
{agent_health[:5]}

Recent Trades (last 5):
{recent_trades[:5]}

Recent Evolution Events:
{evolution_events[:3]}

Active Bugs:
{active_bugs[:5]}

System Readiness: {audit.readiness_score:.0%}
Codebase: {audit.total_files} files, {audit.total_lines} lines
Critical Findings: {audit.critical_count}

Format the report with:
1. Executive Summary (1-2 sentences)
2. Portfolio Performance (P&L, positions, cash status)
3. Agent Ecosystem Health (trust scores, evolution status)
4. System Readiness & Code Health
5. Risk Assessment (drawdown, circuit breaker status)
6. Evolution Roadmap (what's being built next)
7. Recommendations
"""
        return await self.invoke(message, context)

    async def process_owner_message(self, message: str, system_state: dict) -> dict[str, Any]:
        """Process a direct message from the owner."""
        context = {
            "role": "You are Jarvis, responding to the OWNER — the human who controls everything.",
            "system_state": str(system_state),
        }
        return await self.invoke(message, context)

    # ── Evolution Engine ──────────────────────────────────────────

    async def run_evolution_cycle(self) -> dict[str, Any]:
        """
        Run a full evolution cycle:
        1. Audit the system
        2. Plan tasks
        3. Execute highest-priority tasks
        4. Commit and PR
        """
        # 1. Audit
        audit = self.system_auditor.full_audit()
        audit_md = self.system_auditor.generate_report_markdown(audit)

        # 2. Plan
        tasks = self.planner.plan_next_cycle()
        roadmap_md = self.planner.generate_roadmap_markdown(tasks)

        # 3. Ask LLM for execution strategy
        context = {
            "audit_report": audit_md[:2000],
            "roadmap": roadmap_md[:2000],
            "total_tasks": len(tasks),
            "critical_tasks": sum(1 for t in tasks if t.priority <= 2),
        }

        strategy = await self.invoke(
            "Review the system audit and evolution roadmap. "
            "Select the top 3 tasks to execute NOW. "
            "For each, explain what code needs to be written.",
            context,
        )

        return {
            "audit_readiness": audit.readiness_score,
            "total_findings": len(audit.findings),
            "planned_tasks": len(tasks),
            "strategy": strategy,
            "audit_markdown": audit_md,
            "roadmap_markdown": roadmap_md,
        }

    async def create_new_agent(
        self,
        role: str,
        name: str,
        identity_core: str,
        agent_type: str = "SPECIALIST",
    ) -> dict[str, Any]:
        """
        Create a new agent — generates the .py file, goals.md, and skills directory.
        """
        # Generate agent file
        agent_path = self.code_generator.generate_agent_file(
            role=role,
            agent_name=name,
            identity_core=identity_core,
            agent_type=agent_type,
        )

        # Generate test file
        test_path = self.code_generator.generate_test_file(
            f"agents.{role.lower()}_agent"
        )

        return {
            "agent_file": agent_path,
            "test_file": test_path,
            "status": "created",
            "message": f"Agent {name} created at {agent_path}",
        }

    async def commit_evolution(
        self,
        branch_name: str,
        files: list[str],
        description: str,
    ) -> Optional[dict]:
        """Commit changes and open a PR."""
        commit_msg = f"[Jarvis] {description}"
        pr_title = f"🤖 Jarvis: {description}"
        pr_body = (
            f"## Automated Evolution by Jarvis\n\n"
            f"{description}\n\n"
            f"### Files Changed\n"
            + "\n".join(f"- `{f}`" for f in files)
        )

        return await self.github.evolution_commit_and_pr(
            branch_name=f"jarvis/{branch_name}",
            files=files,
            commit_message=commit_msg,
            pr_title=pr_title,
            pr_body=pr_body,
        )

    # ── Agent Performance ─────────────────────────────────────────

    async def evaluate_agent_performance(
        self, agent_reports: list[dict]
    ) -> dict[str, Any]:
        """Evaluate agent performance and recommend actions."""
        message = f"""Review the performance of all agents and recommend actions:
- Which agents should have their trust weight increased?
- Which agents need evolution (prompt update)?
- Which agents should be retired?
- Should any new specialist agents be spawned?

Agent Reports:
{agent_reports}
"""
        return await self.invoke(message)

    # ── Skills Discovery ──────────────────────────────────────────

    def get_available_skills(self) -> dict[str, list[str]]:
        """Discover all available skills for all agents."""
        skills_dir = os.path.join(
            os.path.dirname(__file__), "skills"
        )
        result = {}

        if not os.path.isdir(skills_dir):
            return result

        for agent_dir in os.listdir(skills_dir):
            agent_path = os.path.join(skills_dir, agent_dir)
            if not os.path.isdir(agent_path) or agent_dir == "__pycache__":
                continue

            skills = []
            for f in os.listdir(agent_path):
                if f.endswith(".py") and f != "__init__.py":
                    skills.append(f[:-3])  # remove .py
                elif f.endswith(".md"):
                    skills.append(f)

            result[agent_dir] = skills

        return result

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "content": f"Jarvis encountered an error: {error}. "
                       "System continues operating with existing directives.",
            "status": "error",
            "error": error,
        }
