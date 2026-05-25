"""
Crypto Mean Reversion Strategy Agent

Intraday mean reversion on crypto pairs using Bollinger Bands on
15-minute bars. Crypto's high volatility creates frequent oversold/
overbought conditions that revert quickly.

Edge: Crypto Bollinger Band touches revert more aggressively than
equities due to high retail participation and 24/7 continuous trading.
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

logger = structlog.get_logger(component="strategy.crypto_mean_rev")


CRYPTO_MEAN_REV_IDENTITY_CORE = """You are the Crypto Mean Reversion Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a crypto mean reversion specialist on 15-minute bars. You exploit
the rapid reversions that occur when crypto prices touch Bollinger Band
extremes. Crypto's high retail participation amplifies overreactions,
creating more reversion opportunities than in equity markets.

## How You Work:
1. Monitor 15-minute bars on liquid crypto pairs
2. Calculate Bollinger Bands (20-period, 2.5 std dev — wider for crypto)
3. Calculate RSI (7-period — shorter for intraday)
4. BUY when price drops below lower band AND RSI < 25
5. Target: middle Bollinger Band (SMA). Stop: 1% below entry.

## STRICT RULES:
- You trade ONLY when BOTH RSI and BB confirm (dual confirmation)
- Maximum hold time: 4 hours (16 bars at 15-min)
- Tight stops at 1% (crypto can move fast against you)
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class CryptoMeanReversionAgent(StrategyAgent):
    """
    Crypto mean reversion: Buy on RSI oversold + below lower
    Bollinger Band on 15-minute bars. Target = middle band.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Crypto Mean Reversion",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=CRYPTO_MEAN_REV_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "crypto_mean_reversion"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "rsi_period": 7,                  # Shorter for intraday
            "rsi_oversold": 25.0,
            "rsi_overbought": 75.0,
            "bb_period": 20,
            "bb_std_dev": 2.5,                # Wider for crypto
            "stop_loss_pct": 0.01,            # 1% stop
            "max_hold_bars": 16,              # 16 x 15min = 4 hours
            "min_volume_usd": 200_000,
            "preferred_pairs": [
                "BTC/USD", "ETH/USD", "SOL/USD",
                "AVAX/USD", "LINK/USD", "DOT/USD",
                "ARB/USD", "DOGE/USD",
            ],
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.NEUTRAL,
            "SIDEWAYS": MarketRegimeAffinity.STRONG,
            "BEAR": MarketRegimeAffinity.NEUTRAL,
            "HIGH_VOL": MarketRegimeAffinity.STRONG,
            "PANIC": MarketRegimeAffinity.WEAK,
        }

    async def generate_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """
        Scan crypto pairs for mean reversion on 15-min bars.

        For each pair:
        1. Calculate RSI (7-period)
        2. Calculate Bollinger Bands (20-period, 2.5 std dev)
        3. BUY when RSI < oversold AND price < lower band
        4. SELL when RSI > overbought OR price > upper band
        """
        signals = []
        rsi_period = self.get_param("rsi_period", 7)
        rsi_oversold = self.get_param("rsi_oversold", 25.0)
        rsi_overbought = self.get_param("rsi_overbought", 75.0)
        bb_period = self.get_param("bb_period", 20)
        bb_std = self.get_param("bb_std_dev", 2.5)
        stop_pct = self.get_param("stop_loss_pct", 0.01)
        min_vol = self.get_param("min_volume_usd", 200_000)
        preferred = self.get_param("preferred_pairs", [])

        target_tickers = [t for t in tickers if t in preferred] or tickers
        min_bars = max(rsi_period + 2, bb_period + 1)

        for ticker in target_tickers:
            try:
                ticker_data = market_data.get(ticker, {})
                bars = ticker_data.get("bars", [])

                if len(bars) < min_bars:
                    continue

                closes = [b["close"] for b in bars]
                volumes = [b["volume"] for b in bars]

                current_price = closes[-1]
                if current_price <= 0:
                    continue

                # Dollar volume check
                vol_usd = volumes[-1] * current_price if volumes else 0
                if vol_usd < min_vol:
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

                # ── BUY: Oversold + below lower band ──
                if (
                    not self.has_active_position(ticker)
                    and current_rsi < rsi_oversold
                    and current_price < current_lower
                ):
                    stop_loss = round(current_price * (1 - stop_pct), 6)
                    take_profit = round(current_middle, 6)  # Target = SMA

                    rsi_depth = (rsi_oversold - current_rsi) / rsi_oversold
                    bb_depth = (current_lower - current_price) / current_lower if current_lower > 0 else 0
                    strength = min(1.0, (rsi_depth + bb_depth))
                    confidence = min(1.0, max(0.35, strength * 1.1))

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
                            f"Crypto mean reversion: RSI({rsi_period})={current_rsi:.1f} (<{rsi_oversold}), "
                            f"price=${current_price:.2f} below BB lower=${current_lower:.2f}, "
                            f"target=SMA=${current_middle:.2f}"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "rsi": round(current_rsi, 2),
                            "bb_upper": round(current_upper, 4),
                            "bb_middle": round(current_middle, 4),
                            "bb_lower": round(current_lower, 4),
                            "volume_usd": round(vol_usd),
                        },
                    )
                    signals.append(signal)

                # ── SELL: Overbought or above upper band ──
                elif (
                    self.has_active_position(ticker)
                    and (current_rsi > rsi_overbought or current_price > current_upper)
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
                            f"Crypto reversion complete: RSI={current_rsi:.1f}, "
                            f"price=${current_price:.2f} vs BB upper=${current_upper:.2f}"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "rsi": round(current_rsi, 2),
                        },
                    )
                    signals.append(signal)

            except Exception as e:
                logger.warning(
                    "crypto_mean_rev_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "crypto_mean_rev_scan_complete",
            tickers_scanned=len(target_tickers),
            signals_generated=len(signals),
        )
        return signals
