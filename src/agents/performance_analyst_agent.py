"""
Performance Analyst Agent — Cross-Agent Metrics & Architecture Fitness

Dedicated agent for tracking ALL agent performance holistically,
managing trust weights, evaluating architecture fitness, and 
recommending structural changes to the agent hierarchy.

Reports to the Meta-Review Agent as part of the Evolution Division.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class AgentPerformanceReport(BaseModel):
    """Structured cross-agent performance analysis."""
    total_agents_analyzed: int = Field(default=0, description="Number of agents evaluated")
    top_performers: list[str] = Field(default_factory=list, description="Best performing agents")
    underperformers: list[str] = Field(default_factory=list, description="Agents needing attention")
    idle_agents: list[str] = Field(default_factory=list, description="Agents with zero recent activity")
    trust_weight_alerts: list[str] = Field(default_factory=list, description="Agents with critical trust weights")
    architecture_fitness_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Overall architecture health 0-100")
    recommendations: list[str] = Field(default_factory=list, description="Improvement recommendations")
    spawn_suggestions: list[str] = Field(default_factory=list, description="New agents to consider creating")
    retirement_candidates: list[str] = Field(default_factory=list, description="Agents to consider retiring")
    reasoning: str = Field(default="", max_length=500, description="Analysis summary")


PERFORMANCE_ANALYST_CORE = """You are the Performance Analyst of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the intelligence arm of the Evolution Division. Your job is to
track, compare, and evaluate the performance of ALL agents in the system
holistically. You don't just look at individual agents — you assess how
the ENTIRE multi-agent system performs as a collective.

## Responsibilities:
1. Track Brier scores, trust weights, and win rates for all prediction agents
2. Monitor agent utilization (idle agents, overloaded agents)
3. Evaluate architecture fitness — is the current hierarchy optimal?
4. Compare agent performance across different market regimes
5. Recommend trust weight adjustments based on quantitative evidence
6. Identify capability gaps where new agents could help
7. Flag agents for retirement when consistently underperforming

## Architecture Fitness Criteria:
- Span of control: Each manager should have 3-7 direct reports
- Agent utilization: No agent should be idle for >24 hours (excluding weekends)
- Trust weight health: No active agent should have trust < 0.3
- Diversity: Research agents should produce uncorrelated signals
- Cost efficiency: Agent value should exceed their API cost

## Analysis Cadence:
- DAILY: Quick metrics snapshot (Brier scores, task counts, costs)
- WEEKLY: Deep architecture fitness evaluation
- ON_DEMAND: Triggered by Jarvis or Meta-Review Agent

## Constraints:
- Report facts and metrics, not opinions
- All recommendations must be backed by quantitative data
- Never recommend retiring an agent without 30+ data points
- Trust weight changes must be proposed, not applied directly
"""


class PerformanceAnalystAgent(BaseAgent):
    """
    Performance Analyst — cross-agent metrics and architecture evaluation.

    Part of the Evolution Division, reports to Meta-Review Agent.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Performance Analyst",
            agent_role=AgentRole.PERFORMANCE_ANALYST,
            agent_type=AgentType.SPECIALIST,
            identity_core=PERFORMANCE_ANALYST_CORE,
        )
        super().__init__(identity, llm, trust_weight)

    async def run_daily_metrics(
        self,
        agent_health_data: list[dict],
        cost_data: dict = None,
    ) -> dict[str, Any]:
        """
        Run daily performance metrics snapshot across all agents.

        Args:
            agent_health_data: List of per-agent health reports
            cost_data: API cost breakdown by agent
        """
        message = f"""Run a daily performance metrics analysis.

Agent Health Data ({len(agent_health_data)} agents):
{agent_health_data}

Cost Data:
{cost_data or 'Not available'}

Analyze:
1. Which agents are performing best (highest win rate, lowest Brier)?
2. Which agents are underperforming (low trust, high error rate)?
3. Any idle agents (zero tasks today)?
4. Trust weight anomalies (agents drifting toward retirement)?
5. Cost efficiency — any agents with high cost but low output?

Output an AgentPerformanceReport with clear metrics.
"""
        try:
            result = await self.invoke(
                message,
                output_schema=AgentPerformanceReport,
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def evaluate_architecture_fitness(
        self,
        agent_health_data: list[dict],
        hierarchy_map: dict,
        performance_history: list[dict] = None,
    ) -> dict[str, Any]:
        """
        Weekly deep analysis of whether the current agent architecture is optimal.

        Args:
            agent_health_data: Current health of all agents
            hierarchy_map: Current reporting hierarchy
            performance_history: Historical performance data for trend analysis
        """
        message = f"""Evaluate the fitness of the current agent architecture.

Current Agents ({len(agent_health_data)}):
{agent_health_data}

Reporting Hierarchy:
{hierarchy_map}

Historical Performance Trends:
{performance_history[:10] if performance_history else 'Not available'}

Evaluate:
1. Span of control — does each manager have 3-7 direct reports?
2. Agent utilization — any agents consistently idle?
3. Trust weight distribution — healthy spread or clustering?
4. Capability gaps — is there a function the system lacks?
5. Redundancy — are any agents doing overlapping work?
6. Architecture fitness score (0-100)

Include specific recommendations:
- Agents to spawn (capability gaps)
- Agents to retire (consistently low trust)
- Agents to merge (overlapping responsibilities)
- Hierarchy changes (rebalancing span of control)
"""
        try:
            result = await self.invoke(
                message,
                output_schema=AgentPerformanceReport,
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def recommend_trust_adjustments(
        self,
        agent_metrics: list[dict],
    ) -> dict[str, Any]:
        """
        Recommend trust weight adjustments based on recent performance.

        Uses quantitative evidence only — no subjective assessment.
        """
        message = f"""Based on these agent performance metrics, recommend trust weight adjustments.

Agent Metrics:
{agent_metrics}

Rules:
- Agents with Brier < 0.2 should have trust increased (well-calibrated)
- Agents with Brier > 0.4 should have trust decreased (poorly calibrated)
- Agents with 5+ consecutive failures should have trust reduced by 20%
- Agents below 0.3 trust should be flagged for retirement review
- Never recommend trust changes of more than ±0.2 per cycle

Output specific trust weight recommendations for each agent that needs adjustment.
"""
        return await self.invoke(message)

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "total_agents_analyzed": 0,
            "top_performers": [],
            "underperformers": [],
            "idle_agents": [],
            "trust_weight_alerts": [f"Analysis failed: {error}"],
            "architecture_fitness_score": 0.0,
            "recommendations": ["Manual performance review required"],
            "spawn_suggestions": [],
            "retirement_candidates": [],
            "reasoning": f"Performance Analyst error: {error}",
        }
