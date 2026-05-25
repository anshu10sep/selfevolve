"""
Overnight Hold Strategy Agent

Buys at market close and sells at next market open to capture the
"overnight return premium" — the well-documented phenomenon that
most equity returns historically come from overnight gaps rather
than intraday moves.

Edge: Simple execution (buy close, sell open). Captures a persistent
anomaly. Good for passive income generation.
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

logger = structlog.get_logger(component="strategy.overnight")


OVERNIGHT_IDENTITY_CORE = """You are the Overnight Hold Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are an overnight premium specialist. You exploit the well-documented
"overnight return anomaly" — the phenomenon that most long-term equity returns
are generated during overnight sessions (close-to-open), not during the
regular trading day (open-to-close). Your philosophy: "Sleep and earn."

## How You Work:
1. Analyze each ticker's historical overnight returns (close-to-open)
2. Select tickers with the highest average positive overnight returns
3. Buy at close, sell at next open
4. Diversify across sectors to reduce concentration risk

## STRICT RULES:
- You hold positions for ONE night only (close-to-open)
- You require positive historical overnight drift (statistically significant)
- You diversify — max 1 position per sector
- Maximum positions = configurable parameter (default 3)
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class OvernightHoldStrategyAgent(StrategyAgent):
    """
    Overnight hold strategy: Buy at close, sell at next open.
    Captures the overnight return premium anomaly.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Overnight Hold Strategy",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=OVERNIGHT_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "overnight_hold"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "min_avg_overnight_return": 0.0005,
            "lookback_days": 30,
            "max_positions": 3,
            "stop_loss_pct": 0.02,
            "min_volume": 5_000_000,
            "min_overnight_count": 10,
            "min_positive_rate": 0.55,
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.STRONG,
            "SIDEWAYS": MarketRegimeAffinity.NEUTRAL,
            "BEAR": MarketRegimeAffinity.WEAK,
            "HIGH_VOL": MarketRegimeAffinity.WEAK,
            "PANIC": MarketRegimeAffinity.DISABLED,
        }

    def _calculate_overnight_stats(
        self,
        bars: list[dict],
        lookback: int,
    ) -> dict[str, Any]:
        """
        Calculate overnight return statistics for a ticker.

        Overnight return = (open[t+1] - close[t]) / close[t]

        Returns:
            {
                "avg_return": float,
                "positive_rate": float,
                "total_nights": int,
                "returns": list[float],
            }
        """
        recent_bars = bars[-lookback:] if len(bars) >= lookback else bars

        overnight_returns = []
        for i in range(len(recent_bars) - 1):
            close_today = recent_bars[i]["close"]
            open_tomorrow = recent_bars[i + 1]["open"]

            if close_today <= 0:
                continue

            overnight_ret = (open_tomorrow - close_today) / close_today
            overnight_returns.append(overnight_ret)

        if not overnight_returns:
            return {
                "avg_return": 0.0,
                "positive_rate": 0.0,
                "total_nights": 0,
                "returns": [],
            }

        positive = sum(1 for r in overnight_returns if r > 0)
        avg_ret = sum(overnight_returns) / len(overnight_returns)

        return {
            "avg_return": avg_ret,
            "positive_rate": positive / len(overnight_returns),
            "total_nights": len(overnight_returns),
            "returns": overnight_returns,
        }

    async def generate_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """
        Scan for overnight hold candidates.

        For each ticker:
        1. Calculate average overnight return over lookback period
        2. Filter for positive average return > threshold
        3. Rank by average overnight return
        4. Select top N candidates (max_positions)
        5. Generate BUY signals (to be executed at close)
        """
        candidates = []
        lookback = self.get_param("lookback_days", 30)
        min_avg_ret = self.get_param("min_avg_overnight_return", 0.0005)
        max_pos = self.get_param("max_positions", 3)
        stop_pct = self.get_param("stop_loss_pct", 0.02)
        min_vol = self.get_param("min_volume", 5_000_000)
        min_nights = self.get_param("min_overnight_count", 10)
        min_pos_rate = self.get_param("min_positive_rate", 0.55)

        # Count active positions
        active_count = len(self._active_trades)
        available_slots = max(0, max_pos - active_count)
        if available_slots == 0:
            return []

        for ticker in tickers:
            try:
                ticker_data = market_data.get(ticker, {})
                bars = ticker_data.get("bars", [])

                if len(bars) < max(lookback, min_nights + 2):
                    continue

                if self.has_active_position(ticker):
                    continue

                # Volume filter
                volumes = [b["volume"] for b in bars]
                avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
                if avg_volume < min_vol:
                    continue

                # Calculate overnight stats
                stats = self._calculate_overnight_stats(bars, lookback)

                if stats["total_nights"] < min_nights:
                    continue
                if stats["avg_return"] < min_avg_ret:
                    continue
                if stats["positive_rate"] < min_pos_rate:
                    continue

                current_price = bars[-1]["close"]
                if current_price <= 0:
                    continue

                candidates.append({
                    "ticker": ticker,
                    "current_price": current_price,
                    "avg_overnight_return": stats["avg_return"],
                    "positive_rate": stats["positive_rate"],
                    "total_nights": stats["total_nights"],
                    "avg_volume": avg_volume,
                })

            except Exception as e:
                logger.warning(
                    "overnight_analysis_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        # Rank by average overnight return, select top N
        candidates.sort(key=lambda x: x["avg_overnight_return"], reverse=True)
        selected = candidates[:available_slots]

        # Generate signals
        signals = []
        for candidate in selected:
            ticker = candidate["ticker"]
            price = candidate["current_price"]
            avg_ret = candidate["avg_overnight_return"]
            pos_rate = candidate["positive_rate"]

            stop_loss = round(price * (1 - stop_pct), 2)
            # Expected return based on historical average
            expected_gain = price * avg_ret
            take_profit = round(price * (1 + avg_ret * 2), 2)  # 2x average for target

            # Strength: based on average return magnitude
            strength = min(1.0, avg_ret / 0.005)  # 0.5% avg return = max strength
            # Confidence: based on positive rate
            confidence = min(1.0, max(0.3, pos_rate))

            signal = StrategySignal(
                strategy_name=self.strategy_name,
                strategy_version=self.parameters.version,
                ticker=ticker,
                signal_type=SignalType.BUY,
                strength=round(strength, 3),
                confidence=round(confidence, 3),
                entry_price=price,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                rationale=(
                    f"Overnight premium: avg return={avg_ret:.3%}, "
                    f"positive rate={pos_rate:.0%} over {candidate['total_nights']} nights, "
                    f"buy at close, sell at open"
                ),
                market_data_snapshot={
                    "close": price,
                    "avg_overnight_return": round(avg_ret, 6),
                    "positive_rate": round(pos_rate, 4),
                    "total_nights": candidate["total_nights"],
                    "avg_volume": round(candidate["avg_volume"]),
                },
            )
            signals.append(signal)

        logger.info(
            "overnight_scan_complete",
            tickers_scanned=len(tickers),
            candidates_found=len(candidates),
            signals_generated=len(signals),
        )
        return signals
