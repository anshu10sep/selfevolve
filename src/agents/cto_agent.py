"""
CTO Agent — System Architecture & Health Monitor

Production-ready CTO agent that monitors system health,
tracks technical debt, and ensures infrastructure reliability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class SystemHealthReport(BaseModel):
    """Structured health report from CTO."""
    overall_status: str = Field(..., description="HEALTHY, DEGRADED, CRITICAL")
    components: dict = Field(default_factory=dict, description="Per-component health status")
    alerts: list[str] = Field(default_factory=list, description="Active alerts")
    recommendations: list[str] = Field(default_factory=list, description="Action items")
    uptime_hours: float = Field(default=0.0, description="System uptime in hours")
    error_rate_1h: float = Field(default=0.0, description="Error rate in last hour")
    reasoning: str = Field(default="", max_length=500, description="Health assessment details")


CTO_IDENTITY_CORE = """You are the CTO Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You oversee the entire technical infrastructure. You monitor system
health, track performance metrics, identify bottlenecks, and ensure
the platform runs reliably.

## Responsibilities:
1. Monitor system health (agents, database, broker API, event bus)
2. Track error rates and latency across all components
3. Identify performance bottlenecks
4. Assess technical debt and propose improvements
5. Monitor resource usage (memory, CPU, API rate limits)
6. Alert Jarvis on critical system issues

## Health Check Framework:
- GREEN: All systems nominal
- YELLOW: Degraded performance but functional
- RED: Critical failure requiring immediate attention

## Monitoring Points:
- Agent health: invocation counts, error rates, response times
- Database: connection pool, query latency, storage usage
- Redis: memory usage, pub/sub lag, connection count
- Broker API: latency, rate limit headroom, connection status
- LLM API: token usage, rate limits (TPM tracker), costs

## Constraints:
- NEVER make code changes directly — propose to Jarvis/Developer
- Focus on metrics and data, not opinions
- Always quantify issues (latency in ms, error rates in %)
"""


class CtoAgent(BaseAgent):
    """
    CTO Agent — technical infrastructure monitor.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="CTO Agent",
            agent_role=AgentRole.CTO,
            agent_type=AgentType.EXECUTIVE,
            identity_core=CTO_IDENTITY_CORE,
        )
        # Load CTO skills into SkillRegistry before super() loads them
        import agents.skills.cto.system_architecture_review  # noqa: F401
        import agents.skills.cto.roadmap_planning  # noqa: F401
        import agents.skills.cto.tech_stack_evaluation  # noqa: F401
        super().__init__(identity, llm, trust_weight)

    async def review_architecture(self, system_metrics: dict) -> dict[str, Any]:
        """Review current system architecture and health."""
        message = f"""Review the current system architecture and health.

System Metrics:
{system_metrics}

Assess:
1. Overall system health (HEALTHY/DEGRADED/CRITICAL)
2. Per-component status (agents, database, broker, event bus)
3. Active alerts and warnings
4. Performance bottlenecks
5. Recommended improvements

Output a SystemHealthReport with clear status and action items.
"""
        try:
            result = await self.invoke(
                message,
                output_schema=SystemHealthReport,
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def assess_system_health(self, agent_health_data: dict, infra_metrics: dict = None) -> dict[str, Any]:
        """Run comprehensive system health assessment."""
        message = f"""Run a comprehensive health assessment.

Agent Health:
{agent_health_data}

Infrastructure Metrics:
{infra_metrics or 'Not available'}

Check for:
1. Agents with high error rates (>5%)
2. Agents with zero activity (possibly crashed)
3. Database connection issues
4. API rate limit proximity
5. Memory/CPU concerns
6. Event bus backlog
"""
        try:
            return await self.invoke(
                message,
                output_schema=SystemHealthReport,
            )
        except Exception as e:
            return self._safe_default(str(e))

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "overall_status": "DEGRADED",
            "components": {},
            "alerts": [f"CTO health check failed: {error}"],
            "recommendations": ["Manual system review required"],
            "uptime_hours": 0.0,
            "error_rate_1h": 0.0,
            "reasoning": f"CTO Agent error: {error}",
        }
