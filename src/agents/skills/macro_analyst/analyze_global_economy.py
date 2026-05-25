"""
Macro Analyst — Real Economic Analysis Tools

Production-grade macroeconomic analysis tools that compute real metrics
from economic data. These replace stub implementations.

All functions are deterministic (no LLM) — they compute from data.
"""

from typing import Dict, Any, List, Optional
import logging

from agents.skills.validator import skill

logger = logging.getLogger(__name__)


@skill("macro_analyst")
def analyze_yield_curve(
    short_rate: float,
    mid_rate: float,
    long_rate: float,
    previous_short: Optional[float] = None,
    previous_long: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Analyze the yield curve shape for recession/expansion signals.
    An inverted yield curve (short > long) has historically preceded recessions.

    Args:
        short_rate: 2-year Treasury yield (e.g., 4.5 for 4.5%).
        mid_rate: 5-year or 10-year Treasury yield.
        long_rate: 30-year Treasury yield.
        previous_short: Previous period 2Y yield (for trend detection).
        previous_long: Previous period 30Y yield (for trend detection).

    Returns:
        Dict with curve_shape, spread, recession_signal, and interpretation.
    """
    spread_2_30 = round(long_rate - short_rate, 4)
    spread_2_10 = round(mid_rate - short_rate, 4)

    # Determine shape
    if spread_2_30 < -0.1:
        curve_shape = "inverted"
        recession_signal = True
        risk_level = "HIGH"
    elif spread_2_30 < 0.1:
        curve_shape = "flat"
        recession_signal = False
        risk_level = "ELEVATED"
    elif spread_2_30 < 1.0:
        curve_shape = "normal_shallow"
        recession_signal = False
        risk_level = "MODERATE"
    else:
        curve_shape = "normal_steep"
        recession_signal = False
        risk_level = "LOW"

    # Trend detection
    trend = "stable"
    if previous_short is not None and previous_long is not None:
        prev_spread = previous_long - previous_short
        spread_change = spread_2_30 - prev_spread
        if spread_change > 0.1:
            trend = "steepening"
        elif spread_change < -0.1:
            trend = "flattening"

    interpretation = (
        f"Yield Curve: {curve_shape} (2Y={short_rate}%, 10Y={mid_rate}%, 30Y={long_rate}%). "
        f"2Y-30Y spread: {spread_2_30}%. "
        f"Recession signal: {'YES' if recession_signal else 'NO'}. "
        f"Trend: {trend}."
    )

    return {
        "curve_shape": curve_shape,
        "spread_2_30": spread_2_30,
        "spread_2_10": spread_2_10,
        "recession_signal": recession_signal,
        "risk_level": risk_level,
        "trend": trend,
        "interpretation": interpretation,
    }


@skill("macro_analyst")
def analyze_economic_indicators(
    gdp_growth: float,
    inflation_rate: float,
    unemployment_rate: float,
    fed_funds_rate: float,
    consumer_confidence: Optional[float] = None,
    pmi_manufacturing: Optional[float] = None,
    pmi_services: Optional[float] = None,
    housing_starts: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Analyze key economic indicators to determine the current economic regime.
    Categorizes the regime as: EXPANSION, LATE_CYCLE, CONTRACTION, RECOVERY.

    Args:
        gdp_growth: GDP growth rate (annualized, e.g., 2.5 for 2.5%).
        inflation_rate: CPI inflation rate (YoY, e.g., 3.2 for 3.2%).
        unemployment_rate: Unemployment rate (e.g., 3.7 for 3.7%).
        fed_funds_rate: Federal funds rate (e.g., 5.25 for 5.25%).
        consumer_confidence: Consumer confidence index (optional, ~100 = neutral).
        pmi_manufacturing: Manufacturing PMI (optional, >50 = expansion).
        pmi_services: Services PMI (optional, >50 = expansion).
        housing_starts: Housing starts change YoY % (optional).

    Returns:
        Dict with economic_regime, risk_score, position_size_modifier, and per-indicator analysis.
    """
    score = 0
    signals = []

    # GDP analysis
    if gdp_growth > 3.0:
        score += 2
        signals.append(f"Strong GDP growth ({gdp_growth}%)")
    elif gdp_growth > 1.5:
        score += 1
        signals.append(f"Moderate GDP growth ({gdp_growth}%)")
    elif gdp_growth > 0:
        signals.append(f"Weak GDP growth ({gdp_growth}%)")
    else:
        score -= 3
        signals.append(f"Negative GDP ({gdp_growth}%) — contraction")

    # Inflation analysis
    if inflation_rate <= 2.5:
        score += 1
        signals.append(f"Inflation at target ({inflation_rate}%)")
    elif inflation_rate <= 4.0:
        signals.append(f"Elevated inflation ({inflation_rate}%)")
    elif inflation_rate <= 6.0:
        score -= 1
        signals.append(f"High inflation ({inflation_rate}%)")
    else:
        score -= 2
        signals.append(f"Very high inflation ({inflation_rate}%) — tightening likely")

    # Unemployment analysis
    if unemployment_rate < 4.0:
        score += 1
        signals.append(f"Low unemployment ({unemployment_rate}%) — tight labor market")
    elif unemployment_rate < 5.5:
        signals.append(f"Normal unemployment ({unemployment_rate}%)")
    else:
        score -= 2
        signals.append(f"Elevated unemployment ({unemployment_rate}%)")

    # Fed policy stance
    real_rate = fed_funds_rate - inflation_rate
    if real_rate > 2.0:
        score -= 1
        signals.append(f"Restrictive policy (real rate {real_rate:.1f}%)")
    elif real_rate > 0:
        signals.append(f"Neutral-to-tight policy (real rate {real_rate:.1f}%)")
    else:
        score += 1
        signals.append(f"Accommodative policy (real rate {real_rate:.1f}%)")

    # PMI analysis
    if pmi_manufacturing is not None:
        if pmi_manufacturing > 55:
            score += 1
            signals.append(f"Manufacturing expanding strongly (PMI={pmi_manufacturing})")
        elif pmi_manufacturing > 50:
            signals.append(f"Manufacturing expanding (PMI={pmi_manufacturing})")
        else:
            score -= 1
            signals.append(f"Manufacturing contracting (PMI={pmi_manufacturing})")

    if pmi_services is not None:
        if pmi_services > 55:
            score += 1
        elif pmi_services < 50:
            score -= 1

    # Consumer confidence
    if consumer_confidence is not None:
        if consumer_confidence > 110:
            score += 1
        elif consumer_confidence < 80:
            score -= 1

    # Determine regime
    if score >= 4:
        regime = "EXPANSION"
        position_modifier = 1.0
    elif score >= 1:
        regime = "LATE_CYCLE"
        position_modifier = 0.7
    elif score >= -2:
        regime = "RECOVERY"
        position_modifier = 0.8
    else:
        regime = "CONTRACTION"
        position_modifier = 0.3

    # Risk score (0 = safe, 100 = dangerous)
    risk_score = max(0, min(100, 50 - score * 10))

    interpretation = (
        f"Economic Regime: {regime}. Risk Score: {risk_score}/100. "
        f"Position Size Modifier: {position_modifier:.1f}x. "
        f"Key: GDP {gdp_growth}%, Inflation {inflation_rate}%, "
        f"Unemployment {unemployment_rate}%, Fed {fed_funds_rate}%."
    )

    return {
        "economic_regime": regime,
        "composite_score": score,
        "risk_score": risk_score,
        "position_size_modifier": position_modifier,
        "signals": signals,
        "indicators": {
            "gdp_growth": gdp_growth,
            "inflation_rate": inflation_rate,
            "unemployment_rate": unemployment_rate,
            "fed_funds_rate": fed_funds_rate,
            "real_rate": round(real_rate, 2),
            "pmi_manufacturing": pmi_manufacturing,
            "pmi_services": pmi_services,
            "consumer_confidence": consumer_confidence,
        },
        "interpretation": interpretation,
    }


@skill("macro_analyst")
def compute_market_regime(
    vix_level: float,
    market_return_30d: float,
    breadth_ratio: float,
    correlation_avg: float = 0.5,
) -> Dict[str, Any]:
    """
    Determine the current market regime from volatility and breadth data.
    The regime directly affects position sizing and strategy selection.

    Args:
        vix_level: Current VIX index level (10-80 typical range).
        market_return_30d: S&P 500 30-day return (e.g., -0.05 for -5%).
        breadth_ratio: Advance/Decline ratio (>1 = more advancers).
        correlation_avg: Average pairwise correlation of market stocks (0-1).

    Returns:
        Dict with regime (RISK_ON, NORMAL, RISK_OFF, PANIC), confidence, and sizing guidance.
    """
    # VIX regime classification
    if vix_level < 15:
        vix_regime = "complacent"
        vix_score = 2
    elif vix_level < 20:
        vix_regime = "normal"
        vix_score = 1
    elif vix_level < 30:
        vix_regime = "elevated"
        vix_score = -1
    elif vix_level < 40:
        vix_regime = "high"
        vix_score = -2
    else:
        vix_regime = "extreme"
        vix_score = -3

    # Market return regime
    if market_return_30d > 0.05:
        return_score = 2
    elif market_return_30d > 0.01:
        return_score = 1
    elif market_return_30d > -0.03:
        return_score = 0
    elif market_return_30d > -0.10:
        return_score = -2
    else:
        return_score = -3

    # Breadth score
    if breadth_ratio > 2.0:
        breadth_score = 2
    elif breadth_ratio > 1.2:
        breadth_score = 1
    elif breadth_ratio > 0.8:
        breadth_score = 0
    else:
        breadth_score = -2

    # Correlation score (high correlation = crisis mode)
    if correlation_avg > 0.8:
        corr_score = -2  # Everything moving together = crisis
    elif correlation_avg > 0.6:
        corr_score = -1
    else:
        corr_score = 1

    composite = vix_score + return_score + breadth_score + corr_score

    if composite >= 4:
        regime = "RISK_ON"
        max_position_pct = 1.0
        max_strategies = 5
    elif composite >= 0:
        regime = "NORMAL"
        max_position_pct = 0.7
        max_strategies = 4
    elif composite >= -4:
        regime = "RISK_OFF"
        max_position_pct = 0.4
        max_strategies = 2
    else:
        regime = "PANIC"
        max_position_pct = 0.0
        max_strategies = 0

    confidence = min(1.0, abs(composite) / 6.0)

    return {
        "regime": regime,
        "composite_score": composite,
        "confidence": round(confidence, 2),
        "max_position_pct": max_position_pct,
        "max_active_strategies": max_strategies,
        "components": {
            "vix": {"level": vix_level, "label": vix_regime, "score": vix_score},
            "returns": {"value": market_return_30d, "score": return_score},
            "breadth": {"ratio": breadth_ratio, "score": breadth_score},
            "correlation": {"avg": correlation_avg, "score": corr_score},
        },
        "interpretation": (
            f"Market Regime: {regime} (score={composite}, confidence={confidence:.0%}). "
            f"VIX={vix_level} ({vix_regime}), 30d return={market_return_30d:+.1%}, "
            f"breadth={breadth_ratio:.2f}. Max position: {max_position_pct:.0%}."
        ),
    }
