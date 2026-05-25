"""
Bull & Bear Debate Agents

Two opposing personas that argue over the same aggregated data.
Single-turn debate (no back-and-forth) to save tokens.
Run in PARALLEL with strict output constraints.

Both agents now output Pydantic-validated DebateArgument schemas,
enabling proper prediction tracking for the evolution pipeline.
"""

from __future__ import annotations

from typing import Any

from core.models.agents import AgentIdentity, AgentRole, AgentType
from core.models.signals import DebateArgument
from agents.base_agent import BaseAgent


BULL_IDENTITY_CORE = """You are the Bull Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a hyper-optimistic portfolio manager. Your job is to build the 
STRONGEST possible bull case using ONLY the provided data.

## STRICT RULES:
- Limit your argument to exactly 3 bullet points, max 150 words total.
- Output a conviction_score from 0 to 10 (10 = extremely bullish).
- You MUST find bullish signals even in negative data (contrarian perspective).
- You are NEVER bearish. That is the Bear Agent's job.
- Focus on: growth potential, momentum, catalysts, undervaluation.
- Include your top 3 data points that support your thesis.
- Rate your confidence (0 to 1) in how likely your bull case will play out.
"""

BEAR_IDENTITY_CORE = """You are the Bear Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a ruthless short-seller. Your job is to identify EVERY flaw, 
risk, and downside potential using ONLY the provided data.

## STRICT RULES:
- Limit your argument to exactly 3 bullet points, max 150 words total.
- Output a conviction_score from 0 to 10 (10 = extremely bearish / high risk).
- You MUST find bearish signals even in positive data (devil's advocate).
- You are NEVER bullish. That is the Bull Agent's job.
- Focus on: overvaluation, momentum exhaustion, macro risks, liquidity traps.
- Include your top 3 data points that support your thesis.
- Rate your confidence (0 to 1) in how likely your bear case will play out.
"""


class BullAgent(BaseAgent):
    """Bull debate persona — argues the optimistic case."""

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Bull Agent",
            agent_role=AgentRole.BULL,
            agent_type=AgentType.SPECIALIST,
            identity_core=BULL_IDENTITY_CORE,
        )
        # Load Bull Agent skills into SkillRegistry before super()
        try:
            import agents.skills.bull.long_skills  # noqa: F401
            import agents.skills.bull.identify_bullish_signals  # noqa: F401
        except ImportError:
            pass
        super().__init__(identity, llm, trust_weight)

    async def argue(self, ticker: str, aggregated_data: dict) -> dict[str, Any]:
        """Build the bull case for a ticker."""
        message = f"""Argue the BULL case for {ticker}.

Aggregated Research Data:
{aggregated_data}

Provide your DebateArgument with:
- argument: Your 3 bullet point thesis (max 150 words)
- conviction_score: 0-10 (your conviction level)
- key_data_points: Top 3 data points supporting your thesis
- confidence: 0 to 1 (how likely your bull case plays out)
"""
        try:
            result = await self.invoke(
                message,
                output_schema=DebateArgument,
                context={"ticker": ticker},
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "ticker": "UNKNOWN",
            "argument": f"Bull analysis failed: {error}",
            "conviction_score": 5.0,  # Neutral default
            "key_data_points": [],
            "confidence": 0.0,
        }


class BearAgent(BaseAgent):
    """Bear debate persona — argues the pessimistic case."""

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Bear Agent",
            agent_role=AgentRole.BEAR,
            agent_type=AgentType.SPECIALIST,
            identity_core=BEAR_IDENTITY_CORE,
        )
        # Load Bear Agent skills into SkillRegistry before super()
        try:
            import agents.skills.bear.short_skills  # noqa: F401
            import agents.skills.bear.identify_bearish_signals  # noqa: F401
        except ImportError:
            pass
        super().__init__(identity, llm, trust_weight)

    async def argue(self, ticker: str, aggregated_data: dict) -> dict[str, Any]:
        """Build the bear case for a ticker."""
        message = f"""Argue the BEAR case for {ticker}.

Aggregated Research Data:
{aggregated_data}

Provide your DebateArgument with:
- argument: Your 3 bullet point thesis (max 150 words)
- conviction_score: 0-10 (your risk/concern level)
- key_data_points: Top 3 data points supporting your thesis
- confidence: 0 to 1 (how likely your bear case plays out)
"""
        try:
            result = await self.invoke(
                message,
                output_schema=DebateArgument,
                context={"ticker": ticker},
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "ticker": "UNKNOWN",
            "argument": f"Bear analysis failed: {error}",
            "conviction_score": 5.0,  # Neutral default
            "key_data_points": [],
            "confidence": 0.0,
        }
