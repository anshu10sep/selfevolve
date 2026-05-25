"""
Sentiment Analyst — Real Sentiment Analysis Tools

Production-grade sentiment analysis using keyword scoring, linguistic patterns,
and configurable sentiment lexicons. These replace stub implementations.

For production, these can be enhanced with:
- Alpaca News API integration (fetch_news already in broker/alpaca_client.py)
- FinBERT or distilled transformers for ML-based sentiment
- Social media API integration

All functions are deterministic (no LLM) — they compute from text data.
"""

from typing import Dict, Any, List, Optional
import re
import logging
from collections import Counter

from agents.skills.validator import skill

logger = logging.getLogger(__name__)

# ── Sentiment Lexicons (Financial-Domain) ────────────────────────

BULLISH_WORDS = {
    "beat", "beats", "exceeds", "exceeded", "strong", "surge", "surged",
    "soar", "soared", "rally", "rallied", "growth", "upgrade", "upgraded",
    "buy", "outperform", "bullish", "positive", "profit", "profitability",
    "revenue growth", "expansion", "record", "breakthrough", "innovative",
    "accelerate", "momentum", "optimistic", "dividend", "buyback",
    "acquisition", "partnership", "deal", "milestone", "upside",
    "recovery", "rebound", "improved", "improving", "beat expectations",
}

BEARISH_WORDS = {
    "miss", "missed", "misses", "below", "weak", "decline", "declined",
    "plunge", "plunged", "crash", "sell", "selloff", "bearish", "negative",
    "loss", "losses", "downgrade", "downgraded", "underperform", "warning",
    "recession", "layoff", "layoffs", "restructuring", "bankruptcy",
    "default", "fraud", "investigation", "lawsuit", "subpoena",
    "regulatory", "fine", "penalty", "deteriorating", "disappointing",
    "shortfall", "guidance cut", "downside", "risk", "concern",
}

UNCERTAINTY_WORDS = {
    "uncertain", "uncertainty", "volatile", "volatility", "unpredictable",
    "cautious", "mixed", "flat", "unchanged", "pending", "tbd",
    "under review", "reassessing", "reevaluating", "unclear",
}

URGENCY_WORDS = {
    "breaking", "urgent", "alert", "flash", "emergency",
    "halt", "halted", "suspended", "immediate", "critical",
}


