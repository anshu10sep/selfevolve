"""
Crypto Scalping Strategy Agent

Ultra-short-term intraday strategy for crypto markets (24/7).
Uses 1-minute and 5-minute bars to capture small price moves
with high frequency. Relies on VWAP deviation + RSI extremes
on short timeframes.

Edge: High trade frequency generates consistent small profits.
Crypto's 24/7 availability + high volatility = more opportunities.
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

logger = structlog.get_logger(component="strategy.crypto_scalper")


CRYPTO_SCALPER_IDENTITY_CORE = """You are the Crypto Scalping Strategy Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are an intraday crypto scalper. You operate 24/7 on the most liquid
crypto pairs (BTC/USD, ETH/USD, SOL/USD, etc.) and capture small, rapid
price moves using short-timeframe technical indicators.

## How You Work:
1. Monitor 5-minute bars on crypto pairs
2. Calculate short-period RSI (5-period) for overbought/oversold
3. Use EMA crossovers (8/21) for trend direction
4. Enter on RSI extremes aligned with EMA trend
5. Exit quickly with tight targets (0.3% profit) and stops (0.5% loss)

## STRICT RULES:
- You ONLY trade crypto pairs, NEVER equities
- Your timeframe is 5-minute bars (intraday, not swing)
- Maximum hold time: 2 hours (24 bars at 5-min)
- You always set stop-loss and take-profit orders
- Position sizes are SMALL (high frequency, small PnL per trade)
- Your signal generation is DETERMINISTIC — no LLM for signals
"""


class CryptoScalpingAgent(StrategyAgent):
    """
    Crypto scalping strategy: Short-timeframe RSI + EMA
    crossover on 5-minute bars. 24/7 operation.
    """

    def __init__(self, llm, trust_weight: float = 1.0, mode: StrategyMode = StrategyMode.PAPER):
        identity = AgentIdentity(
            agent_name="Crypto Scalper",
            agent_role=AgentRole.AUDITOR,
            agent_type=AgentType.SPECIALIST,
            identity_core=CRYPTO_SCALPER_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight, mode)

    @property
    def strategy_name(self) -> str:
        return "crypto_scalper"

    def _default_parameters(self) -> dict[str, Any]:
        return {
            "rsi_period": 5,
            "rsi_oversold": 25.0,
            "rsi_overbought": 75.0,
            "ema_fast": 8,
            "ema_slow": 21,
            "take_profit_pct": 0.003,      # 0.3% target
            "stop_loss_pct": 0.005,         # 0.5% stop
            "max_hold_bars": 24,            # 24 x 5min = 2 hours
            "min_volume_usd": 100_000,      # Min dollar volume per bar
            "preferred_pairs": [
                "BTC/USD", "ETH/USD", "SOL/USD",
                "AVAX/USD", "LINK/USD", "DOT/USD",
            ],
        }

    def get_regime_affinity(self) -> dict[str, MarketRegimeAffinity]:
        return {
            "BULL": MarketRegimeAffinity.STRONG,
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
        Scan crypto pairs for scalping opportunities on 5-min bars.

        For each pair:
        1. Calculate short-period RSI (5-bar)
        2. Calculate EMA(8) and EMA(21) for trend
        3. BUY: RSI oversold AND EMA_fast > EMA_slow (uptrend)
        4. SELL: RSI overbought AND holding position
        """
        signals = []
        rsi_period = self.get_param("rsi_period", 5)
        rsi_oversold = self.get_param("rsi_oversold", 25.0)
        rsi_overbought = self.get_param("rsi_overbought", 75.0)
        ema_fast_period = self.get_param("ema_fast", 8)
        ema_slow_period = self.get_param("ema_slow", 21)
        tp_pct = self.get_param("take_profit_pct", 0.003)
        sl_pct = self.get_param("stop_loss_pct", 0.005)
        min_vol = self.get_param("min_volume_usd", 100_000)
        preferred = self.get_param("preferred_pairs", [])

        # Filter to preferred crypto pairs
        target_tickers = [t for t in tickers if t in preferred] or tickers

        min_bars = max(rsi_period + 2, ema_slow_period + 2)

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

                # Volume check (dollar volume)
                current_vol = volumes[-1] * current_price if len(volumes) > 0 else 0
                if current_vol < min_vol:
                    continue

                # 1. Short-period RSI
                rsi_values = self.calculate_rsi(closes, rsi_period)
                if not rsi_values:
                    continue
                current_rsi = rsi_values[-1]

                # 2. EMA crossover for trend direction
                ema_fast = self.calculate_ema(closes, ema_fast_period)
                ema_slow = self.calculate_ema(closes, ema_slow_period)
                if not ema_fast or not ema_slow:
                    continue

                # Align lengths
                min_len = min(len(ema_fast), len(ema_slow))
                if min_len < 2:
                    continue
                
                current_fast = ema_fast[-1]
                current_slow = ema_slow[-1]
                prev_fast = ema_fast[-2] if len(ema_fast) > 1 else current_fast
                prev_slow = ema_slow[-2] if len(ema_slow) > 1 else current_slow

                uptrend = current_fast > current_slow
                downtrend = current_fast < current_slow
                # Crossover detection
                bullish_cross = prev_fast <= prev_slow and current_fast > current_slow
                bearish_cross = prev_fast >= prev_slow and current_fast < current_slow

                # ── BUY Signal ──
                if (
                    not self.has_active_position(ticker)
                    and current_rsi < rsi_oversold
                    and uptrend
                ):
                    stop_loss = round(current_price * (1 - sl_pct), 6)
                    take_profit = round(current_price * (1 + tp_pct), 6)

                    # Strength: deeper RSI = stronger signal
                    rsi_depth = (rsi_oversold - current_rsi) / rsi_oversold
                    ema_spread = abs(current_fast - current_slow) / current_slow if current_slow > 0 else 0
                    strength = min(1.0, rsi_depth + ema_spread * 50)
                    confidence = min(1.0, max(0.3, strength * 0.9))

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
                            f"Crypto scalp: RSI({rsi_period})={current_rsi:.1f} (<{rsi_oversold}), "
                            f"EMA({ema_fast_period})={current_fast:.2f} > EMA({ema_slow_period})={current_slow:.2f}, "
                            f"{'bullish crossover' if bullish_cross else 'uptrend'}"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "rsi": round(current_rsi, 2),
                            "ema_fast": round(current_fast, 4),
                            "ema_slow": round(current_slow, 4),
                            "volume_usd": round(current_vol),
                            "bullish_cross": bullish_cross,
                        },
                    )
                    signals.append(signal)

                # ── SELL Signal (overbought exit or bearish cross) ──
                elif (
                    self.has_active_position(ticker)
                    and (current_rsi > rsi_overbought or bearish_cross)
                ):
                    signal = StrategySignal(
                        strategy_name=self.strategy_name,
                        strategy_version=self.parameters.version,
                        ticker=ticker,
                        signal_type=SignalType.SELL,
                        strength=0.7 if current_rsi > rsi_overbought else 0.6,
                        confidence=0.75,
                        entry_price=current_price,
                        rationale=(
                            f"Scalp exit: RSI={current_rsi:.1f}"
                            f"{' (overbought)' if current_rsi > rsi_overbought else ''}"
                            f"{' bearish EMA cross' if bearish_cross else ''}"
                        ),
                        market_data_snapshot={
                            "close": current_price,
                            "rsi": round(current_rsi, 2),
                        },
                    )
                    signals.append(signal)

            except Exception as e:
                logger.warning(
                    "crypto_scalp_signal_error",
                    ticker=ticker,
                    error=str(e),
                )
                continue

        logger.info(
            "crypto_scalp_scan_complete",
            tickers_scanned=len(target_tickers),
            signals_generated=len(signals),
        )
        return signals
