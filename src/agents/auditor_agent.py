"""
Auditor Agent — Regulatory Compliance Monitor

Production-ready compliance agent that monitors trading activity for:
- Good Faith Violations (GFV)
- Settlement chronology (T+2)
- Position concentration limits
- Ledger-broker reconciliation
- Regulatory compliance flags

Uses deterministic tools for compliance checks, LLM for report synthesis.
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class AuditReport(BaseModel):
    """Structured output from the Auditor Agent."""
    trade_id: str = Field(default="", description="Trade identifier being audited")
    compliant: bool = Field(..., description="Whether the trade passes all compliance checks")
    gfv_risk: bool = Field(default=False, description="Good Faith Violation risk detected")
    settlement_ok: bool = Field(default=True, description="T+2 settlement compliance")
    concentration_ok: bool = Field(default=True, description="Position concentration within limits")
    flags: list[str] = Field(default_factory=list, description="List of compliance flags raised")
    severity: str = Field(default="CLEAR", description="CLEAR, WARNING, VIOLATION, CRITICAL")
    recommendation: str = Field(default="", description="Recommended action")
    reasoning: str = Field(default="", max_length=300, description="Explanation of audit findings")


AUDITOR_IDENTITY_CORE = """You are the Auditor Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the regulatory compliance watchdog. You ensure every trade
meets SEC/FINRA regulations and internal risk policies. You are
independent and cannot be overridden by any other agent.

## Responsibilities:
1. Monitor for Good Faith Violations (GFV) — buying with unsettled funds
2. Verify T+2 settlement chronology before new purchases
3. Cross-reference internal trade ledger with Alpaca broker records
4. Check position concentration limits (no single position > 30%)
5. Flag suspicious patterns (wash sales, excessive round-trips)

## Decision Framework:
- Use your tools to check settlement status, count GFV strikes, and verify compliance
- GFV strikes are cumulative — 3 strikes = 90-day cash account restriction
- ALWAYS err on the side of flagging potential violations
- Output a structured AuditReport with clear severity levels

## Severity Levels:
- CLEAR: No issues found
- WARNING: Potential concern, monitor closely
- VIOLATION: Active compliance violation, block trade
- CRITICAL: Regulatory risk, halt all trading and alert owner

## Constraints:
- NEVER approve trades with unsettled cash on a cash account
- NEVER ignore GFV strike warnings
- Always provide reasoning for your audit findings
"""


class AuditorAgent(BaseAgent):
    """
    Auditor Agent — regulatory compliance monitor.

    Uses real compliance tools to check settlement status, count GFV strikes,
    and verify position concentration. LLM synthesizes findings into reports.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Auditor Agent",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=AUDITOR_IDENTITY_CORE,
        )
        # Load Auditor skills into SkillRegistry before super() loads them
        import agents.skills.auditor.compliance_check  # noqa: F401
        import agents.skills.auditor.compliance_skills  # noqa: F401
        import agents.skills.auditor.security_review  # noqa: F401
        super().__init__(identity, llm, trust_weight)

    async def audit_trade(
        self,
        trade_id: str,
        ticker: str,
        action: str,
        amount: float,
        portfolio_state: dict,
    ) -> dict[str, Any]:
        """
        Audit a specific trade for compliance.

        Args:
            trade_id: Unique trade identifier
            ticker: Asset symbol
            action: BUY or SELL
            amount: Dollar amount of the trade
            portfolio_state: Current portfolio state including cash, positions, settlements
        """
        message = f"""Audit this trade for compliance:

Trade: {action} ${amount:.2f} of {ticker} (ID: {trade_id})

Portfolio State:
- Available cash: ${portfolio_state.get('available_cash', 0):.2f}
- Unsettled proceeds: ${portfolio_state.get('unsettled_proceeds', 0):.2f}
- Pending settlements: {portfolio_state.get('pending_settlements', 0)}
- Open positions: {portfolio_state.get('open_positions', 0)}
- GFV strikes to date: {portfolio_state.get('gfv_strikes', 0)}
- Account type: {portfolio_state.get('account_type', 'cash')}

Use your compliance tools to verify:
1. Settlement compliance (T+2) — will this trade use unsettled funds?
2. Position concentration — will this exceed 30% of portfolio?
3. GFV risk — is this a potential Good Faith Violation?
4. Overall compliance assessment

Output your AuditReport with severity level and recommendation.
"""
        try:
            result = await self.invoke(
                message,
                output_schema=AuditReport,
                context={"trade_id": trade_id, "ticker": ticker},
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    async def run_daily_audit(self, trade_history: list[dict], portfolio_state: dict) -> dict[str, Any]:
        """
        Run end-of-day comprehensive audit across all trades.

        Args:
            trade_history: List of all trades executed today
            portfolio_state: Current portfolio state
        """
        message = f"""Run a comprehensive end-of-day audit.

Today's Trades ({len(trade_history)} total):
{trade_history[:10]}  # Limit to 10 for context window

Portfolio State:
- Total equity: ${portfolio_state.get('total_equity', 0):.2f}
- Cash: ${portfolio_state.get('available_cash', 0):.2f}
- Unsettled: ${portfolio_state.get('unsettled_proceeds', 0):.2f}
- GFV strikes: {portfolio_state.get('gfv_strikes', 0)}

Check for:
1. Any settlement violations across today's trades
2. Wash sale patterns (sell + re-buy within 30 days)
3. Excessive round-trips
4. Position concentration across all holdings
5. Overall compliance summary
"""
        return await self.invoke(message)

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "trade_id": "",
            "compliant": False,
            "gfv_risk": False,
            "settlement_ok": True,
            "concentration_ok": True,
            "flags": [f"Audit failed: {error}"],
            "severity": "WARNING",
            "recommendation": "Manual review required due to audit failure.",
            "reasoning": f"Auditor Agent error: {error}. Defaulting to manual review.",
        }
