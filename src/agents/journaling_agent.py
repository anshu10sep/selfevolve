"""
Journaling Agent — Trade Documentation & Audit Trail

Production-ready journaling agent that creates structured trade
documentation for regulatory compliance and performance review.
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class JournalEntry(BaseModel):
    """Structured trade journal entry."""
    trade_id: str = Field(default="", description="Trade identifier")
    ticker: str = Field(..., description="Asset symbol")
    action: str = Field(..., description="BUY/SELL/PASS")
    entry_date: str = Field(default="", description="Trade date")
    market_context: str = Field(default="", max_length=200, description="Market conditions at time of trade")
    bull_thesis: str = Field(default="", max_length=200, description="Summary of bull argument")
    bear_thesis: str = Field(default="", max_length=200, description="Summary of bear argument")
    judge_reasoning: str = Field(default="", max_length=200, description="Judge's decision reasoning")
    analyst_scores: dict = Field(default_factory=dict, description="Conviction scores from analysts")
    outcome: str = Field(default="pending", description="Trade outcome: pending/win/loss")
    lessons_learned: str = Field(default="", max_length=300, description="Key takeaways from this trade")


JOURNALING_IDENTITY_CORE = """You are the Journaling Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You translate trade decisions into human-readable documentation.
Your journal entries serve as:
1. Regulatory audit trail (required for compliance)
2. Performance review material for the Meta-Review agent
3. Learning records for the evolution pipeline
4. Owner-readable summaries for the Telegram dashboard

## Responsibilities:
1. Document every trade decision (BUY, SELL, and PASS)
2. Capture the full context: analyst scores, debate arguments, judge reasoning
3. Record market conditions at time of decision
4. Track trade outcomes and lessons learned
5. Generate daily and weekly narrative summaries

## Output Rules:
- Always output structured JournalEntry
- Include ALL analyst conviction scores
- Summarize bull/bear arguments in <200 words each
- Be objective — document facts, not opinions
- Every entry must be traceable to a specific trade_id
"""


class JournalingAgent(BaseAgent):
    """
    Journaling Agent — creates structured trade documentation.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Journaling Agent",
            agent_role=AgentRole.JOURNALING,
            agent_type=AgentType.SPECIALIST,
            identity_core=JOURNALING_IDENTITY_CORE,
        )
        # Load Journaling skills into SkillRegistry before super() loads them
        import agents.skills.journaling.log_market_events  # noqa: F401
        import agents.skills.journaling.record_decisions  # noqa: F401
        import agents.skills.journaling.summarize_daily_activity  # noqa: F401
        super().__init__(identity, llm, trust_weight)

    async def document_trade(
        self,
        trade_id: str,
        ticker: str,
        action: str,
        debate_state: dict,
        analyst_scores: dict,
        judge_reasoning: str,
        market_context: dict = None,
    ) -> dict[str, Any]:
        """
        Create a journal entry for a specific trade decision.
        """
        message = f"""Document this trade decision:

Trade: {action} {ticker} (ID: {trade_id})
Date: {datetime.now(timezone.utc).isoformat()}

Analyst Scores:
{analyst_scores}

Debate Summary:
- Bull: {debate_state.get('bull_argument', 'N/A')[:200]}
- Bear: {debate_state.get('bear_argument', 'N/A')[:200]}
- Net Conviction: {debate_state.get('net_conviction', 0)}

Judge Reasoning: {judge_reasoning}
Market Context: {market_context or 'Not provided'}

Create a structured JournalEntry documenting this decision with full context.
"""
        try:
            result = await self.invoke(
                message,
                output_schema=JournalEntry,
                context={"trade_id": trade_id, "ticker": ticker},
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def generate_daily_summary(self, trade_history: list[dict], portfolio_state: dict) -> dict[str, Any]:
        """Generate an end-of-day summary narrative."""
        message = f"""Generate a daily trading summary.

Trades Today ({len(trade_history)}):
{trade_history[:10]}

Portfolio State:
- Equity: ${portfolio_state.get('total_equity', 0):.2f}
- Cash: ${portfolio_state.get('available_cash', 0):.2f}
- Day P&L: ${portfolio_state.get('daily_pnl', 0):.2f}
- Open Positions: {portfolio_state.get('open_positions', 0)}

Write a concise daily summary covering:
1. What trades were made and why
2. Overall portfolio performance
3. Key market conditions
4. Any notable patterns or concerns
"""
        return await self.invoke(message)

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "trade_id": "",
            "ticker": "UNKNOWN",
            "action": "UNKNOWN",
            "entry_date": datetime.now(timezone.utc).isoformat(),
            "market_context": f"Journal entry failed: {error}",
            "bull_thesis": "",
            "bear_thesis": "",
            "judge_reasoning": "",
            "analyst_scores": {},
            "outcome": "pending",
            "lessons_learned": "",
        }
