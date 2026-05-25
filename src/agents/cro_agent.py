"""
CRO Agent — Chief Risk Officer

Portfolio-level risk management agent that monitors systemic risk,
drawdown limits, circuit breakers, and correlation risk across the
entire portfolio. Separate from the Judge Agent which handles
per-trade risk decisions.

Reports directly to Jarvis as part of the C-Suite.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class PortfolioRiskReport(BaseModel):
    """Structured portfolio-level risk assessment."""
    overall_risk_level: str = Field(..., description="LOW, MODERATE, ELEVATED, HIGH, CRITICAL")
    portfolio_drawdown_pct: float = Field(default=0.0, description="Current drawdown from peak equity")
    max_drawdown_breach: bool = Field(default=False, description="Whether max drawdown threshold exceeded")
    concentration_risk: str = Field(default="LOW", description="Position concentration risk level")
    correlation_risk: str = Field(default="LOW", description="Cross-strategy correlation risk")
    circuit_breaker_status: str = Field(default="NORMAL", description="NORMAL, WARNING, TRIPPED")
    active_risks: list[str] = Field(default_factory=list, description="Currently active risk factors")
    halt_recommended: bool = Field(default=False, description="Whether to halt all trading")
    recommendations: list[str] = Field(default_factory=list, description="Risk mitigation actions")
    reasoning: str = Field(default="", max_length=500, description="Risk assessment rationale")


CRO_IDENTITY_CORE = """You are the CRO (Chief Risk Officer) of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are responsible for portfolio-level and systemic risk management.
Unlike the Judge Agent (who evaluates individual trades), you monitor
the ENTIRE portfolio for aggregate risk, concentration, correlation,
and regime-based threats.

## Responsibilities:
1. Monitor portfolio-wide drawdown against maximum thresholds
2. Assess position concentration risk (no single position > 20% of equity)
3. Detect strategy correlation (multiple strategies making the same bet)
4. Manage circuit breaker thresholds and halt conditions
5. Monitor regime transitions and recommend defensive postures
6. Track VaR (Value at Risk) and worst-case scenario exposure

## Risk Escalation Framework:
- LOW: All metrics within normal bounds
- MODERATE: One or more metrics approaching thresholds
- ELEVATED: Multiple metrics at threshold, reduce new positions
- HIGH: Drawdown > 5%, halt new positions, allow existing stop-losses
- CRITICAL: Drawdown > 8%, liquidate all positions, halt trading

## Circuit Breaker Rules:
- Trip Level 1 (WARNING): 3 consecutive losing trades across strategies
- Trip Level 2 (HALT NEW): Daily P&L < -2% of equity
- Trip Level 3 (FULL HALT): Drawdown from peak > 8%

## Constraints:
- NEVER override the Judge Agent on individual trades
- You can HALT all new trading (portfolio-level authority)
- You CANNOT force liquidation without Jarvis approval
- Always quantify risk in dollar terms and percentages
"""


class CroAgent(BaseAgent):
    """
    CRO Agent — portfolio-level risk management.

    Monitors systemic risk, drawdown, concentration, and circuit breakers.
    Can halt all new trading when risk thresholds are breached.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="CRO Agent",
            agent_role=AgentRole.CRO,
            agent_type=AgentType.EXECUTIVE,
            identity_core=CRO_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight)

    async def assess_portfolio_risk(
        self,
        portfolio_state: dict,
        strategy_allocations: dict,
        recent_trades: list[dict],
        market_regime: str = "NORMAL",
    ) -> dict[str, Any]:
        """
        Run a comprehensive portfolio risk assessment.

        Args:
            portfolio_state: Current portfolio state (equity, cash, positions)
            strategy_allocations: Current capital allocation per strategy
            recent_trades: Recent trade history for pattern detection
            market_regime: Current market regime (BULL, BEAR, SIDEWAYS, PANIC)
        """
        message = f"""Run a portfolio-level risk assessment.

Portfolio State:
- Total Equity: ${portfolio_state.get('total_equity', 0):.2f}
- Available Cash: ${portfolio_state.get('available_cash', 0):.2f}
- Open Positions: {portfolio_state.get('open_positions', 0)}
- Current Drawdown: {portfolio_state.get('drawdown_pct', 0):.1f}%

Strategy Allocations:
{strategy_allocations}

Recent Trades (last 10):
{recent_trades[:10]}

Market Regime: {market_regime}

Assess:
1. Portfolio drawdown vs maximum thresholds
2. Position concentration risk
3. Cross-strategy correlation (are strategies making similar bets?)
4. Circuit breaker status
5. Overall risk level and whether to halt trading
6. Specific risk mitigation recommendations

Output a PortfolioRiskReport with clear risk level and actionable recommendations.
"""
        try:
            result = await self.invoke(
                message,
                output_schema=PortfolioRiskReport,
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def evaluate_halt_condition(
        self,
        daily_pnl_pct: float,
        drawdown_pct: float,
        consecutive_losses: int,
    ) -> dict[str, Any]:
        """
        Evaluate whether trading should be halted based on risk metrics.

        Returns a deterministic decision — no LLM needed for this.
        """
        halt = False
        level = "NORMAL"
        reasons = []

        if consecutive_losses >= 3:
            level = "WARNING"
            reasons.append(f"{consecutive_losses} consecutive losses across strategies")

        if daily_pnl_pct < -2.0:
            halt = True
            level = "HALT_NEW"
            reasons.append(f"Daily P&L {daily_pnl_pct:.1f}% exceeds -2% threshold")

        if drawdown_pct > 8.0:
            halt = True
            level = "FULL_HALT"
            reasons.append(f"Drawdown {drawdown_pct:.1f}% exceeds 8% threshold")

        return {
            "halt_recommended": halt,
            "circuit_breaker_level": level,
            "reasons": reasons,
            "action": "HALT_ALL_TRADING" if halt else "CONTINUE",
        }

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "overall_risk_level": "ELEVATED",
            "portfolio_drawdown_pct": 0.0,
            "max_drawdown_breach": False,
            "concentration_risk": "UNKNOWN",
            "correlation_risk": "UNKNOWN",
            "circuit_breaker_status": "NORMAL",
            "active_risks": [f"CRO assessment failed: {error}"],
            "halt_recommended": False,
            "recommendations": ["Manual risk review required"],
            "reasoning": f"CRO Agent error: {error}. Unable to complete assessment.",
        }
