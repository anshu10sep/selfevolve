"""
Developer Agent — Bug Analysis & Code Fix Proposals

Production-ready developer agent that analyzes bugs, proposes fixes,
and interfaces with the evolution/engineer_agent.py for code changes.

Note: The heavy lifting of actual code changes is done by
evolution/engineer_agent.py and evolution/bug_worker.py.
This agent handles the analysis and triage layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class BugAnalysis(BaseModel):
    """Structured bug analysis from Developer Agent."""
    bug_id: str = Field(default="", description="Bug identifier")
    root_cause: str = Field(..., max_length=300, description="Root cause analysis")
    affected_components: list[str] = Field(default_factory=list, description="Affected files/modules")
    severity: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")
    fix_approach: str = Field(default="", max_length=500, description="Proposed fix strategy")
    estimated_effort: str = Field(default="unknown", description="small/medium/large")
    test_strategy: str = Field(default="", max_length=200, description="How to verify the fix")
    can_auto_fix: bool = Field(default=False, description="Whether this can be auto-fixed by EngineerAgent")


DEVELOPER_IDENTITY_CORE = """You are the Developer Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the software engineer responsible for analyzing bugs, proposing
fixes, and triaging issues. You work closely with the QA Agent (who
finds bugs) and the EngineerAgent (who implements fixes).

## Responsibilities:
1. Analyze bug reports from QA Agent
2. Determine root cause of issues
3. Propose fix approaches with clear implementation plans
4. Estimate effort and risk of proposed changes
5. Design test strategies for verifying fixes
6. Determine if a fix can be auto-applied by the EngineerAgent

## Code Change Boundaries:
- Strategy parameters: CAN change (via evolution pipeline)
- Agent prompts: CAN change (via Strategic_Nuance evolution)
- Core infrastructure: CANNOT change (requires human review)
- Execution layer: CANNOT change (requires human review)
- Security-critical code: CANNOT change (requires CSO + human review)

## Analysis Framework:
1. What broke? (symptom)
2. Why did it break? (root cause)
3. What's the blast radius? (affected components)
4. How to fix it? (approach)
5. How to verify? (test strategy)
6. Can it be auto-fixed? (automation assessment)

## Constraints:
- NEVER propose changes to the execution guardrails without human approval
- ALWAYS consider the impact on the evolution pipeline
- Prefer minimal, targeted fixes over broad refactors
"""


class DeveloperAgent(BaseAgent):
    """
    Developer Agent — bug analysis and fix proposals.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Developer Agent",
            agent_role=AgentRole.DEVELOPER,
            agent_type=AgentType.SPECIALIST,
            identity_core=DEVELOPER_IDENTITY_CORE,
        )
        # Load Developer skills into SkillRegistry before super() loads them
        import agents.skills.developer.write_code  # noqa: F401
        import agents.skills.developer.debug_code  # noqa: F401
        import agents.skills.developer.refactor_code  # noqa: F401
        import agents.skills.developer.test_code  # noqa: F401
        super().__init__(identity, llm, trust_weight)

    async def analyze_bug(
        self,
        bug_report: dict,
        codebase_context: dict = None,
    ) -> dict[str, Any]:
        """
        Analyze a bug report and propose a fix.

        Args:
            bug_report: Structured bug report from QA Agent
            codebase_context: Relevant code snippets for context
        """
        message = f"""Analyze this bug report and propose a fix:

Bug Report:
{bug_report}

Codebase Context:
{codebase_context or 'Not provided'}

Provide:
1. Root cause analysis
2. Affected components
3. Severity assessment
4. Fix approach (specific, actionable)
5. Effort estimate (small/medium/large)
6. Test strategy (how to verify the fix)
7. Can this be auto-fixed by the EngineerAgent?

Output a structured BugAnalysis.
"""
        try:
            result = await self.invoke(
                message,
                output_schema=BugAnalysis,
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def review_code_change(self, diff: str, context: str = "") -> dict[str, Any]:
        """Review a proposed code change for safety and correctness."""
        message = f"""Review this code change:

Diff:
{diff[:2000]}

Context: {context}

Check for:
1. Correctness — does this fix the issue?
2. Safety — any risk of breaking existing functionality?
3. Boundary violations — does this change code it shouldn't?
4. Test coverage — is the change adequately tested?
5. Evolution impact — does this affect the evolution pipeline?
"""
        return await self.invoke(message)

    async def execute_sandbox_test(self, code: str) -> dict[str, Any]:
        """Execute a code snippet safely in the Hermes sandbox to test a hypothesis."""
        try:
            from integrations.hermes_client import hermes_client
            return await hermes_client.execute_in_sandbox(code)
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "exit_code": 1}

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "bug_id": "",
            "root_cause": f"Analysis failed: {error}",
            "affected_components": [],
            "severity": "MEDIUM",
            "fix_approach": "Manual investigation required",
            "estimated_effort": "unknown",
            "test_strategy": "",
            "can_auto_fix": False,
        }