@skill("sentiment_analyst")
def analyze_news_sentiment(headlines: List[str]) -> Dict[str, Any]:
    """
    Analyze a list of news headlines/articles for financial sentiment.
    Uses a financial-domain sentiment lexicon with weighted scoring.

    Args:
        headlines: List of news headline or article text strings.

    Returns:
        Dict with sentiment_score (-1.0 to 1.0), dominant_sentiment, confidence,
        bullish/bearish word counts, and per-article breakdown.
    """
    if not headlines:
        return {
            "sentiment_score": 0.0,
            "dominant_sentiment": "no_data",
            "confidence": 0.0,
            "article_count": 0,
            "interpretation": "No headlines provided.",
        }

    total_bull = 0
    total_bear = 0
    total_uncertain = 0
    total_urgent = 0
    article_sentiments = []

    for headline in headlines:
        text_lower = headline.lower()
        words = set(re.findall(r'\b\w+\b', text_lower))
        bigrams = set()
        word_list = re.findall(r'\b\w+\b', text_lower)
        for i in range(len(word_list) - 1):
            bigrams.add(f"{word_list[i]} {word_list[i+1]}")

        all_tokens = words | bigrams

        bull_count = len(all_tokens & BULLISH_WORDS)
        bear_count = len(all_tokens & BEARISH_WORDS)
        unc_count = len(all_tokens & UNCERTAINTY_WORDS)
        urg_count = len(all_tokens & URGENCY_WORDS)

        total_bull += bull_count
        total_bear += bear_count
        total_uncertain += unc_count
        total_urgent += urg_count

        # Per-article score
        total_signals = bull_count + bear_count
        if total_signals > 0:
            art_score = round((bull_count - bear_count) / total_signals, 3)
        else:
            art_score = 0.0

        article_sentiments.append({
            "headline": headline[:100],
            "score": art_score,
            "bullish_signals": bull_count,
            "bearish_signals": bear_count,
        })

    # Aggregate score
    total_signals = total_bull + total_bear
    if total_signals > 0:
        sentiment_score = round((total_bull - total_bear) / total_signals, 3)
    else:
        sentiment_score = 0.0

    # Confidence based on signal density
    signals_per_article = total_signals / len(headlines)
    confidence = min(1.0, round(signals_per_article / 3.0, 2))  # 3+ signals per article = full confidence

    # Determine dominant sentiment
    if sentiment_score > 0.2:
        dominant = "bullish"
    elif sentiment_score < -0.2:
        dominant = "bearish"
    else:
        dominant = "neutral"

    # Urgency modifier
    if total_urgent > 0:
        dominant = f"urgent_{dominant}"

    interpretation = (
        f"Analyzed {len(headlines)} headlines. "
        f"Score: {sentiment_score:+.3f} ({dominant}). "
        f"Bullish signals: {total_bull}, Bearish: {total_bear}, "
        f"Uncertain: {total_uncertain}. Confidence: {confidence:.0%}."
    )

    return {
        "sentiment_score": sentiment_score,
        "dominant_sentiment": dominant,
        "confidence": confidence,
        "bullish_count": total_bull,
        "bearish_count": total_bear,
        "uncertainty_count": total_uncertain,
        "urgency_count": total_urgent,
        "article_count": len(headlines),
        "top_articles": sorted(article_sentiments, key=lambda x: abs(x["score"]), reverse=True)[:5],
        "interpretation": interpretation,
    }


@skill("sentiment_analyst")
def compute_fear_greed_score(
    price_change_1d: float,
    price_change_5d: float,
    price_change_30d: float,
    volume_ratio: float,
    vix_level: Optional[float] = None,
    put_call_ratio: Optional[float] = None,
    new_highs: int = 0,
    new_lows: int = 0,
) -> Dict[str, Any]:
    """
    Compute a Fear & Greed composite score from market data.
    Inspired by CNN's Fear & Greed Index, adapted for individual stocks.

    Args:
        price_change_1d: 1-day price change percentage (e.g., 0.02 for +2%).
        price_change_5d: 5-day price change percentage.
        price_change_30d: 30-day price change percentage.
        volume_ratio: Current volume / 20-day average volume.
        vix_level: VIX index level (optional, 10-80 range typical).
        put_call_ratio: Put/Call ratio (optional, <0.7 = greedy, >1.0 = fearful).
        new_highs: Number of new 52-week highs in the market.
        new_lows: Number of new 52-week lows in the market.

    Returns:
        Dict with fear_greed_score (0-100), label, component scores, and interpretation.
    """
    components = {}

    # 1. Momentum (short-term price action) — 0 to 100
    momentum = min(100, max(0, 50 + price_change_1d * 500))
    components["momentum"] = round(momentum)

    # 2. Trend strength (medium-term) — 0 to 100
    trend = min(100, max(0, 50 + price_change_30d * 200))
    components["trend_strength"] = round(trend)

    # 3. Volume conviction — 0 to 100
    vol_score = min(100, max(0, volume_ratio * 50))
    if price_change_1d > 0:
        vol_score = min(100, vol_score * 1.2)  # High volume + up = greedy
    else:
        vol_score = max(0, 100 - vol_score * 1.2)  # High volume + down = fearful
    components["volume"] = round(vol_score)

    # 4. Market breadth (if highs/lows available) — 0 to 100
    total_hl = new_highs + new_lows
    if total_hl > 0:
        breadth = round((new_highs / total_hl) * 100)
    else:
        breadth = 50
    components["market_breadth"] = breadth

    # 5. VIX fear gauge (if available) — 0 to 100
    if vix_level is not None:
        # VIX 10 = extreme greed (100), VIX 30 = extreme fear (0)
        vix_score = max(0, min(100, round(100 - (vix_level - 10) * (100 / 20))))
        components["vix"] = vix_score
    else:
        vix_score = 50  # Neutral default

    # 6. Put/Call ratio (if available)
    if put_call_ratio is not None:
        # <0.7 = greedy, 0.85 = neutral, >1.0 = fearful
        pcr_score = max(0, min(100, round(100 - (put_call_ratio - 0.5) * 200)))
        components["put_call_ratio"] = pcr_score
    else:
        pcr_score = 50

    # Composite score (weighted average)
    weights = {
        "momentum": 0.20,
        "trend_strength": 0.20,
        "volume": 0.15,
        "market_breadth": 0.15,
        "vix": 0.15,
        "put_call_ratio": 0.15,
    }

    scores = [momentum, trend, vol_score, breadth, vix_score, pcr_score]
    weight_vals = list(weights.values())
    composite = round(sum(s * w for s, w in zip(scores, weight_vals)))

    # Label
    if composite >= 80:
        label = "EXTREME_GREED"
    elif composite >= 60:
        label = "GREED"
    elif composite >= 40:
        label = "NEUTRAL"
    elif composite >= 20:
        label = "FEAR"
    else:
        label = "EXTREME_FEAR"

    interpretation = (
        f"Fear & Greed Score: {composite}/100 ({label}). "
        f"Momentum: {components.get('momentum')}, "
        f"Trend: {components.get('trend_strength')}, "
        f"Volume: {components.get('volume')}."
    )

    return {
        "fear_greed_score": composite,
        "label": label,
        "components": components,
        "interpretation": interpretation,
    }


