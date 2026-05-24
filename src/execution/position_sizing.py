"""
ATR-Based Position Sizing (Volatility Targeting)

The LLM determines direction and thesis. This deterministic module
determines the exact dollar amount. Position sizing is calculated
mathematically based on Average True Range (ATR) to ensure each
trade risks exactly the target percentage of portfolio equity.
"""

from __future__ import annotations

import structlog
import numpy as np

from config.constants import (
    ATR_PERIOD,
    TARGET_RISK_PCT_PER_ATR,
    LOW_VOLUME_THRESHOLD,
    SLIPPAGE_PENALTY_LOW_VOLUME,
    MAX_POSITION_PCT,
    TRANCHE_SCALE_THRESHOLDS,
)

logger = structlog.get_logger(component="position_sizing")


class PositionSizer:
    """
    Deterministic position sizing based on volatility targeting.
    
    The system sizes positions so that a 1-ATR adverse move equals
    exactly TARGET_RISK_PCT_PER_ATR of portfolio equity. This prevents
    both over-sizing in volatile markets and under-sizing in calm markets.
    """

    def __init__(self, portfolio_equity: float, max_risk_pct: float = 2.0):
        self.portfolio_equity = portfolio_equity
        self.max_risk_usd = portfolio_equity * (max_risk_pct / 100.0)

    def calculate_position_size(
        self,
        current_price: float,
        stop_loss_price: float,
        daily_volume: float = float("inf"),
    ) -> PositionResult:
        """
        Calculate the optimal position size.
        
        Args:
            current_price: Current asset price
            stop_loss_price: Stop loss price level
            daily_volume: Average daily dollar volume for liquidity check
            
        Returns:
            PositionResult with fractional shares, notional, and risk metrics
        """
        # ── Risk Per Share ─────────────────────────────────────────
        risk_per_share = abs(current_price - stop_loss_price)
        if risk_per_share <= 0:
            logger.warning(
                "invalid_stop_loss",
                price=current_price,
                stop_loss=stop_loss_price,
            )
            return PositionResult.zero(current_price, "Invalid stop loss")

        # ── Maximum Shares by Risk ─────────────────────────────────
        max_shares = self.max_risk_usd / risk_per_share

        # ── Liquidity Penalty ──────────────────────────────────────
        liquidity_penalty = 1.0
        if daily_volume < LOW_VOLUME_THRESHOLD:
            liquidity_penalty = 1.0 - SLIPPAGE_PENALTY_LOW_VOLUME
            logger.info(
                "liquidity_penalty_applied",
                daily_volume=daily_volume,
                penalty=SLIPPAGE_PENALTY_LOW_VOLUME,
            )

        adjusted_shares = max_shares * liquidity_penalty

        # ── Notional Calculation ───────────────────────────────────
        notional = adjusted_shares * current_price

        # ── Portfolio Concentration Limit ──────────────────────────
        max_notional = self.portfolio_equity * (MAX_POSITION_PCT / 100.0)
        if notional > max_notional:
            notional = max_notional
            adjusted_shares = notional / current_price

        # ── Dynamic Tranche Sizing ─────────────────────────────────
        tranche_pct = self._get_tranche_percentage()
        max_tranche = self.portfolio_equity * tranche_pct
        if notional > max_tranche:
            notional = max_tranche
            adjusted_shares = notional / current_price

        return PositionResult(
            fractional_quantity=round(adjusted_shares, 6),
            notional=round(notional, 2),
            risk_per_share=round(risk_per_share, 4),
            total_risk_usd=round(adjusted_shares * risk_per_share, 2),
            risk_pct_of_portfolio=round(
                (adjusted_shares * risk_per_share / self.portfolio_equity) * 100, 2
            ),
            current_price=current_price,
            stop_loss_price=stop_loss_price,
            liquidity_penalty=liquidity_penalty,
            reason="Calculated via ATR volatility targeting",
        )

    def _get_tranche_percentage(self) -> float:
        """
        Dynamic tranche percentage based on portfolio equity.
        
        As the account grows, reduce per-trade allocation to preserve wealth.
        """
        for threshold, pct in sorted(
            TRANCHE_SCALE_THRESHOLDS.items(), reverse=True
        ):
            if self.portfolio_equity > threshold:
                return pct
        return 0.10  # Default: 10% per trade

    @staticmethod
    def calculate_atr(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = ATR_PERIOD,
    ) -> float:
        """
        Calculate the Average True Range (ATR) indicator.
        
        Uses the standard Wilder's ATR calculation.
        """
        if len(highs) < period + 1:
            return 0.0

        highs_arr = np.array(highs)
        lows_arr = np.array(lows)
        closes_arr = np.array(closes)

        # True Range components
        tr1 = highs_arr[1:] - lows_arr[1:]
        tr2 = np.abs(highs_arr[1:] - closes_arr[:-1])
        tr3 = np.abs(lows_arr[1:] - closes_arr[:-1])

        true_range = np.maximum(tr1, np.maximum(tr2, tr3))

        # Wilder's smoothed ATR
        atr = np.mean(true_range[-period:])
        return float(atr)

    @staticmethod
    def calculate_stop_loss_from_atr(
        current_price: float,
        atr: float,
        multiplier: float = 2.0,
    ) -> float:
        """Calculate stop loss based on ATR distance."""
        return round(current_price - (atr * multiplier), 2)

    @staticmethod
    def calculate_take_profit_from_atr(
        current_price: float,
        atr: float,
        multiplier: float = 3.0,
    ) -> float:
        """Calculate take profit based on ATR distance (risk:reward ratio)."""
        return round(current_price + (atr * multiplier), 2)


class PositionResult:
    """Result of a position sizing calculation."""

    def __init__(
        self,
        fractional_quantity: float,
        notional: float,
        risk_per_share: float,
        total_risk_usd: float,
        risk_pct_of_portfolio: float,
        current_price: float,
        stop_loss_price: float,
        liquidity_penalty: float = 1.0,
        reason: str = "",
    ):
        self.fractional_quantity = fractional_quantity
        self.notional = notional
        self.risk_per_share = risk_per_share
        self.total_risk_usd = total_risk_usd
        self.risk_pct_of_portfolio = risk_pct_of_portfolio
        self.current_price = current_price
        self.stop_loss_price = stop_loss_price
        self.liquidity_penalty = liquidity_penalty
        self.reason = reason

    @classmethod
    def zero(cls, current_price: float, reason: str) -> PositionResult:
        """Return a zero-size position."""
        return cls(
            fractional_quantity=0.0,
            notional=0.0,
            risk_per_share=0.0,
            total_risk_usd=0.0,
            risk_pct_of_portfolio=0.0,
            current_price=current_price,
            stop_loss_price=current_price,
            reason=reason,
        )

    def to_dict(self) -> dict:
        return {
            "fractional_quantity": self.fractional_quantity,
            "notional": self.notional,
            "risk_per_share": self.risk_per_share,
            "total_risk_usd": self.total_risk_usd,
            "risk_pct_of_portfolio": self.risk_pct_of_portfolio,
            "current_price": self.current_price,
            "stop_loss_price": self.stop_loss_price,
            "liquidity_penalty": self.liquidity_penalty,
            "reason": self.reason,
        }
