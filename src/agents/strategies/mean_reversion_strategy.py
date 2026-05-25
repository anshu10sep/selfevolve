"""
Mean Reversion Strategy Agent

Profits from price returning to the mean. Buys when RSI is oversold
AND price is below the lower Bollinger Band. Sells when RSI recovers
to overbought or price hits the upper band.

Edge: Works well in range-bound and sideways markets.
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

logger = structlog.get_logger(component="strategy.mean_reversion")


MEAN_REVERSION_IDENTITY_CORE = """You are the Mean Reversion Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a mean reversion specialist. You profit from the statistical tendency
of prices to revert to their average. When an asset is oversold (RSI low,
price below Bollinger Band), you buy. When it reverts to overbought territory,
you sell. Your philosophy: "What goes down must come up."

## How You Work:
1. Calculate RSI and Bollinger Bands for each candidate
2. Buy when RSI < oversold threshold AND price < lower Bollinger Band
3. Sell when RSI > overbought threshold OR price > upper Bollinger Band
4. Use ATR-based stops for risk management

## STRICT RULES:
- You NEVER buy in a strong downtrend (this is mean reversion, not bottom-picking)
- You require BOTH RSI + Bollinger Band confirmation for entries
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class MeanReversionStrategyAgent(StrategyAgent):
    """
    Mean reversion strategy: Buy oversold, sell overbought.
    Uses RSI + Bollinger Bands for dual confirmation.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Mean Reversion Strategy",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=MEAN_REVERSION_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "mean_reversion"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "rsi_period": 14,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "bb_period": 20,
            "bb_std_dev": 2.0,
            "atr_period": 14,
            "stop_loss_atr_mult": 2.0,
            "max_hold_days": 10,
            "min_volume": 1_000_000,
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.NEUTRAL,
            "SIDEWAYS": MarketRegimeAffinity.STRONG,
            "BEAR": MarketRegimeAffinity.WEAK,
            "HIGH_VOL": MarketRegimeAffinity.STRONG,
            "PANIC": MarketRegimeAffinity.DISABLED,
        }

    async def generate_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """
        Scan for mean reversion signals.

        For each ticker:
        1. Calculate RSI
        2. Calculate Bollinger Bands
        3. BUY when RSI < oversold AND price < lower band
        4. SELL when RSI > overbought OR price > upper band (for active positions)
        """
        signals = []
        rsi_period = self.get_param("rsi_period", 14)
        rsi_oversold = self.get_param("rsi_oversold", 30.0)
        rsi_overbought = self.get_param("rsi_overbought", 70.0)
        bb_period = self.get_param("bb_period", 20)
        bb_std = self.get_param("bb_std_dev", 2.0)
        atr_period = self.get_param("atr_period", 14)
        stop_mult = self.get_param("stop_loss_atr_mult", 2.0)
        min_vol = self.get_param("min_volume", 1_000_000)

        min_bars = max(rsi_period + 2, bb_period + 1, atr_period + 2)

        for ticker in tickers:
            try:
                ticker_data = market_data.get(ticker, {})
                bars = ticker_data.get("bars", [])

                if len(bars) < min_bars:
                    continue

                closes = [b["close"] for b in bars]
                highs = [b["high"] for b in bars]
                lows = [b["low"] for b in bars]
                volumes = [b["volume"] for b in bars]

                current_price = closes[-1]
                if current_price <= 0:
                    continue

                # Volume filter
                avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
                if avg_volume < min_vol:
                    continue

                # 1. RSI
                rsi_values = self.calculate_rsi(closes, rsi_period)
                if not rsi_values:
                    continue
                current_rsi = rsi_values[-1]

                # 2. Bollinger Bands
                upper, middle, lower = self.calculate_bollinger_bands(
                    closes, bb_period, bb_std
                )
                if not upper:
                    continue
                current_upper = upper[-1]
                current_middle = middle[-1]
                current_lower = lower[-1]

                # 3. ATR for stops
                atr_values = self.calculate_atr(highs, lows, closes, atr_period)
                current_atr = atr_values[-1] if atr_values else current_price * 0.02

                # ── BUY Signal: Oversold ──
                if (
                    not self.has_active_position(ticker)
                    and current_rsi < rsi_oversold
                    and current_price < current_lower
                ):
                    stop_loss = round(current_price - (current_atr * stop_mult), 2)
                    # Target: mean (middle Bollinger Band)
                    take_profit = round(current_middle, 2)

                    # Strength: how far below oversold + how far below lower band
                    rsi_depth = (rsi_oversold - current_rsi) / rsi_oversold
                    bb_depth = (current_lower - current_price) / current_lower if current_lower > 0 else 0
                    strength = min(1.0, (rsi_depth + bb_depth) / 2)
                    confidence = min(1.0, max(0.3, strength * 1.2))

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
                            f"RSI={current_rsi:.1f} (<{rsi_oversold}), "
                            f"price={current_price:.2f} below BB lower={current_lower:.2f}, "
                            f"target=SMA={current_middle:.2f}"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "rsi": round(current_rsi, 2),
                            "bb_upper": round(current_upper, 2),
                            "bb_middle": round(current_middle, 2),
                            "bb_lower": round(current_lower, 2),
                            "atr": round(current_atr, 4),
                        },
                    )
                    signals.append(signal)

                # ── SELL Signal: Overbought (for active positions) ──
                elif (
                    self.has_active_position(ticker)
                    and (current_rsi > rsi_overbought or current_price > current_upper)
                ):
                    signal = StrategySignal(
                        strategy_name=self.strategy_name,
                        strategy_version=self.parameters.version,
                        ticker=ticker,
                        signal_type=SignalType.SELL,
                        strength=min(1.0, (current_rsi - rsi_overbought) / 30) if current_rsi > rsi_overbought else 0.5,
                        confidence=0.8,
                        entry_price=current_price,
                        rationale=(
                            f"Mean reversion target reached: RSI={current_rsi:.1f}, "
                            f"price={current_price:.2f} vs BB upper={current_upper:.2f}"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "rsi": round(current_rsi, 2),
                            "bb_upper": round(current_upper, 2),
                        },
                    )
                    signals.append(signal)

            except Exception as e:
                logger.warning(
                    "mean_reversion_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "mean_reversion_scan_complete",
            tickers_scanned=len(tickers),
            signals_generated=len(signals),
        )
        return signals