@skill("sentiment_analyst")
def detect_sentiment_divergence(
    price_change: float,
    sentiment_score: float,
    volume_ratio: float,
) -> Dict[str, Any]:
    """
    Detect divergence between price action and market sentiment.
    Divergences often precede reversals (e.g., prices rising but sentiment turning negative).

    Args:
        price_change: Recent price change percentage (e.g., 0.05 for +5%).
        sentiment_score: Current news sentiment score (-1.0 to 1.0).
        volume_ratio: Current volume / average volume ratio.

    Returns:
        Dict with divergence_detected, type, strength, and interpretation.
    """
    price_bullish = price_change > 0.01
    price_bearish = price_change < -0.01
    sentiment_bullish = sentiment_score > 0.2
    sentiment_bearish = sentiment_score < -0.2

    divergence_detected = False
    divergence_type = "none"
    strength = "weak"

    if price_bullish and sentiment_bearish:
        divergence_detected = True
        divergence_type = "bearish_divergence"
        interpretation = (
            f"BEARISH DIVERGENCE: Price rising ({price_change:+.1%}) but sentiment "
            f"is negative ({sentiment_score:+.3f}). Price may reverse down."
        )
    elif price_bearish and sentiment_bullish:
        divergence_detected = True
        divergence_type = "bullish_divergence"
        interpretation = (
            f"BULLISH DIVERGENCE: Price falling ({price_change:+.1%}) but sentiment "
            f"is positive ({sentiment_score:+.3f}). Price may reverse up."
        )
    else:
        interpretation = (
            f"No divergence detected. Price ({price_change:+.1%}) and sentiment "
            f"({sentiment_score:+.3f}) are aligned."
        )

    # Strength based on volume confirmation
    if divergence_detected:
        if volume_ratio > 1.5:
            strength = "strong"
        elif volume_ratio > 1.0:
            strength = "moderate"
        else:
            strength = "weak"

    return {
        "divergence_detected": divergence_detected,
        "divergence_type": divergence_type,
        "strength": strength,
        "price_change": price_change,
        "sentiment_score": sentiment_score,
        "volume_ratio": volume_ratio,
        "interpretation": interpretation,
    }
