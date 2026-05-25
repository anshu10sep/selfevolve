"""
Momentum Strategy Agent

Captures trending moves by buying assets showing strong upward momentum
with volume confirmation. Holds for a configurable number of days with
a trailing ATR-based stop loss.

Edge: Works well in strong bull markets and sector rotations.
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

logger = structlog.get_logger(component="strategy.momentum")


MOMENTUM_IDENTITY_CORE = """You are the Momentum Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a momentum specialist. You identify and capture trending moves by buying
assets that are already demonstrating strong upward price momentum with volume
confirmation. Your philosophy: "The trend is your friend."

## How You Work:
1. Calculate N-day returns for each candidate ticker
2. Confirm momentum with above-average volume
3. Set entries at current price, stops via ATR, targets at 3x ATR
4. Hold for a configured number of days with trailing stop

## STRICT RULES:
- You ONLY generate signals when momentum + volume align
- You NEVER chase thin-volume breakouts
- You exit at trailing stop or hold-period expiry, whichever comes first
- Your signal generation is DETERMINISTIC — you never use LLM for signals
- LLM is used ONLY for post-mortem reflection on your performance
"""


class MomentumStrategyAgent(StrategyAgent):
    """
    Momentum strategy: Buy when N-day return exceeds threshold
    with volume confirmation. Hold with trailing ATR stop.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Momentum Strategy",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=MOMENTUM_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "momentum"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "lookback_period": 5,
            "entry_threshold": 0.02,
            "hold_days": 5,
            "trailing_stop_atr_mult": 2.0,
            "take_profit_atr_mult": 3.0,
            "volume_confirmation_mult": 1.5,
            "atr_period": 14,
            "min_volume": 1_000_000,
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.STRONG,
            "SIDEWAYS": MarketRegimeAffinity.NEUTRAL,
            "BEAR": MarketRegimeAffinity.WEAK,
            "HIGH_VOL": MarketRegimeAffinity.NEUTRAL,
            "PANIC": MarketRegimeAffinity.DISABLED,
        }

    async def generate_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """
        Scan for momentum signals.

        For each ticker:
        1. Calculate lookback-period return
        2. Check volume vs average
        3. Calculate ATR for stop/target
        4. Generate BUY signal if criteria met
        """
        signals = []
        lookback = self.get_param("lookback_period", 5)
        threshold = self.get_param("entry_threshold", 0.02)
        vol_mult = self.get_param("volume_confirmation_mult", 1.5)
        atr_period = self.get_param("atr_period", 14)
        stop_mult = self.get_param("trailing_stop_atr_mult", 2.0)
        tp_mult = self.get_param("take_profit_atr_mult", 3.0)
        min_vol = self.get_param("min_volume", 1_000_000)

        for ticker in tickers:
            try:
                ticker_data = market_data.get(ticker, {})
                bars = ticker_data.get("bars", [])

                if len(bars) < max(lookback + 1, atr_period + 2):
                    continue

                # Skip if already in position
                if self.has_active_position(ticker):
                    continue

                closes = [b["close"] for b in bars]
                highs = [b["high"] for b in bars]
                lows = [b["low"] for b in bars]
                volumes = [b["volume"] for b in bars]

                # 1. N-day return
                current_price = closes[-1]
                lookback_price = closes[-(lookback + 1)]
                if lookback_price <= 0:
                    continue
                n_day_return = (current_price - lookback_price) / lookback_price

                if n_day_return < threshold:
                    continue

                # 2. Volume confirmation
                avg_volume = sum(volumes[:-1]) / max(1, len(volumes) - 1)
                if avg_volume <= 0 or volumes[-1] < avg_volume * vol_mult:
                    continue
                if volumes[-1] < min_vol:
                    continue

                # 3. ATR for stop/target
                atr_values = self.calculate_atr(highs, lows, closes, atr_period)
                if not atr_values:
                    continue
                current_atr = atr_values[-1]
                if current_atr <= 0:
                    continue

                stop_loss = round(current_price - (current_atr * stop_mult), 2)
                take_profit = round(current_price + (current_atr * tp_mult), 2)

                # 4. Signal strength based on momentum magnitude
                # Normalize: 5% return = strength 1.0
                strength = min(1.0, abs(n_day_return) / 0.05)
                # Confidence based on volume surge
                vol_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0
                confidence = min(1.0, vol_ratio / 3.0)

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
                        f"{lookback}d return={n_day_return:.1%}, "
                        f"vol={volumes[-1]/1e6:.1f}M ({vol_ratio:.1f}x avg), "
                        f"ATR={current_atr:.2f}"
                    ),
                    market_data_snapshot={
                        "close": current_price,
                        "n_day_return": round(n_day_return, 4),
                        "volume": volumes[-1],
                        "avg_volume": round(avg_volume),
                        "atr": round(current_atr, 4),
                    },
                )
                signals.append(signal)

            except Exception as e:
                logger.warning(
                    "momentum_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "momentum_scan_complete",
            tickers_scanned=len(tickers),
            signals_generated=len(signals),
        )
        return signals
