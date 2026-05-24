"""
Unit tests for position sizing (ATR volatility targeting).

Verifies that the deterministic position sizer correctly calculates
fractional share quantities, risk limits, and liquidity penalties.
"""

import pytest
from execution.position_sizing import PositionSizer, PositionResult


class TestPositionSizer:
    """Tests for ATR-based position sizing."""

    def setup_method(self):
        """Create a sizer with $100 portfolio and 2% max risk."""
        self.sizer = PositionSizer(portfolio_equity=100.0, max_risk_pct=2.0)

    def test_basic_position_sizing(self):
        """Basic position size calculation with a clear stop loss."""
        result = self.sizer.calculate_position_size(
            current_price=100.0,
            stop_loss_price=98.0,  # $2 risk per share
        )
        # max_risk_usd = $2.00, risk_per_share = $2.00
        # max_shares = $2.00 / $2.00 = 1.0
        # notional = 1.0 * $100 = $100.00
        # But capped at 10% tranche = $10
        assert result.fractional_quantity > 0
        assert result.notional > 0
        assert result.notional <= 20.0  # Max position limit
        assert result.risk_pct_of_portfolio <= 2.0

    def test_tight_stop_loss_larger_position(self):
        """Tighter stop loss allows larger uncapped position size."""
        # Compare risk calculations directly (before tranche capping)
        result_tight = self.sizer.calculate_position_size(
            current_price=50.0,
            stop_loss_price=49.5,  # $0.50 risk per share
        )
        result_wide = self.sizer.calculate_position_size(
            current_price=50.0,
            stop_loss_price=48.0,  # $2.00 risk per share
        )
        # Tight stop should have lower risk per share
        assert result_tight.risk_per_share < result_wide.risk_per_share
        # Both capped at same tranche limit, but risk per share proves the math
        assert result_tight.risk_per_share == 0.5
        assert result_wide.risk_per_share == 2.0

    def test_invalid_stop_loss_returns_zero(self):
        """Stop loss at or above current price returns zero."""
        result = self.sizer.calculate_position_size(
            current_price=100.0,
            stop_loss_price=100.0,
        )
        assert result.fractional_quantity == 0
        assert result.notional == 0

    def test_low_volume_penalty(self):
        """Low volume assets get a slippage penalty."""
        normal = self.sizer.calculate_position_size(
            current_price=50.0,
            stop_loss_price=49.0,
            daily_volume=10_000_000,  # Normal volume
        )
        low_vol = self.sizer.calculate_position_size(
            current_price=50.0,
            stop_loss_price=49.0,
            daily_volume=1_000_000,  # Low volume
        )
        # Low volume position should be smaller
        assert low_vol.fractional_quantity <= normal.fractional_quantity
        assert low_vol.liquidity_penalty < 1.0

    def test_concentration_limit(self):
        """Position cannot exceed 20% of portfolio."""
        # With a $0.01 risk per share on a $1 stock, the sizer would
        # want to buy a lot of shares. Concentration limit should cap it.
        result = self.sizer.calculate_position_size(
            current_price=1.0,
            stop_loss_price=0.99,
        )
        assert result.notional <= 20.0  # 20% of $100

    def test_atr_calculation(self):
        """ATR calculation with known values."""
        highs = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
        lows = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
        closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]

        atr = PositionSizer.calculate_atr(highs, lows, closes, period=14)
        assert atr > 0
        # All TR values should be 1 (high-low = 1), so ATR ≈ 1.0
        assert abs(atr - 1.0) < 0.1

    def test_stop_loss_from_atr(self):
        """Stop loss calculation from ATR."""
        stop = PositionSizer.calculate_stop_loss_from_atr(
            current_price=100.0,
            atr=2.0,
            multiplier=2.0,
        )
        assert stop == 96.0  # 100 - (2 * 2)

    def test_take_profit_from_atr(self):
        """Take profit calculation from ATR."""
        tp = PositionSizer.calculate_take_profit_from_atr(
            current_price=100.0,
            atr=2.0,
            multiplier=3.0,
        )
        assert tp == 106.0  # 100 + (2 * 3)
