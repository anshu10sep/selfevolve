"""
Breakout Strategy Agent

Detects consolidation periods (Bollinger Band squeeze + low ATR)
and buys on breakout above resistance with volume surge confirmation.
Uses tight stop below the consolidation range.

Edge: Captures explosive moves after quiet periods. Low win rate
but high reward-to-risk ratio.
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

logger = structlog.get_logger(component="strategy.breakout")


BREAKOUT_IDENTITY_CORE = """You are the Breakout Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a breakout specialist. You identify periods of price consolidation
(tight Bollinger Bands, low ATR) and enter when price explodes out of the
range with heavy volume. Your philosophy: "Volatility compression precedes expansion."

## How You Work:
1. Detect Bollinger Band squeeze (narrow band width)
2. Wait for price breakout above upper band with volume surge
3. Enter on breakout, stop below consolidation low, target 3x ATR
4. Accept lower win rate in exchange for high reward-to-risk

## STRICT RULES:
- You NEVER enter without volume confirmation (>2x average)
- You require minimum consolidation period before breakout
- You use tight stops (below consolidation range)
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class BreakoutStrategyAgent(StrategyAgent):
    """
    Breakout strategy: Detect consolidation squeeze,
    buy on volume-confirmed breakout.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Breakout Strategy",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=BREAKOUT_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "breakout"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "squeeze_bb_width_pct": 0.04,
            "breakout_volume_mult": 2.0,
            "consolidation_min_days": 5,
            "atr_period": 14,
            "bb_period": 20,
            "bb_std_dev": 2.0,
            "stop_loss_atr_mult": 1.5,
            "take_profit_atr_mult": 3.0,
            "min_volume": 1_000_000,
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.NEUTRAL,
            "SIDEWAYS": MarketRegimeAffinity.WEAK,
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
        Scan for breakout signals.

        For each ticker:
        1. Calculate Bollinger Band width — detect squeeze
        2. Check if price breaks above upper band
        3. Confirm with volume surge (>2x average)
        4. Generate BUY with stop below consolidation low
        """
        signals = []
        squeeze_width = self.get_param("squeeze_bb_width_pct", 0.04)
        vol_mult = self.get_param("breakout_volume_mult", 2.0)
        consol_days = self.get_param("consolidation_min_days", 5)
        atr_period = self.get_param("atr_period", 14)
        bb_period = self.get_param("bb_period", 20)
        bb_std = self.get_param("bb_std_dev", 2.0)
        stop_mult = self.get_param("stop_loss_atr_mult", 1.5)
        tp_mult = self.get_param("take_profit_atr_mult", 3.0)
        min_vol = self.get_param("min_volume", 1_000_000)

        min_bars = max(bb_period + consol_days, atr_period + 2)

        for ticker in tickers:
            try:
                ticker_data = market_data.get(ticker, {})
                bars = ticker_data.get("bars", [])

                if len(bars) < min_bars:
                    continue

                if self.has_active_position(ticker):
                    continue

                closes = [b["close"] for b in bars]
                highs = [b["high"] for b in bars]
                lows = [b["low"] for b in bars]
                volumes = [b["volume"] for b in bars]

                current_price = closes[-1]
                if current_price <= 0:
                    continue

                # Volume filter
                if volumes[-1] < min_vol:
                    continue

                # 1. Bollinger Bands
                upper, middle, lower = self.calculate_bollinger_bands(
                    closes, bb_period, bb_std
                )
                if len(upper) < consol_days + 1:
                    continue

                # 2. Check for squeeze over consolidation period
                # Band width = (upper - lower) / middle
                squeeze_detected = True
                for i in range(-(consol_days + 1), -1):
                    idx = len(upper) + i
                    if idx < 0 or idx >= len(upper):
                        squeeze_detected = False
                        break
                    width = (upper[idx] - lower[idx]) / middle[idx] if middle[idx] > 0 else 999
                    if width > squeeze_width:
                        squeeze_detected = False
                        break

                if not squeeze_detected:
                    continue

                # 3. Breakout: current price above upper band
                current_upper = upper[-1]
                if current_price <= current_upper:
                    continue

                # 4. Volume confirmation
                avg_volume = sum(volumes[-(consol_days + 1):-1]) / consol_days
                if avg_volume <= 0 or volumes[-1] < avg_volume * vol_mult:
                    continue

                # 5. ATR for stops/targets
                atr_values = self.calculate_atr(highs, lows, closes, atr_period)
                current_atr = atr_values[-1] if atr_values else current_price * 0.02

                # Stop below consolidation low
                consolidation_low = min(lows[-(consol_days + 1):])
                atr_stop = current_price - (current_atr * stop_mult)
                stop_loss = round(max(consolidation_low * 0.99, atr_stop), 2)
                take_profit = round(current_price + (current_atr * tp_mult), 2)

                # Signal strength based on breakout magnitude
                breakout_pct = (current_price - current_upper) / current_upper if current_upper > 0 else 0
                vol_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0
                strength = min(1.0, breakout_pct * 10 + (vol_ratio - vol_mult) / 5)
                confidence = min(1.0, max(0.4, vol_ratio / 4))

                # Band width for the squeeze magnitude
                prev_width = (upper[-2] - lower[-2]) / middle[-2] if len(upper) > 1 and middle[-2] > 0 else 0

                signal = StrategySignal(
                    strategy_name=self.strategy_name,
                    strategy_version=self.parameters.version,
                    ticker=ticker,
                    signal_type=SignalType.BUY,
                    strength=round(max(0.1, strength), 3),
                    confidence=round(confidence, 3),
                    entry_price=current_price,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
                    rationale=(
                        f"BB squeeze ({consol_days}d width={prev_width:.3f}<{squeeze_width}), "
                        f"breakout +{breakout_pct:.1%} above upper band, "
                        f"vol={volumes[-1]/1e6:.1f}M ({vol_ratio:.1f}x avg)"
                    ),
                    market_data_snapshot={
                        "close": current_price,
                        "bb_upper": round(current_upper, 2),
                        "bb_width": round(prev_width, 4),
                        "volume": volumes[-1],
                        "vol_ratio": round(vol_ratio, 2),
                        "atr": round(current_atr, 4),
                        "consolidation_low": consolidation_low,
                    },
                )
                signals.append(signal)

            except Exception as e:
                logger.warning(
                    "breakout_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "breakout_scan_complete",
            tickers_scanned=len(tickers),
            signals_generated=len(signals),
        )
        return signals
