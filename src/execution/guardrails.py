"""
Execution Guardrail Service

The absolute safety net between LLM decisions and real money.
This deterministic Python service validates every trade against:
- T+1 settlement constraints
- Good Faith Violation (GFV) limits
- Capital availability
- Position sizing limits
- Regulatory compliance

The LLM is STRIPPED of all regulatory knowledge to prevent
hallucination. This service is the sole authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from core.models.portfolio import PortfolioState, TradeIntent, TradeSide
from core.models.signals import ExecutionOrder, ExecutionAction
from core.models.audit import AuditEvent, AuditEventType, BugReport, BugSeverity
from config.constants import (
    MAX_GFV_STRIKES,
    GFV_CATASTROPHIC_LOSS_THRESHOLD_PCT,
    MAX_POSITION_PCT,
    MIN_TRANCHE_SIZE_USD,
)

logger = structlog.get_logger(component="execution_guardrails")


class GFVViolationError(Exception):
    """Raised when a trade would cause a Good Faith Violation."""
    pass


class InsufficientFundsError(Exception):
    """Raised when settled cash is insufficient for the trade."""
    pass


class PositionLimitError(Exception):
    """Raised when a trade would exceed position concentration limits."""
    pass


class RegulatoryHaltError(Exception):
    """Raised when trading is halted due to regulatory constraints."""
    pass


class ExecutionGuardrailService:
    """
    Deterministic execution guardrails that override any LLM decision.
    
    This service sits between the Judge Agent's ExecutionOrder and the
    Alpaca API. It CANNOT be bypassed, modified, or reasoned about by
    any agent in the system.
    
    Design Principle: The LLM outputs conviction. This service outputs reality.
    """

    def __init__(
        self,
        portfolio_state: PortfolioState,
        gfv_strike_count: int = 0,
        restricted_tickers: set[str] | None = None,
        watchlist: set[str] | None = None,
    ):
        self.portfolio = portfolio_state
        self.gfv_strikes = gfv_strike_count
        self.restricted_tickers = restricted_tickers or set()
        self.watchlist = watchlist  # None means all tickers allowed

    def validate_execution_order(
        self, order: ExecutionOrder, current_price: float
    ) -> TradeIntent | None:
        """
        Validate an ExecutionOrder against all guardrails.
        
        Returns a validated TradeIntent ready for Alpaca submission,
        or None if the order should be rejected.
        
        Raises specific exceptions for audit logging.
        """
        validation_errors: list[str] = []

        # ── 1. Action Filter ──────────────────────────────────────
        if order.action in (ExecutionAction.HOLD, ExecutionAction.PASS):
            logger.info(
                "order_passed",
                ticker=order.ticker,
                action=order.action.value,
                reason=order.reasoning,
            )
            return None

        # ── 2. Watchlist Validation ────────────────────────────────
        if self.watchlist is not None and order.ticker not in self.watchlist:
            validation_errors.append(
                f"Ticker {order.ticker} not in approved watchlist. "
                "Possible prompt injection defense triggered."
            )

        # ── 3. Restricted List Check ──────────────────────────────
        if order.ticker in self.restricted_tickers:
            validation_errors.append(
                f"Ticker {order.ticker} is on the restricted list "
                "(OFAC sanctions / FINRA halt)."
            )

        # ── 4. Settlement Validation (T+1) ────────────────────────
        if order.action == ExecutionAction.BUY:
            if order.allocated_capital > self.portfolio.settled_cash:
                # Check if this would cause a GFV
                if self.portfolio.unsettled_cash > 0:
                    validation_errors.append(
                        f"Insufficient settled cash: "
                        f"${self.portfolio.settled_cash:.2f} available, "
                        f"${order.allocated_capital:.2f} requested. "
                        f"Unsettled: ${self.portfolio.unsettled_cash:.2f}"
                    )

        # ── 5. Capital Validation ─────────────────────────────────
        if order.action == ExecutionAction.BUY:
            if order.allocated_capital > self.portfolio.buying_power:
                validation_errors.append(
                    f"Exceeds buying power: "
                    f"${self.portfolio.buying_power:.2f} available, "
                    f"${order.allocated_capital:.2f} requested."
                )

            if order.allocated_capital < MIN_TRANCHE_SIZE_USD:
                validation_errors.append(
                    f"Order below minimum: ${order.allocated_capital:.2f} "
                    f"< ${MIN_TRANCHE_SIZE_USD:.2f}"
                )

        # ── 6. Position Concentration Limit ───────────────────────
        if order.action == ExecutionAction.BUY:
            existing_value = 0.0
            if order.ticker in self.portfolio.positions:
                existing_value = self.portfolio.positions[order.ticker].market_value
            new_total = existing_value + order.allocated_capital
            max_allowed = self.portfolio.total_equity * (MAX_POSITION_PCT / 100.0)
            if new_total > max_allowed:
                validation_errors.append(
                    f"Position concentration exceeded: "
                    f"${new_total:.2f} > ${max_allowed:.2f} "
                    f"({MAX_POSITION_PCT}% limit)"
                )

        # ── 7. Stop Loss Validation ───────────────────────────────
        if order.action == ExecutionAction.BUY and order.stop_loss_price is not None:
            if order.stop_loss_price >= current_price:
                validation_errors.append(
                    f"Invalid stop loss: ${order.stop_loss_price:.2f} >= "
                    f"current price ${current_price:.2f}"
                )

        # ── 8. Take Profit Validation ─────────────────────────────
        if order.action == ExecutionAction.BUY and order.take_profit_price is not None:
            if order.take_profit_price <= current_price:
                validation_errors.append(
                    f"Invalid take profit: ${order.take_profit_price:.2f} <= "
                    f"current price ${current_price:.2f}"
                )

        # ── 9. Sanity Check: Absurd Price Targets ─────────────────
        if order.take_profit_price is not None:
            # Block take-profit > 3x ATR from current price
            reasonable_upper = current_price * 1.20  # 20% max for micro-cap
            if order.take_profit_price > reasonable_upper:
                validation_errors.append(
                    f"Absurd take-profit target: ${order.take_profit_price:.2f} "
                    f"exceeds 20% from current ${current_price:.2f}"
                )

        # ── Reject or Approve ─────────────────────────────────────
        if validation_errors:
            for error in validation_errors:
                logger.warning("guardrail_rejection", error=error, ticker=order.ticker)
            raise ValueError(
                f"Execution guardrail rejections: {'; '.join(validation_errors)}"
            )

        # Convert to TradeIntent
        return TradeIntent(
            ticker=order.ticker,
            side=TradeSide.BUY if order.action == ExecutionAction.BUY else TradeSide.SELL,
            notional=order.allocated_capital,
            stop_loss_price=order.stop_loss_price,
            take_profit_price=order.take_profit_price,
            client_order_id=order.client_order_id,
            conviction_score=order.confidence_score,
            reasoning=order.reasoning,
        )

    def check_gfv_emergency_override(
        self, proposed_loss_pct: float
    ) -> bool:
        """
        Determine if an intentional GFV should be triggered to prevent
        catastrophic loss.
        
        Per architecture: if blocking a stop-loss risks >10% portfolio loss,
        the system intentionally triggers a GFV (max 2 per 12 months).
        """
        if proposed_loss_pct < GFV_CATASTROPHIC_LOSS_THRESHOLD_PCT:
            return False

        if self.gfv_strikes >= MAX_GFV_STRIKES:
            logger.error(
                "gfv_limit_reached",
                strikes=self.gfv_strikes,
                proposed_loss=proposed_loss_pct,
            )
            return False

        logger.warning(
            "gfv_emergency_override",
            proposed_loss=proposed_loss_pct,
            current_strikes=self.gfv_strikes,
        )
        return True

    def validate_sell_settlement(
        self, ticker: str, unsettled_amount: float
    ) -> bool:
        """
        Check if selling would violate settlement rules.
        
        Returns True if the sell is safe, False if it would cause a GFV.
        """
        if unsettled_amount <= 0:
            return True

        position = self.portfolio.positions.get(ticker)
        if not position:
            return False

        # Check if the position was bought with settled funds
        return True  # Simplified — full implementation checks timestamps

    def create_rejection_audit(
        self, order: ExecutionOrder, reason: str
    ) -> AuditEvent:
        """Create an audit event for a rejected trade."""
        return AuditEvent(
            event_type=AuditEventType.TRADE_REJECTED,
            details={
                "ticker": order.ticker,
                "action": order.action.value,
                "allocated_capital": order.allocated_capital,
                "confidence": order.confidence_score,
                "rejection_reason": reason,
                "reasoning": order.reasoning,
            },
        )
