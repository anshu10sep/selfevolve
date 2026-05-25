"""
Market Regime Detection — Deterministic Classification

Classifies current market conditions into regimes that drive
strategy allocation decisions. Uses ONLY deterministic indicators:
  - ADX for trend strength
  - VIX proxy via ATR expansion
  - Price vs SMA for trend direction
  - Bollinger Band width for volatility regime

NO LLM involvement — this is pure math.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from agents.skills.validator import skill

logger = structlog.get_logger(component="regime_detection")


# ════════════════════════════════════════════════════════════════════
# REGIME CLASSIFICATION
# ════════════════════════════════════════════════════════════════════

@skill("strategy_agent")
def detect_market_regime(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
    vix_level: float = 0.0,
) -> dict:
    """
    Classify the current market regime using deterministic indicators.

    Regimes:
      - TRENDING_UP: Strong uptrend (ADX > 25, price > SMA, higher highs)
      - TRENDING_DOWN: Strong downtrend (ADX > 25, price < SMA, lower lows)
      - MEAN_REVERTING: Range-bound (ADX < 20, price oscillating around SMA)
      - VOLATILE: High volatility (ATR expanding, VIX > 25)
      - BREAKOUT: Transitioning from low vol to high vol (BB squeeze → expansion)
      - LOW_VOLATILITY: Calm market (ATR contracting, VIX < 15)

    Args:
        closes: List of closing prices (most recent last)
        highs: List of high prices
        lows: List of low prices
        volumes: List of volume data
        vix_level: Current VIX level (0 if unavailable)

    Returns:
        Regime classification with confidence and supporting indicators
    """
    if len(closes) < 50:
        return {
            "regime": "LOW_VOLATILITY",
            "confidence": 0.3,
            "reason": "Insufficient data for regime detection",
            "indicators": {},
        }

    # ── Calculate Indicators ───────────────────────────────────────
    sma_20 = _sma(closes, 20)
    sma_50 = _sma(closes, 50)
    atr_values = _atr(highs, lows, closes, 14)
    bb_width = _bollinger_width(closes, 20, 2.0)
    adx = _calculate_adx_value(highs, lows, closes, 14)

    current_price = closes[-1]
    current_sma_20 = sma_20[-1] if sma_20 else current_price
    current_sma_50 = sma_50[-1] if sma_50 else current_price
    current_atr = atr_values[-1] if atr_values else 0
    current_bb_width = bb_width[-1] if bb_width else 0

    # ATR trend (expanding or contracting)
    if len(atr_values) >= 5:
        atr_recent = sum(atr_values[-5:]) / 5
        atr_older = sum(atr_values[-10:-5]) / 5 if len(atr_values) >= 10 else atr_recent
        atr_expanding = atr_recent > atr_older * 1.1
        atr_contracting = atr_recent < atr_older * 0.9
    else:
        atr_expanding = False
        atr_contracting = False

    # BB width trend (squeeze detection)
    if len(bb_width) >= 10:
        bb_recent = sum(bb_width[-5:]) / 5
        bb_older = sum(bb_width[-10:-5]) / 5
        bb_squeezing = bb_recent < bb_older * 0.85  # Width narrowing
        bb_expanding = bb_recent > bb_older * 1.3   # Width widening
    else:
        bb_squeezing = False
        bb_expanding = False

    # Higher highs / lower lows
    if len(closes) >= 20:
        recent_highs = [max(highs[i-5:i]) for i in range(len(highs)-15, len(highs), 5) if i >= 5]
        higher_highs = len(recent_highs) >= 2 and all(
            recent_highs[i] > recent_highs[i-1] for i in range(1, len(recent_highs))
        )
        lower_lows_list = [min(lows[i-5:i]) for i in range(len(lows)-15, len(lows), 5) if i >= 5]
        lower_lows = len(lower_lows_list) >= 2 and all(
            lower_lows_list[i] < lower_lows_list[i-1] for i in range(1, len(lower_lows_list))
        )
    else:
        higher_highs = False
        lower_lows = False

    # ── Regime Classification ──────────────────────────────────────
    indicators = {
        "adx": round(adx, 2),
        "price_vs_sma20": round((current_price / current_sma_20 - 1) * 100, 2),
        "price_vs_sma50": round((current_price / current_sma_50 - 1) * 100, 2),
        "atr": round(current_atr, 4),
        "atr_expanding": atr_expanding,
        "bb_width": round(current_bb_width, 4),
        "bb_squeezing": bb_squeezing,
        "bb_expanding": bb_expanding,
        "higher_highs": higher_highs,
        "lower_lows": lower_lows,
        "vix": vix_level,
    }

    # Decision tree (priority-ordered)

    # 1. VOLATILE: VIX high or ATR expanding rapidly
    if vix_level > 30 or (atr_expanding and current_atr > 0 and
                           current_atr / current_price * 100 > 3):
        return {
            "regime": "VOLATILE",
            "confidence": 0.8 if vix_level > 30 else 0.65,
            "reason": f"High volatility (VIX={vix_level:.0f}, ATR expanding)",
            "indicators": indicators,
            "strategy_boost": {"momentum": 0.5, "mean_reversion": 0.7, "breakout": 1.2,
                               "pairs": 0.5, "vwap": 0.6},
        }

    # 2. BREAKOUT: BB squeeze followed by expansion
    if bb_expanding and (bb_squeezing or (len(bb_width) >= 20 and
                                           min(bb_width[-20:-5]) < bb_width[-1] * 0.5)):
        return {
            "regime": "BREAKOUT",
            "confidence": 0.7,
            "reason": "Bollinger Band squeeze → expansion (breakout in progress)",
            "indicators": indicators,
            "strategy_boost": {"momentum": 1.3, "mean_reversion": 0.3, "breakout": 1.5,
                               "pairs": 0.8, "vwap": 0.5},
        }

    # 3. TRENDING_UP: ADX strong + price above SMAs + higher highs
    if adx > 25 and current_price > current_sma_20 and current_price > current_sma_50:
        confidence = 0.6
        if higher_highs:
            confidence += 0.15
        if adx > 40:
            confidence += 0.1
        return {
            "regime": "TRENDING_UP",
            "confidence": min(0.9, confidence),
            "reason": f"Strong uptrend (ADX={adx:.0f}, price above SMA20/50)",
            "indicators": indicators,
            "strategy_boost": {"momentum": 1.5, "mean_reversion": 0.5, "breakout": 1.0,
                               "pairs": 0.8, "vwap": 0.8},
        }

    # 4. TRENDING_DOWN: ADX strong + price below SMAs + lower lows
    if adx > 25 and current_price < current_sma_20 and current_price < current_sma_50:
        confidence = 0.6
        if lower_lows:
            confidence += 0.15
        return {
            "regime": "TRENDING_DOWN",
            "confidence": min(0.9, confidence),
            "reason": f"Strong downtrend (ADX={adx:.0f}, price below SMA20/50)",
            "indicators": indicators,
            "strategy_boost": {"momentum": 0.3, "mean_reversion": 0.7, "breakout": 0.5,
                               "pairs": 1.0, "vwap": 0.5},
        }

    # 5. LOW_VOLATILITY: BB contracting, ATR contracting
    if atr_contracting and (vix_level < 15 or vix_level == 0):
        return {
            "regime": "LOW_VOLATILITY",
            "confidence": 0.6,
            "reason": f"Low volatility (ATR contracting, VIX={vix_level:.0f})",
            "indicators": indicators,
            "strategy_boost": {"momentum": 0.8, "mean_reversion": 1.0, "breakout": 0.7,
                               "pairs": 1.2, "vwap": 1.2},
        }

    # 6. DEFAULT: MEAN_REVERTING (range-bound)
    return {
        "regime": "MEAN_REVERTING",
        "confidence": 0.5,
        "reason": f"Range-bound market (ADX={adx:.0f}, no clear trend)",
        "indicators": indicators,
        "strategy_boost": {"momentum": 0.5, "mean_reversion": 1.5, "breakout": 0.5,
                           "pairs": 1.3, "vwap": 1.3},
    }


@skill("strategy_agent")
def get_regime_strategy_weights(
    regime: str,
) -> dict:
    """
    Get the recommended strategy allocation weights for a given regime.

    Returns multipliers that the Portfolio Manager applies to base allocations.

    Args:
        regime: Current market regime name

    Returns:
        Dict mapping strategy_name → weight multiplier (1.0 = normal)
    """
    REGIME_WEIGHTS = {
        "TRENDING_UP": {
            "momentum": 1.5,
            "mean_reversion": 0.5,
            "breakout": 1.0,
            "pairs": 0.8,
            "vwap": 0.8,
        },
        "TRENDING_DOWN": {
            "momentum": 0.3,
            "mean_reversion": 0.7,
            "breakout": 0.5,
            "pairs": 1.0,
            "vwap": 0.5,
        },
        "MEAN_REVERTING": {
            "momentum": 0.5,
            "mean_reversion": 1.5,
            "breakout": 0.5,
            "pairs": 1.3,
            "vwap": 1.3,
        },
        "VOLATILE": {
            "momentum": 0.5,
            "mean_reversion": 0.7,
            "breakout": 1.2,
            "pairs": 0.5,
            "vwap": 0.6,
        },
        "BREAKOUT": {
            "momentum": 1.3,
            "mean_reversion": 0.3,
            "breakout": 1.5,
            "pairs": 0.8,
            "vwap": 0.5,
        },
        "LOW_VOLATILITY": {
            "momentum": 0.8,
            "mean_reversion": 1.0,
            "breakout": 0.7,
            "pairs": 1.2,
            "vwap": 1.2,
        },
    }

    return REGIME_WEIGHTS.get(regime, {
        "momentum": 1.0,
        "mean_reversion": 1.0,
        "breakout": 1.0,
        "pairs": 1.0,
        "vwap": 1.0,
    })


# ════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS (deterministic math)
# ════════════════════════════════════════════════════════════════════

def _sma(values: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    if len(values) < period:
        return []
    return [
        sum(values[i:i + period]) / period
        for i in range(len(values) - period + 1)
    ]


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float]:
    """Average True Range."""
    if len(highs) < period + 1:
        return []

    true_ranges = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return []

    atr_values = [sum(true_ranges[:period]) / period]
    for i in range(period, len(true_ranges)):
        atr_val = (atr_values[-1] * (period - 1) + true_ranges[i]) / period
        atr_values.append(atr_val)

    return atr_values


def _bollinger_width(closes: list[float], period: int, std_mult: float) -> list[float]:
    """Bollinger Band width (upper - lower) / middle."""
    if len(closes) < period:
        return []

    widths = []
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        sma = sum(window) / period
        if sma == 0:
            widths.append(0)
            continue
        std = math.sqrt(sum((x - sma) ** 2 for x in window) / period)
        width = (2 * std_mult * std) / sma  # Normalized width
        widths.append(width)

    return widths


def _calculate_adx_value(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float:
    """Calculate current ADX value (returns single float)."""
    n = len(highs)
    if n < period * 2 + 1:
        return 15.0  # Default to "no trend"

    # +DM, -DM, TR
    plus_dm = []
    minus_dm = []
    true_ranges = []

    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        true_ranges.append(tr)

    if len(plus_dm) < period:
        return 15.0

    # Wilder's smoothing
    s_pdm = sum(plus_dm[:period])
    s_mdm = sum(minus_dm[:period])
    s_tr = sum(true_ranges[:period])

    dx_values = []
    for i in range(period, len(plus_dm)):
        s_pdm = s_pdm - (s_pdm / period) + plus_dm[i]
        s_mdm = s_mdm - (s_mdm / period) + minus_dm[i]
        s_tr = s_tr - (s_tr / period) + true_ranges[i]

        pdi = (s_pdm / s_tr * 100) if s_tr > 0 else 0
        mdi = (s_mdm / s_tr * 100) if s_tr > 0 else 0
        di_sum = pdi + mdi
        dx = (abs(pdi - mdi) / di_sum * 100) if di_sum > 0 else 0
        dx_values.append(dx)

    if len(dx_values) < period:
        return 15.0

    # Smooth DX → ADX
    adx = sum(dx_values[:period]) / period
    for i in range(period, len(dx_values)):
        adx = (adx * (period - 1) + dx_values[i]) / period

    return adx
