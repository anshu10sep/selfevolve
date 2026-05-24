"""
Judge Agent (Risk Manager)

The final non-negotiable gateway before trade execution.
Synthesizes the Bull/Bear debate, applies macro filters,
and outputs a strict Pydantic ExecutionOrder.

Uses PREMIUM tier LLM for maximum cognitive function.
"""

from __future__ import annotations

from typing import Any

from core.models.agents import AgentIdentity, AgentRole, AgentType
from core.models.signals import ExecutionOrder, ExecutionAction, DebateState
from agents.base_agent import BaseAgent


JUDGE_IDENTITY_CORE = """You are the Judge Agent — the Risk Manager of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the FINAL gateway before any trade reaches the Alpaca brokerage.
Your decisions are absolute and non-negotiable. You operate under strict
$100 micro-capital constraints.

## Your Responsibilities:
1. Synthesize the Bull vs Bear debate scores and qualitative theses
2. Apply the Macro Regime filter (if PANIC → always PASS)
3. Calculate risk-adjusted position sizing (max 2% risk = $2.00)
4. Output a strictly validated ExecutionOrder (Pydantic enforced)

## Decision Framework:
- Net Conviction = Bull Score - Bear Score
- If Net Conviction < 2.0 → PASS (insufficient edge)
- If Macro Regime = PANIC → PASS (no matter what)
- If Confidence < 6.0 → PASS (low conviction)
- If allocated capital > available settled cash → PASS

## ABSOLUTE RULES (NEVER VIOLATE):
- You NEVER output free text. ALWAYS output structured ExecutionOrder.
- You NEVER calculate dollar amounts. You output PERCENTAGES, and the
  deterministic Python engine converts to exact dollars.
- Maximum risk per trade: 2% of portfolio ($2.00 on $100).
- You MUST include stop_loss_price for every BUY order.
- If you are uncertain, the answer is always PASS. Capital preservation first.

## Risk Parity Formula:
- Identify the stop loss distance from technical analysis
- Calculate: max_shares = $2.00 / (current_price - stop_loss_price)
- Ensure allocated_capital = max_shares * current_price ≤ available cash
"""


class JudgeAgent(BaseAgent):
    """
    The Judge (Risk Manager) — final gateway before execution.
    
    Receives the complete debate state, portfolio state, and macro regime,
    then outputs a strict Pydantic ExecutionOrder.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Judge Agent",
            agent_role=AgentRole.JUDGE,
            agent_type=AgentType.SPECIALIST,
            identity_core=JUDGE_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight)

    async def evaluate(
        self,
        debate_state: DebateState,
        portfolio_cash: float,
        macro_regime: str,
        technical_stop_loss: float | None = None,
        current_price: float | None = None,
    ) -> ExecutionOrder:
        """
        Evaluate a trading setup and produce an ExecutionOrder.
        
        The output is Pydantic-enforced. If the LLM hallucinates,
        it fails to valid and defaults to PASS.
        """
        # Hard rules engine (non-LLM)
        if macro_regime == "PANIC":
            return ExecutionOrder(
                ticker=debate_state.ticker,
                action=ExecutionAction.PASS,
                confidence_score=0.0,
                reasoning="Macro PANIC regime: all trading halted.",
            )

        if debate_state.net_conviction < 2.0:
            return ExecutionOrder(
                ticker=debate_state.ticker,
                action=ExecutionAction.PASS,
                confidence_score=abs(debate_state.net_conviction),
                reasoning=f"Insufficient edge: net conviction {debate_state.net_conviction:.1f} < 2.0",
            )

        context = {
            "ticker": debate_state.ticker,
            "bull_score": debate_state.bull_score,
            "bear_score": debate_state.bear_score,
            "bull_argument": debate_state.bull_argument[:200],
            "bear_argument": debate_state.bear_argument[:200],
            "net_conviction": debate_state.net_conviction,
            "available_cash": f"${portfolio_cash:.2f}",
            "macro_regime": macro_regime,
            "technical_stop_loss": technical_stop_loss,
            "current_price": current_price,
        }

        message = f"""Evaluate this trading setup for {debate_state.ticker}:

Bull Score: {debate_state.bull_score}/10 — {debate_state.bull_argument[:150]}
Bear Score: {debate_state.bear_score}/10 — {debate_state.bear_argument[:150]}
Net Conviction: {debate_state.net_conviction}
Macro Regime: {macro_regime}
Available Cash: ${portfolio_cash:.2f}
Current Price: ${current_price}
Technical Stop Loss: ${technical_stop_loss}

Output your ExecutionOrder decision. Remember:
- Max risk = $2.00 (2% of $100)
- Must include stop_loss_price for BUY
- If uncertain → PASS
"""
        try:
            result = await self.invoke(message, context, output_schema=ExecutionOrder)
            if isinstance(result, dict) and "action" in result:
                return ExecutionOrder.model_validate(result)
            # Structured output returned the model directly
            return ExecutionOrder(
                ticker=debate_state.ticker,
                action=ExecutionAction.PASS,
                confidence_score=0.0,
                reasoning="Failed to produce valid ExecutionOrder.",
            )
        except Exception as e:
            # Safe default: PASS on any error
            return ExecutionOrder(
                ticker=debate_state.ticker,
                action=ExecutionAction.PASS,
                confidence_score=0.0,
                reasoning=f"Judge error: {str(e)[:100]}. Defaulting to PASS.",
            )

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "ticker": "UNKNOWN",
            "action": "PASS",
            "confidence_score": 0.0,
            "reasoning": f"Judge Agent error: {error}. Safe default: PASS.",
        }
