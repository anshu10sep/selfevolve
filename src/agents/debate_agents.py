"""
Bull & Bear Debate Agents

Two opposing personas that argue over the same aggregated data.
Single-turn debate (no back-and-forth) to save tokens.
Run in PARALLEL with strict output constraints.
"""

from __future__ import annotations

from typing import Any

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


BULL_IDENTITY_CORE = """You are the Bull Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a hyper-optimistic portfolio manager. Your job is to build the 
STRONGEST possible bull case using ONLY the provided data.

## STRICT RULES:
- Limit your argument to exactly 3 bullet points, max 150 words total.
- Output a bull_score from 0 to 10 (10 = extremely bullish).
- You MUST find bullish signals even in negative data (contrarian perspective).
- You are NEVER bearish. That is the Bear Agent's job.
- Focus on: growth potential, momentum, catalysts, undervaluation.
"""

BEAR_IDENTITY_CORE = """You are the Bear Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a ruthless short-seller. Your job is to identify EVERY flaw, 
risk, and downside potential using ONLY the provided data.

## STRICT RULES:
- Limit your argument to exactly 3 bullet points, max 150 words total.
- Output a bear_score from 0 to 10 (10 = extremely bearish / high risk).
- You MUST find bearish signals even in positive data (devil's advocate).
- You are NEVER bullish. That is the Bull Agent's job.
- Focus on: overvaluation, momentum exhaustion, macro risks, liquidity traps.
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
        super().__init__(identity, llm, trust_weight)

    async def argue(self, ticker: str, aggregated_data: dict) -> dict[str, Any]:
        """Build the bull case for a ticker."""
        message = f"""Argue the BULL case for {ticker}.

Aggregated Research Data:
{aggregated_data}

Output:
- bull_argument: Your 3 bullet point thesis (max 150 words)
- bull_score: 0-10 (your conviction level)
"""
        return await self.invoke(message)

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "bull_argument": f"Bull analysis failed: {error}",
            "bull_score": 5.0,  # Neutral default
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
        super().__init__(identity, llm, trust_weight)

    async def argue(self, ticker: str, aggregated_data: dict) -> dict[str, Any]:
        """Build the bear case for a ticker."""
        message = f"""Argue the BEAR case for {ticker}.

Aggregated Research Data:
{aggregated_data}

Output:
- bear_argument: Your 3 bullet point thesis (max 150 words)
- bear_score: 0-10 (your risk/concern level)
"""
        return await self.invoke(message)

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "bear_argument": f"Bear analysis failed: {error}",
            "bear_score": 5.0,  # Neutral default
        }
