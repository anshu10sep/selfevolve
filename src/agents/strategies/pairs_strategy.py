"""
Pairs / Statistical Arbitrage Strategy Agent (Long-Only Variant)

Tracks correlated asset pairs and exploits mean reversion in their
price ratio spread. Since we operate a CASH account (no shorting),
this agent goes LONG on the underperformer when the spread z-score
exceeds the entry threshold.

Edge: Market-neutral in concept — profits from relative mispricing
regardless of market direction. Provides diversification.
Signal generation is fully deterministic — no LLM in the hot path.
"""

from __future__ import annotations

import math
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

logger = structlog.get_logger(component="strategy.pairs")


PAIRS_IDENTITY_CORE = """You are the Pairs/Statistical Arbitrage Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a statistical arbitrage specialist. You track correlated asset pairs
and exploit temporary divergences in their price ratio. When two normally
correlated assets diverge, you buy the underperformer, expecting the spread
to revert. Your philosophy: "Correlated assets that diverge must converge."

## Cash Account Constraint:
Since we operate a CASH account, you can only go LONG on the underperformer.
You cannot short the outperformer. This means you capture roughly half the
theoretical pairs trade return, but with no margin risk.

## STRICT RULES:
- You ONLY trade pre-configured, validated pairs with correlation > 0.80
- You track z-score of the price ratio spread
- Entry when z-score > threshold, exit when z-score < exit threshold
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class PairsStrategyAgent(StrategyAgent):
    """
    Pairs/stat-arb strategy (long-only): Buy the underperformer
    in a correlated pair when spread z-score exceeds threshold.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Pairs Strategy",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=PAIRS_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "pairs"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "pairs": [
                ["XLK", "QQQ"],
                ["GOOGL", "META"],
                ["AAPL", "MSFT"],
                ["SPY", "QQQ"],
                ["AMD", "NVDA"],
            ],
            "correlation_min": 0.80,
            "zscore_entry": 2.0,
            "zscore_exit": 0.5,
            "lookback_days": 60,
            "max_hold_days": 10,
            "stop_loss_pct": 0.03,
            "min_volume": 1_000_000,
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.NEUTRAL,
            "SIDEWAYS": MarketRegimeAffinity.STRONG,
            "BEAR": MarketRegimeAffinity.NEUTRAL,
            "HIGH_VOL": MarketRegimeAffinity.NEUTRAL,
            "PANIC": MarketRegimeAffinity.DISABLED,
        }

    def _calculate_correlation(
        self, series_a: list[float], series_b: list[float]
    ) -> float:
        """Calculate Pearson correlation between two price series."""
        if len(series_a) != len(series_b) or len(series_a) < 5:
            return 0.0

        n = len(series_a)
        mean_a = sum(series_a) / n
        mean_b = sum(series_b) / n

        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(series_a, series_b)) / n
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in series_a) / n)
        std_b = math.sqrt(sum((b - mean_b) ** 2 for b in series_b) / n)

        if std_a == 0 or std_b == 0:
            return 0.0
        return cov / (std_a * std_b)

    def _calculate_spread_zscore(
        self, series_a: list[float], series_b: list[float]
    ) -> tuple[float, float, float]:
        """
        Calculate the z-score of the price ratio spread.

        Returns:
            (current_zscore, spread_mean, spread_std)
        """
        if len(series_a) != len(series_b) or len(series_a) < 5:
            return 0.0, 0.0, 0.0

        # Price ratio: A / B
        ratios = [
            a / b if b > 0 else 0
            for a, b in zip(series_a, series_b)
        ]
        ratios = [r for r in ratios if r > 0]

        if len(ratios) < 5:
            return 0.0, 0.0, 0.0

        mean_ratio = sum(ratios) / len(ratios)
        std_ratio = math.sqrt(
            sum((r - mean_ratio) ** 2 for r in ratios) / len(ratios)
        )

        if std_ratio == 0:
            return 0.0, mean_ratio, 0.0

        current_ratio = ratios[-1]
        zscore = (current_ratio - mean_ratio) / std_ratio

        return zscore, mean_ratio, std_ratio

    async def generate_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """
        Scan configured pairs for spread divergence.

        For each pair:
        1. Calculate correlation — skip if below threshold
        2. Calculate z-score of price ratio spread
        3. If z-score > entry: BUY underperformer
        4. If z-score < exit and active position: SELL
        """
        signals = []
        pairs = self.get_param("pairs", [])
        corr_min = self.get_param("correlation_min", 0.80)
        zscore_entry = self.get_param("zscore_entry", 2.0)
        zscore_exit = self.get_param("zscore_exit", 0.5)
        stop_pct = self.get_param("stop_loss_pct", 0.03)
        min_vol = self.get_param("min_volume", 1_000_000)

        for pair in pairs:
            try:
                if len(pair) != 2:
                    continue

                ticker_a, ticker_b = pair[0], pair[1]

                # Both tickers need to be in market_data
                data_a = market_data.get(ticker_a, {})
                data_b = market_data.get(ticker_b, {})
                bars_a = data_a.get("bars", [])
                bars_b = data_b.get("bars", [])

                if len(bars_a) < 20 or len(bars_b) < 20:
                    continue

                # Align lengths
                min_len = min(len(bars_a), len(bars_b))
                closes_a = [b["close"] for b in bars_a[-min_len:]]
                closes_b = [b["close"] for b in bars_b[-min_len:]]
                volumes_a = [b["volume"] for b in bars_a[-min_len:]]
                volumes_b = [b["volume"] for b in bars_b[-min_len:]]

                # 1. Correlation check
                correlation = self._calculate_correlation(closes_a, closes_b)
                if abs(correlation) < corr_min:
                    continue

                # 2. Z-score of spread
                zscore, spread_mean, spread_std = self._calculate_spread_zscore(
                    closes_a, closes_b
                )

                price_a = closes_a[-1]
                price_b = closes_b[-1]

                # 3. Identify underperformer
                # If z-score > 0: A is outperforming → buy B (underperformer)
                # If z-score < 0: B is outperforming → buy A (underperformer)
                if abs(zscore) > zscore_entry:
                    underperformer = ticker_b if zscore > 0 else ticker_a
                    outperformer = ticker_a if zscore > 0 else ticker_b
                    under_price = price_b if zscore > 0 else price_a
                    under_volumes = volumes_b if zscore > 0 else volumes_a

                    # Volume check
                    if under_volumes[-1] < min_vol:
                        continue

                    # Skip if already holding
                    if self.has_active_position(underperformer):
                        continue

                    stop_loss = round(under_price * (1 - stop_pct), 2)
                    # Target: spread reverts to mean → estimate price move
                    revert_pct = abs(zscore) * spread_std / spread_mean if spread_mean > 0 else 0.02
                    take_profit = round(under_price * (1 + min(revert_pct, 0.05)), 2)

                    strength = min(1.0, abs(zscore) / (zscore_entry * 2))
                    confidence = min(1.0, max(0.3, abs(correlation)))

                    signal = StrategySignal(
                        strategy_name=self.strategy_name,
                        strategy_version=self.parameters.version,
                        ticker=underperformer,
                        signal_type=SignalType.BUY,
                        strength=round(strength, 3),
                        confidence=round(confidence, 3),
                        entry_price=under_price,
                        stop_loss_price=stop_loss,
                        take_profit_price=take_profit,
                        rationale=(
                            f"Pair {ticker_a}/{ticker_b}: z-score={zscore:.2f} "
                            f"(>{zscore_entry}), corr={correlation:.2f}, "
                            f"buying underperformer {underperformer}"
                        ),
                        market_data_snapshot={
                            "pair": [ticker_a, ticker_b],
                            "zscore": round(zscore, 4),
                            "correlation": round(correlation, 4),
                            "price_a": price_a,
                            "price_b": price_b,
                            "spread_mean": round(spread_mean, 4),
                            "spread_std": round(spread_std, 4),
                        },
                    )
                    signals.append(signal)

                # 4. Exit signal for active positions
                for active_ticker in [ticker_a, ticker_b]:
                    if self.has_active_position(active_ticker) and abs(zscore) < zscore_exit:
                        signal = StrategySignal(
                            strategy_name=self.strategy_name,
                            strategy_version=self.parameters.version,
                            ticker=active_ticker,
                            signal_type=SignalType.SELL,
                            strength=0.6,
                            confidence=0.7,
                            entry_price=price_a if active_ticker == ticker_a else price_b,
                            rationale=(
                                f"Pair {ticker_a}/{ticker_b}: spread reverted, "
                                f"z-score={zscore:.2f} (<{zscore_exit})"
                            ),
                            market_data_snapshot={
                                "pair": [ticker_a, ticker_b],
                                "zscore": round(zscore, 4),
                            },
                        )
                        signals.append(signal)

            except Exception as e:
                logger.warning(
                    "pairs_signal_error",
                    pair=pair,
                    error=str(e),
                )
                continue

        logger.info(
            "pairs_scan_complete",
            pairs_scanned=len(pairs),
            signals_generated=len(signals),
        )
        return signals
