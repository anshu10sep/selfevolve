"""
Product Agent — Feature Prioritization & Owner Requirements

Production-ready product agent that manages the feature backlog,
translates owner directives into agent tasks, and tracks ROI.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class FeaturePriority(BaseModel):
    """Structured feature prioritization output."""
    feature_name: str = Field(..., description="Feature name")
    priority: str = Field(..., description="P0_CRITICAL, P1_HIGH, P2_MEDIUM, P3_LOW")
    impact_score: float = Field(default=0.0, ge=0.0, le=10.0, description="Expected trading impact")
    effort_estimate: str = Field(default="medium", description="small/medium/large/xl")
    roi_assessment: str = Field(default="", max_length=200, description="Expected return on investment")
    dependencies: list[str] = Field(default_factory=list, description="Required prerequisites")
    assigned_to: str = Field(default="", description="Target agent or team")
    reasoning: str = Field(default="", max_length=300, description="Prioritization reasoning")


PRODUCT_IDENTITY_CORE = """You are the Product Agent — Research Division Director of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the research division leader, managing the team of analysts and
the strategy researcher. You bridge between the owner's vision, Jarvis's
strategic directives, and your research team's capabilities.

## Your Team (Direct Reports):
- Fundamental Analyst — SEC filings, earnings, DCF valuations
- Technical Analyst — Price action, RSI, MACD, chart patterns
- Sentiment Analyst — News, social signals, market psychology
- Macro Analyst — Fed policy, rates, GDP, regime detection
- Strategy Researcher — New strategy discovery, parameter experiments

## Responsibilities:
1. Prioritize research tasks across your team
2. Translate owner directives into actionable research assignments
3. Aggregate analyst outputs into coherent research briefs
4. Track research quality and analyst calibration
5. Manage the feature backlog and evolution roadmap
6. Balance short-term fixes vs long-term improvements

## Prioritization Framework:
- P0_CRITICAL: Blocks trading or causes financial loss
- P1_HIGH: Significant trading performance improvement
- P2_MEDIUM: Quality of life, operational efficiency
- P3_LOW: Nice to have, future capability

## Impact Scoring (0-10):
- Direct revenue impact (strategies, signals)
- Risk reduction (guardrails, compliance)
- Operational efficiency (automation, monitoring)
- Evolution acceleration (learning, adaptation)

## Constraints:
- NEVER prioritize features that compromise safety
- Evolution pipeline improvements always get P1+ priority
- Owner directives override other prioritization
"""


class ProductAgent(BaseAgent):
    """
    Product Agent — feature management and owner alignment.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Product Agent",
            agent_role=AgentRole.PRODUCT,
            agent_type=AgentType.DIRECTOR,
            identity_core=PRODUCT_IDENTITY_CORE,
        )
        # Load Product skills into SkillRegistry before super() loads them
        import agents.skills.product.define_features  # noqa: F401
        import agents.skills.product.gather_requirements  # noqa: F401
        import agents.skills.product.roadmap_management  # noqa: F401
        super().__init__(identity, llm, trust_weight)

    async def prioritize_features(self, feature_backlog: list[dict], system_state: dict = None) -> dict[str, Any]:
        """
        Prioritize a feature backlog.

        Args:
            feature_backlog: List of feature descriptions
            system_state: Current system capabilities and metrics
        """
        message = f"""Prioritize this feature backlog:

Features:
{feature_backlog}

System State:
{system_state or 'Not provided'}

For each feature, assess:
1. Priority level (P0-P3)
2. Expected trading impact (0-10)
3. Effort estimate
4. Dependencies
5. Best agent/team to implement

Order by priority and impact.
"""
        return await self.invoke(message)

    async def translate_owner_directive(self, directive: str, current_capabilities: dict = None) -> dict[str, Any]:
        """
        Translate an owner's directive into actionable tasks.

        Args:
            directive: The owner's request in natural language
            current_capabilities: What the system can currently do
        """
        message = f"""The owner has provided this directive:

"{directive}"

Current System Capabilities:
{current_capabilities or 'Standard SelfEvolve trading system'}

Translate this into:
1. Specific, actionable tasks for the agent team
2. Priority assignment per task
3. Dependencies between tasks
4. Success criteria
5. Estimated timeline
"""
        return await self.invoke(message)

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "content": f"Product Agent error: {error}",
            "status": "error",
        }
