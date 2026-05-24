"""
Unit tests for execution guardrails.

Tests the deterministic safety layer that protects the $100 portfolio
from LLM errors, regulatory violations, and over-allocation.
"""

import pytest
from core.models.signals import ExecutionOrder, ExecutionAction
from core.models.portfolio import PortfolioState, Position, TradeSide
from execution.guardrails import ExecutionGuardrailService


class TestExecutionGuardrails:
    """Tests for the execution guardrail validation service."""

    def setup_method(self):
        """Set up a default portfolio for each test."""
        self.portfolio = PortfolioState(
            total_equity=100.0,
            settled_cash=100.0,
            unsettled_cash=0.0,
            buying_power=100.0,
        )
        self.service = ExecutionGuardrailService(
            portfolio_state=self.portfolio,
            gfv_strike_count=0,
            watchlist={"AAPL", "MSFT", "SPY"},
        )

    def test_pass_order_returns_none(self):
        """PASS orders should return None (no trade intent)."""
        order = ExecutionOrder(
            ticker="AAPL",
            action=ExecutionAction.PASS,
            confidence_score=3.0,
            reasoning="Insufficient conviction",
        )
        result = self.service.validate_execution_order(order, current_price=180.0)
        assert result is None

    def test_hold_order_returns_none(self):
        """HOLD orders should return None (no trade intent)."""
        order = ExecutionOrder(
            ticker="AAPL",
            action=ExecutionAction.HOLD,
            confidence_score=5.0,
            reasoning="Hold existing position",
        )
        result = self.service.validate_execution_order(order, current_price=180.0)
        assert result is None

    def test_valid_buy_order_passes(self):
        """A valid buy order within all limits should pass."""
        order = ExecutionOrder(
            ticker="AAPL",
            action=ExecutionAction.BUY,
            confidence_score=8.0,
            allocated_capital=10.0,
            stop_loss_price=175.0,
            take_profit_price=190.0,
            reasoning="Strong bullish setup",
        )
        result = self.service.validate_execution_order(order, current_price=180.0)
        assert result is not None
        assert result.ticker == "AAPL"
        assert result.side == TradeSide.BUY
        assert result.notional == 10.0

    def test_exceeds_buying_power_rejected(self):
        """Orders exceeding buying power should be rejected."""
        order = ExecutionOrder(
            ticker="AAPL",
            action=ExecutionAction.BUY,
            confidence_score=8.0,
            allocated_capital=150.0,  # Exceeds $100
            stop_loss_price=175.0,
            reasoning="Over-allocated",
        )
        with pytest.raises(ValueError, match="buying power"):
            self.service.validate_execution_order(order, current_price=180.0)

    def test_ticker_not_in_watchlist_rejected(self):
        """Orders for tickers not in watchlist should be rejected."""
        order = ExecutionOrder(
            ticker="TSLA",
            action=ExecutionAction.BUY,
            confidence_score=9.0,
            allocated_capital=10.0,
            stop_loss_price=200.0,
            reasoning="Not in watchlist",
        )
        with pytest.raises(ValueError, match="watchlist"):
            self.service.validate_execution_order(order, current_price=210.0)

    def test_invalid_stop_loss_rejected(self):
        """Stop loss above current price should be rejected."""
        order = ExecutionOrder(
            ticker="AAPL",
            action=ExecutionAction.BUY,
            confidence_score=8.0,
            allocated_capital=10.0,
            stop_loss_price=185.0,  # Above current price of 180
            take_profit_price=195.0,
            reasoning="Bad stop loss",
        )
        with pytest.raises(ValueError, match="stop loss"):
            self.service.validate_execution_order(order, current_price=180.0)

    def test_position_concentration_limit(self):
        """Positions exceeding 20% of portfolio should be rejected."""
        # Add an existing $15 position in AAPL
        self.portfolio.positions["AAPL"] = Position(
            ticker="AAPL",
            quantity=0.08,
            avg_entry_price=180.0,
            current_price=180.0,
            market_value=14.40,
        )
        # Try to add another $10 → total = $24.40 > $20 (20% of $100)
        order = ExecutionOrder(
            ticker="AAPL",
            action=ExecutionAction.BUY,
            confidence_score=8.0,
            allocated_capital=10.0,
            stop_loss_price=175.0,
            reasoning="Would exceed concentration",
        )
        with pytest.raises(ValueError, match="concentration"):
            self.service.validate_execution_order(order, current_price=180.0)

    def test_gfv_emergency_override_granted(self):
        """GFV override should be granted for catastrophic losses."""
        assert self.service.check_gfv_emergency_override(12.0) is True

    def test_gfv_emergency_override_denied_if_strikes_maxed(self):
        """GFV override should be denied when strikes are maxed out."""
        service = ExecutionGuardrailService(
            portfolio_state=self.portfolio,
            gfv_strike_count=2,  # Max strikes reached
        )
        assert service.check_gfv_emergency_override(12.0) is False

    def test_gfv_not_triggered_for_small_loss(self):
        """GFV override should not trigger for small losses."""
        assert self.service.check_gfv_emergency_override(5.0) is False
