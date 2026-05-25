"""
VWAP Reversion Strategy Agent

Intraday VWAP (Volume Weighted Average Price) reversion. Buys when price
dips below VWAP by a configurable threshold with volume support, sells
when price returns to or crosses VWAP.

Edge: High win rate on liquid stocks. Consistent small profits.
Best for generating daily income on high-volume names.
Signal generation is fully deterministic — no LLM in the hot path.
"""

from __future__ import annotations

from typing import Any

import structlog

from agents.strategies.strategy_base import (
    StrategyAgent,
    StrategySignal,
    SignalType,
    StrategyMode,
    MarketRegimeAffinity,
)
from core.models.agents import AgentIdentity, AgentRole, AgentType

logger = structlog.get_logger(component="strategy.vwap")


VWAP_IDENTITY_CORE = """You are the VWAP Reversion Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a VWAP specialist. You trade intraday reversions to the Volume Weighted
Average Price. When price dips significantly below VWAP with volume, you buy,
expecting a reversion to the mean. Your philosophy: "VWAP is the institutional
fair value — deviations are opportunities."

## How You Work:
1. Calculate VWAP from intraday volume and price data
2. Buy when price < VWAP * (1 - deviation_threshold) with volume support
3. Sell when price returns to VWAP (or exceeds it)
4. Use tight percentage-based stops

## STRICT RULES:
- You ONLY trade highly liquid stocks (>5M daily volume)
- You use small position sizes (high frequency, small profits)
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class VWAPStrategyAgent(StrategyAgent):
    """
    VWAP reversion strategy: Buy below VWAP, sell at VWAP.
    Targets consistent small profits on liquid stocks.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="VWAP Strategy",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=VWAP_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "vwap"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "vwap_deviation_pct": 0.005,
            "min_daily_volume": 5_000_000,
            "max_hold_bars": 24,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.005,
            "volume_confirmation_mult": 1.2,
            "min_bars_for_vwap": 10,
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.NEUTRAL,
            "SIDEWAYS": MarketRegimeAffinity.STRONG,
            "BEAR": MarketRegimeAffinity.WEAK,
            "HIGH_VOL": MarketRegimeAffinity.WEAK,
            "PANIC": MarketRegimeAffinity.DISABLED,
        }

    async def generate_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """
        Scan for VWAP reversion signals.

        For each ticker:
        1. Calculate VWAP from available bar data
        2. BUY if price < VWAP * (1 - deviation) with volume support
        3. SELL if active position and price >= VWAP
        """
        signals = []
        deviation_pct = self.get_param("vwap_deviation_pct", 0.005)
        min_vol = self.get_param("min_daily_volume", 5_000_000)
        stop_pct = self.get_param("stop_loss_pct", 0.01)
        tp_pct = self.get_param("take_profit_pct", 0.005)
        vol_mult = self.get_param("volume_confirmation_mult", 1.2)
        min_bars = self.get_param("min_bars_for_vwap", 10)

        for ticker in tickers:
            try:
                ticker_data = market_data.get(ticker, {})
                bars = ticker_data.get("bars", [])

                if len(bars) < min_bars:
                    continue

                highs = [b["high"] for b in bars]
                lows = [b["low"] for b in bars]
                closes = [b["close"] for b in bars]
                volumes = [b["volume"] for b in bars]

                current_price = closes[-1]
                current_volume = volumes[-1]
                if current_price <= 0:
                    continue

                # Volume filter
                total_volume = sum(volumes)
                if total_volume < min_vol:
                    continue

                # Calculate VWAP
                vwap_values = self.calculate_vwap(highs, lows, closes, volumes)
                if not vwap_values:
                    continue
                current_vwap = vwap_values[-1]
                if current_vwap <= 0:
                    continue

                # Average volume for the session
                avg_volume = sum(volumes) / len(volumes)

                # Deviation from VWAP
                deviation = (current_price - current_vwap) / current_vwap

                # ── BUY: Price below VWAP by threshold ──
                if (
                    not self.has_active_position(ticker)
                    and deviation < -deviation_pct
                    and current_volume >= avg_volume * vol_mult
                ):
                    stop_loss = round(current_price * (1 - stop_pct), 2)
                    take_profit = round(current_vwap, 2)  # Target = VWAP itself

                    # Strength: how far below VWAP
                    strength = min(1.0, abs(deviation) / (deviation_pct * 3))
                    # Confidence: volume support
                    vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                    confidence = min(1.0, max(0.3, vol_ratio / 2))

                    signal = StrategySignal(
                        strategy_name=self.strategy_name,
                        strategy_version=self.parameters.version,
                        ticker=ticker,
                        signal_type=SignalType.BUY,
                        strength=round(strength, 3),
                        confidence=round(confidence, 3),
                        entry_price=current_price,
                        stop_loss_price=stop_loss,
                        take_profit_price=take_profit,
                        rationale=(
                            f"Price={current_price:.2f} is {deviation:.2%} below VWAP={current_vwap:.2f}, "
                            f"vol={current_volume/1e6:.1f}M ({vol_ratio:.1f}x avg)"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "vwap": round(current_vwap, 4),
                            "deviation_pct": round(deviation, 4),
                            "volume": current_volume,
                            "avg_volume": round(avg_volume),
                        },
                    )
                    signals.append(signal)

                # ── SELL: Price returned to/above VWAP ──
                elif (
                    self.has_active_position(ticker)
                    and deviation >= 0
                ):
                    signal = StrategySignal(
                        strategy_name=self.strategy_name,
                        strategy_version=self.parameters.version,
                        ticker=ticker,
                        signal_type=SignalType.SELL,
                        strength=0.7,
                        confidence=0.8,
                        entry_price=current_price,
                        rationale=(
                            f"VWAP reversion complete: price={current_price:.2f} "
                            f">= VWAP={current_vwap:.2f}"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "vwap": round(current_vwap, 4),
                        },
                    )
                    signals.append(signal)

            except Exception as e:
                logger.warning(
                    "vwap_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "vwap_scan_complete",
            tickers_scanned=len(tickers),
            signals_generated=len(signals),
        )
        return signals
