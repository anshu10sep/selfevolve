"""
Gap Fill Strategy Agent

Trades overnight gaps. When a stock gaps down at open, buys if the
historical gap fill rate is high. Sells when the gap fills (price
returns to previous close) or at stop-loss.

Edge: Gap fills are one of the most reliable intraday patterns.
High win rate. Good for daily income generation.
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

logger = structlog.get_logger(component="strategy.gap_fill")


GAP_FILL_IDENTITY_CORE = """You are the Gap Fill Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a gap fill specialist. You trade overnight price gaps — when a stock
opens significantly lower than the previous close, you buy, expecting the gap
to fill as price returns to the prior close level. Your philosophy: "Gaps want
to be filled."

## How You Work:
1. At market open, compare today's open to yesterday's close
2. If gap_down > threshold, check historical fill rate for the ticker
3. If fill rate > minimum, buy with target at previous close (gap fill)
4. Use tight stop below the gap open

## STRICT RULES:
- You ONLY trade gap-downs (buying), not gap-ups (would require shorting)
- You require statistical evidence (historical fill rate > 60%)
- You have a time limit — exit if gap hasn't filled within N bars
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class GapFillStrategyAgent(StrategyAgent):
    """
    Gap fill strategy: Buy on overnight gap-down when
    historical fill rate is high. Target = previous close.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Gap Fill Strategy",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=GAP_FILL_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "gap_fill"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "min_gap_pct": 0.02,
            "historical_fill_rate_min": 0.60,
            "gap_lookback_days": 30,
            "max_fill_wait_bars": 8,
            "stop_loss_pct": 0.015,
            "min_volume": 2_000_000,
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.NEUTRAL,
            "SIDEWAYS": MarketRegimeAffinity.STRONG,
            "BEAR": MarketRegimeAffinity.WEAK,
            "HIGH_VOL": MarketRegimeAffinity.STRONG,
            "PANIC": MarketRegimeAffinity.DISABLED,
        }

    def _calculate_historical_fill_rate(
        self,
        bars: list[dict],
        min_gap_pct: float,
    ) -> tuple[float, int, int]:
        """
        Calculate the historical gap fill rate for a ticker.

        A gap fill occurs when the day's high reaches or exceeds
        the previous day's close after a gap-down open.

        Returns:
            (fill_rate, gaps_found, gaps_filled)
        """
        gaps_found = 0
        gaps_filled = 0

        for i in range(1, len(bars)):
            prev_close = bars[i - 1]["close"]
            today_open = bars[i]["open"]
            today_high = bars[i]["high"]

            if prev_close <= 0:
                continue

            gap_pct = (today_open - prev_close) / prev_close

            # Only count gap-downs
            if gap_pct < -min_gap_pct:
                gaps_found += 1
                # Gap filled if today's high reached previous close
                if today_high >= prev_close:
                    gaps_filled += 1

        fill_rate = gaps_filled / gaps_found if gaps_found > 0 else 0.0
        return fill_rate, gaps_found, gaps_filled

    async def generate_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """
        Scan for gap fill opportunities.

        For each ticker:
        1. Check if today's open gapped down from yesterday's close
        2. Calculate historical fill rate
        3. If gap_down > threshold AND fill_rate > min → BUY
        4. Target = previous close (gap fill level)
        """
        signals = []
        min_gap = self.get_param("min_gap_pct", 0.02)
        min_fill_rate = self.get_param("historical_fill_rate_min", 0.60)
        lookback = self.get_param("gap_lookback_days", 30)
        stop_pct = self.get_param("stop_loss_pct", 0.015)
        min_vol = self.get_param("min_volume", 2_000_000)

        for ticker in tickers:
            try:
                ticker_data = market_data.get(ticker, {})
                bars = ticker_data.get("bars", [])

                if len(bars) < max(lookback, 5):
                    continue

                if self.has_active_position(ticker):
                    continue

                # Current bar (today) and previous bar (yesterday)
                today = bars[-1]
                yesterday = bars[-2]

                today_open = today["open"]
                yesterday_close = yesterday["close"]
                current_price = today["close"]
                current_volume = today["volume"]

                if yesterday_close <= 0 or today_open <= 0:
                    continue

                # Volume filter
                if current_volume < min_vol:
                    continue

                # 1. Gap calculation
                gap_pct = (today_open - yesterday_close) / yesterday_close

                # Only trade gap-downs
                if gap_pct >= -min_gap:
                    continue

                # 2. Historical fill rate
                lookback_bars = bars[-lookback:]
                fill_rate, gaps_found, gaps_filled = self._calculate_historical_fill_rate(
                    lookback_bars, min_gap
                )

                if fill_rate < min_fill_rate:
                    continue
                if gaps_found < 3:
                    # Need minimum sample size
                    continue

                # 3. Generate BUY signal
                stop_loss = round(current_price * (1 - stop_pct), 2)
                take_profit = round(yesterday_close, 2)  # Gap fill target

                # Strength: magnitude of gap + fill rate
                gap_magnitude = min(1.0, abs(gap_pct) / 0.05)  # 5% gap = max
                strength = min(1.0, (gap_magnitude + fill_rate) / 2)
                confidence = min(1.0, fill_rate)

                # Check if gap is already partially filled
                partial_fill = (current_price - today_open) / (yesterday_close - today_open) if (yesterday_close - today_open) != 0 else 0
                if partial_fill > 0.8:
                    # Gap mostly filled already
                    continue

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
                        f"Gap down {gap_pct:.1%} (open={today_open:.2f} vs prev close={yesterday_close:.2f}), "
                        f"hist fill rate={fill_rate:.0%} ({gaps_filled}/{gaps_found}), "
                        f"target={yesterday_close:.2f}"
                    ),
                    market_data_snapshot={
                        "open": today_open,
                        "close": current_price,
                        "prev_close": yesterday_close,
                        "gap_pct": round(gap_pct, 4),
                        "fill_rate": round(fill_rate, 4),
                        "gaps_found": gaps_found,
                        "partial_fill": round(partial_fill, 4),
                        "volume": current_volume,
                    },
                )
                signals.append(signal)

            except Exception as e:
                logger.warning(
                    "gap_fill_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "gap_fill_scan_complete",
            tickers_scanned=len(tickers),
            signals_generated=len(signals),
        )
        return signals
