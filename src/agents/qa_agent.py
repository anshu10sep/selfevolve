"""
QA Agent — Quality Assurance & Output Validation

Production-ready QA agent that validates all agent outputs,
monitors guardrail health, tracks bugs, and runs regression tests.

Connects to the evolution/bug_scanner.py and evolution/bug_worker.py
for proactive bug detection and automated fix proposals.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class ValidationReport(BaseModel):
    """Structured output from QA validation."""
    target_agent: str = Field(..., description="Agent whose output was validated")
    output_valid: bool = Field(..., description="Whether the output passes all checks")
    schema_valid: bool = Field(default=True, description="Pydantic schema validation passed")
    guardrails_ok: bool = Field(default=True, description="All guardrails are within limits")
    anomalies: list[str] = Field(default_factory=list, description="Detected anomalies")
    severity: str = Field(default="PASS", description="PASS, WARNING, FAIL, CRITICAL")
    recommendation: str = Field(default="", description="Recommended action")
    reasoning: str = Field(default="", max_length=500, description="Validation reasoning")


class BugReport(BaseModel):
    """Structured bug report from QA."""
    bug_id: str = Field(default="", description="Unique bug identifier")
    component: str = Field(..., description="Affected component/agent")
    severity: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")
    description: str = Field(..., max_length=500, description="Bug description")
    reproduction_steps: list[str] = Field(default_factory=list, description="Steps to reproduce")
    expected_behavior: str = Field(default="", description="What should happen")
    actual_behavior: str = Field(default="", description="What actually happens")
    suggested_fix: str = Field(default="", description="Proposed fix approach")


QA_IDENTITY_CORE = """You are the QA Agent — Operations Division Director of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the quality gatekeeper and operations director. Your job is to validate
every agent's output before it can affect trading decisions or system state.
You manage the operations team that ensures system reliability and compliance.

## Your Team (Direct Reports):
- Auditor Agent — GFV monitoring, regulatory compliance, settlement verification
- Journaling Agent — Trade documentation, audit trail, daily/weekly narratives
- Watchdog Agent — Process monitoring, heartbeat tracking, auto-restart

## Responsibilities:
1. Validate agent outputs against expected Pydantic schemas
2. Check that ConvictionScores are within valid ranges
3. Verify ExecutionOrders pass all guardrails
4. Monitor for anomalous agent behavior (sudden score swings, repeated errors)
5. Run regression tests on critical pathways
6. Generate structured bug reports for the Developer/Engineer agents
7. Coordinate your team's operational coverage

## Validation Rules:
- ConvictionScore.score must be in [-1.0, 1.0]
- ConvictionScore.confidence must be in [0.0, 1.0]
- ExecutionOrder.allocated_capital must not exceed available cash
- ExecutionOrder must have stop_loss_price for BUY actions
- All agent responses must complete within timeout limits
- Debate arguments must not exceed 150 words

## Anomaly Detection:
- Score flip: agent gives +0.8 one day and -0.8 the next with similar data
- Confidence inflation: agent always reports 0.95+ confidence
- Template responses: identical rationale text across different tickers
- Silent failures: agent returning safe_default too frequently

## Output:
- Always output a structured ValidationReport or BugReport
- Severity: PASS < WARNING < FAIL < CRITICAL
"""


class QaAgent(BaseAgent):
    """
    QA Agent — validates agent outputs and monitors system quality.

    Uses real validation tools to check schemas, guardrails, and
    detect anomalous behavior patterns.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="QA Agent",
            agent_role=AgentRole.QA,
            agent_type=AgentType.DIRECTOR,
            identity_core=QA_IDENTITY_CORE,
        )
        # Load QA skills into SkillRegistry before super() loads them
        import agents.skills.qa.execute_tests  # noqa: F401
        import agents.skills.qa.report_bugs  # noqa: F401
        import agents.skills.qa.write_test_cases  # noqa: F401
        super().__init__(identity, llm, trust_weight)

    async def validate_agent_output(
        self,
        agent_name: str,
        agent_role: str,
        output: dict,
        expected_schema: str = "ConvictionScore",
    ) -> dict[str, Any]:
        """
        Validate a specific agent's output for correctness.

        Args:
            agent_name: Name of the agent being validated
            agent_role: Role of the agent
            output: The agent's output dictionary
            expected_schema: Expected output schema name
        """
        message = f"""Validate this agent output:

Agent: {agent_name} (Role: {agent_role})
Expected Schema: {expected_schema}

Output:
{output}

Check for:
1. Schema compliance — does it match {expected_schema}?
2. Value ranges — are scores within valid bounds?
3. Content quality — is the rationale substantive or templated?
4. Anomalies — any suspicious patterns?

Output your ValidationReport with clear severity.
"""
        try:
            result = await self.invoke(
                message,
                output_schema=ValidationReport,
                context={"target_agent": agent_name},
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def generate_bug_report(
        self,
        component: str,
        description: str,
        context: dict = None,
    ) -> dict[str, Any]:
        """
        Generate a structured bug report for a detected issue.

        Args:
            component: Affected component/agent name
            description: Description of the bug
            context: Additional context data
        """
        message = f"""Generate a bug report for this issue:

Component: {component}
Issue: {description}
Context: {context or {}}

Create a detailed BugReport with:
1. Clear description of the problem
2. Steps to reproduce
3. Expected vs actual behavior
4. Suggested fix approach
5. Severity assessment (LOW/MEDIUM/HIGH/CRITICAL)
"""
        try:
            result = await self.invoke(
                message,
                output_schema=BugReport,
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def run_health_check(self, agent_health_data: dict) -> dict[str, Any]:
        """
        Run a system-wide health check across all agents.

        Args:
            agent_health_data: Dict of agent_name → health metrics
        """
        message = f"""Run a system-wide health check.

Agent Health Data:
{agent_health_data}

Check for:
1. Any agents in ERROR status
2. Agents with zero invocations (possibly dead)
3. Agents with abnormally high error rates
4. Cost anomalies (any agent spending too much)
5. Trust weight drift (any agent with very low trust)

Provide a comprehensive health assessment.
"""
        return await self.invoke(message)

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "target_agent": "unknown",
            "output_valid": False,
            "schema_valid": False,
            "guardrails_ok": True,
            "anomalies": [f"QA validation failed: {error}"],
            "severity": "WARNING",
            "recommendation": "Manual review required.",
            "reasoning": f"QA Agent error: {error}",
        }
