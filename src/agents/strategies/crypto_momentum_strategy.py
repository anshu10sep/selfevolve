"""
Crypto Momentum Strategy Agent

Intraday crypto momentum that exploits the high-volatility nature
of crypto markets. Uses hourly bars (vs daily for equities) with
momentum indicators calibrated for crypto's larger typical moves.

Edge: Crypto trends tend to be sharper and more sustained than equities.
Higher base volatility → larger momentum returns per trade.
24/7 operation. Signal generation is fully deterministic.
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

logger = structlog.get_logger(component="strategy.crypto_momentum")


CRYPTO_MOMENTUM_IDENTITY_CORE = """You are the Crypto Momentum Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are a crypto momentum specialist operating on hourly bars. You capture
trending moves in crypto markets where momentum signals are amplified by
higher base volatility compared to equities.

## How You Work:
1. Monitor hourly bars on top crypto pairs
2. Calculate 12-bar momentum (equivalent to half a day)
3. Confirm with volume surge and RSI divergence
4. Enter on strong momentum with ATR-based stops
5. Hold for 6-24 hours with trailing stops

## Key Differences from Equity Momentum:
- Higher thresholds (crypto moves 3-5x larger than equities)
- Shorter lookback (12 hours vs 5 days)
- Wider stops (crypto ATR is much larger)
- 24/7 operation — no market hours restriction

## STRICT RULES:
- You ONLY trade crypto pairs listed in your preferred_pairs
- You require 3% minimum move (vs 2% for equities)
- You use wider stops (3x ATR vs 2x ATR for equities)
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class CryptoMomentumAgent(StrategyAgent):
    """
    Crypto momentum strategy: Captures sharp trending moves
    on hourly bars with volume confirmation. 24/7 operation.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Crypto Momentum",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=CRYPTO_MOMENTUM_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "crypto_momentum"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "lookback_bars": 12,             # 12 hourly bars = half day
            "entry_threshold": 0.03,          # 3% move (vs 2% for equities)
            "max_hold_bars": 48,              # 48 hours max hold
            "trailing_stop_atr_mult": 3.0,    # 3x ATR (wider for crypto)
            "take_profit_atr_mult": 4.0,      # 4x ATR target
            "volume_confirmation_mult": 1.3,   # Lower threshold (crypto is spikier)
            "atr_period": 14,
            "rsi_period": 14,
            "rsi_trend_threshold": 50.0,       # RSI must be > 50 for buys
            "min_volume_usd": 500_000,
            "preferred_pairs": [
                "BTC/USD", "ETH/USD", "SOL/USD",
                "AVAX/USD", "DOT/USD", "LINK/USD",
                "ARB/USD", "DOGE/USD", "MATIC/USD",
            ],
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.STRONG,
            "SIDEWAYS": MarketRegimeAffinity.WEAK,
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
        Scan crypto pairs for momentum on hourly bars.

        For each pair:
        1. Calculate N-bar return (12-bar default)
        2. Confirm with volume surge and RSI > 50
        3. Calculate ATR for stop/target (wider for crypto)
        4. Generate BUY signal if criteria met
        """
        signals = []
        lookback = self.get_param("lookback_bars", 12)
        threshold = self.get_param("entry_threshold", 0.03)
        vol_mult = self.get_param("volume_confirmation_mult", 1.3)
        atr_period = self.get_param("atr_period", 14)
        rsi_period = self.get_param("rsi_period", 14)
        rsi_threshold = self.get_param("rsi_trend_threshold", 50.0)
        stop_mult = self.get_param("trailing_stop_atr_mult", 3.0)
        tp_mult = self.get_param("take_profit_atr_mult", 4.0)
        min_vol = self.get_param("min_volume_usd", 500_000)
        preferred = self.get_param("preferred_pairs", [])

        target_tickers = [t for t in tickers if t in preferred] or tickers
        min_bars = max(lookback + 1, atr_period + 2, rsi_period + 2)

        for ticker in target_tickers:
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

                # Dollar volume check
                current_vol_usd = volumes[-1] * current_price
                if current_vol_usd < min_vol:
                    continue

                # 1. N-bar return
                lookback_price = closes[-(lookback + 1)]
                if lookback_price <= 0:
                    continue
                n_bar_return = (current_price - lookback_price) / lookback_price

                if n_bar_return < threshold:
                    continue

                # 2. Volume confirmation
                avg_volume = sum(volumes[-(lookback + 1):-1]) / max(1, lookback)
                if avg_volume <= 0 or volumes[-1] < avg_volume * vol_mult:
                    continue

                # 3. RSI trend confirmation
                rsi_values = self.calculate_rsi(closes, rsi_period)
                if rsi_values and rsi_values[-1] < rsi_threshold:
                    continue  # RSI too weak for momentum

                # 4. ATR for stops/targets (wider for crypto)
                atr_values = self.calculate_atr(highs, lows, closes, atr_period)
                if not atr_values:
                    continue
                current_atr = atr_values[-1]
                if current_atr <= 0:
                    continue

                stop_loss = round(current_price - (current_atr * stop_mult), 6)
                take_profit = round(current_price + (current_atr * tp_mult), 6)

                # Signal strength
                strength = min(1.0, abs(n_bar_return) / 0.08)  # 8% = max (crypto)
                vol_ratio = volumes[-1] / avg_volume if avg_volume > 0 else 1.0
                confidence = min(1.0, max(0.3, vol_ratio / 3))

                rsi_val = rsi_values[-1] if rsi_values else 50

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
                        f"Crypto momentum: {lookback}-bar return={n_bar_return:.1%}, "
                        f"RSI={rsi_val:.1f}, vol={vol_ratio:.1f}x avg, "
                        f"ATR={current_atr:.2f}"
                    ),
                    market_data_snapshot={
                        "close": current_price,
                        "n_bar_return": round(n_bar_return, 4),
                        "rsi": round(rsi_val, 2),
                        "volume_usd": round(current_vol_usd),
                        "atr": round(current_atr, 4),
                        "vol_ratio": round(vol_ratio, 2),
                    },
                )
                signals.append(signal)

            except Exception as e:
                logger.warning(
                    "crypto_momentum_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "crypto_momentum_scan_complete",
            tickers_scanned=len(target_tickers),
            signals_generated=len(signals),
        )
        return signals
