"""
Insight Skills — Cross-Agent Intelligence Tools

Tools that let agents query other agents' published insights
during their reasoning loop. These are registered for all
analyst roles and the Judge.

When an analyst is analyzing a ticker, it can call `get_current_regime()`
to see if the Macro Analyst has detected a regime change, or
`get_active_signals()` to see what other analysts have found.

The Judge uses `get_active_signals()` + `get_risk_alerts()` to make
fully informed decisions backed by the entire team's intelligence.
"""

from typing import Dict, Any, List, Optional

from agents.skills.validator import skill


def _get_publisher():
    """Lazy-load the InsightPublisher singleton."""
    from core.insight_publisher import insight_publisher
    return insight_publisher


# ═══════════════════════════════════════════════════════════════════
# REGIME TOOLS — All analysts need regime awareness
# ═══════════════════════════════════════════════════════════════════


@skill("technical_analyst")
def get_current_regime_for_ta() -> Dict[str, Any]:
    """
    Get the current market regime classification from the Macro Analyst.
    Use this BEFORE starting your technical analysis to adjust your
    approach based on the macro environment.

    Returns:
        Dict with regime info (type, description, confidence) or
        a message that no regime data is available.
    """
    return _get_regime()


@skill("fundamental_analyst")
def get_current_regime_for_fa() -> Dict[str, Any]:
    """
    Get the current market regime from the Macro Analyst.
    Use this to contextualize your fundamental analysis
    (e.g., growth stocks perform differently in BULL vs BEAR regimes).

    Returns:
        Dict with regime info or message that no data is available.
    """
    return _get_regime()


@skill("sentiment_analyst")
def get_current_regime_for_sa() -> Dict[str, Any]:
    """
    Get the current market regime from the Macro Analyst.
    Sentiment interpretation varies by regime — use this for context.

    Returns:
        Dict with regime info or message that no data is available.
    """
    return _get_regime()


@skill("judge")
def get_current_regime_for_judge() -> Dict[str, Any]:
    """
    Get the current market regime classification.
    Factor this into your trade decision — risk appetite
    should decrease in BEAR/PANIC regimes.

    Returns:
        Dict with regime info (type, confidence, description).
    """
    return _get_regime()


def _get_regime() -> Dict[str, Any]:
    """Internal: fetch latest regime insight."""
    pub = _get_publisher()
    regime = pub.get_active_regime()

    if regime is None:
        return {
            "regime": "UNKNOWN",
            "confidence": 0.0,
            "description": "No regime data available. The Macro Analyst has not published a regime classification yet.",
            "available": False,
        }

    return {
        "regime": regime.data.get("regime", regime.data.get("new_regime", "UNKNOWN")),
        "confidence": regime.confidence,
        "description": regime.description[:300],
        "source": regime.source_agent,
        "age_minutes": round(regime.age_minutes, 1),
        "data": regime.data,
        "available": True,
    }


# ═══════════════════════════════════════════════════════════════════
# SIGNAL TOOLS — Judge needs full team intelligence
# ═══════════════════════════════════════════════════════════════════


@skill("judge")
def get_active_signals(
    ticker: str = "",
    max_age_minutes: int = 60,
) -> Dict[str, Any]:
    """
    Get all active analysis signals from ALL agents for a given ticker.
    Use this to see what the full analyst team has found before
    making your BUY/PASS decision.

    Args:
        ticker: Ticker to filter for. Leave empty for all tickers.
        max_age_minutes: Maximum age of signals to include (default 60).

    Returns:
        Dict with signals list, regime info, and summary statistics.
    """
    pub = _get_publisher()

    ticker_filter = ticker.upper().strip() if ticker else None
    signals = pub.get_all_active_signals(
        ticker=ticker_filter,
        max_age_minutes=max_age_minutes,
    )

    if not signals:
        return {
            "signals_found": 0,
            "signals": [],
            "summary": "No active signals from the analyst team.",
        }

    formatted = []
    bullish_count = 0
    bearish_count = 0

    for s in signals:
        entry = {
            "source": s.source_agent,
            "type": s.insight_type.value,
            "ticker": s.ticker,
            "title": s.title,
            "description": s.description[:200],
            "confidence": s.confidence,
            "urgency": s.urgency.value,
            "age_minutes": round(s.age_minutes, 1),
        }
        formatted.append(entry)

        # Count sentiment direction from data
        direction = s.data.get("direction", s.data.get("signal", ""))
        if direction in ("BULLISH", "BUY", "LONG", "bullish"):
            bullish_count += 1
        elif direction in ("BEARISH", "SELL", "SHORT", "bearish"):
            bearish_count += 1

    return {
        "signals_found": len(formatted),
        "bullish_signals": bullish_count,
        "bearish_signals": bearish_count,
        "signals": formatted,
        "summary": (
            f"Team published {len(formatted)} active signals. "
            f"Bullish: {bullish_count}, Bearish: {bearish_count}."
        ),
    }


@skill("judge")
def get_risk_alerts() -> Dict[str, Any]:
    """
    Get all active risk and compliance alerts before making a trade decision.
    If there are CRITICAL alerts, strongly consider PASSING on the trade.

    Returns:
        Dict with active risk alerts and their urgency levels.
    """
    pub = _get_publisher()
    alerts = pub.get_risk_alerts(max_age_minutes=120)

    if not alerts:
        return {
            "alerts_found": 0,
            "alerts": [],
            "has_critical": False,
            "summary": "No active risk alerts. Clear to trade.",
        }

    formatted = []
    has_critical = False

    for a in alerts:
        formatted.append({
            "source": a.source_agent,
            "type": a.insight_type.value,
            "title": a.title,
            "description": a.description[:200],
            "urgency": a.urgency.value,
            "age_minutes": round(a.age_minutes, 1),
        })
        if a.urgency == "CRITICAL":
            has_critical = True

    return {
        "alerts_found": len(formatted),
        "alerts": formatted,
        "has_critical": has_critical,
        "summary": (
            f"{len(formatted)} active risk alert(s). "
            + ("⚠️ CRITICAL alert present — consider PASSING." if has_critical else "No critical alerts.")
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# CROSS-ANALYST TOOLS — See what other analysts found
# ═══════════════════════════════════════════════════════════════════


@skill("technical_analyst")
def get_fundamental_flags(ticker: str = "") -> Dict[str, Any]:
    """
    Check if the Fundamental Analyst has flagged anything on this ticker.
    Use this to see if there are earnings surprises or valuation extremes
    that should inform your technical analysis.

    Args:
        ticker: Ticker to check. Leave empty for all.

    Returns:
        Dict with any active fundamental flags.
    """
    return _get_insights_by_type("FUNDAMENTAL_FLAG", "FUNDAMENTAL_ANALYST", ticker)


@skill("technical_analyst")
def get_sentiment_alerts_for_ta(ticker: str = "") -> Dict[str, Any]:
    """
    Check if the Sentiment Analyst has detected any divergences.
    Price-sentiment divergence can signal reversals.

    Args:
        ticker: Ticker to check.

    Returns:
        Dict with sentiment divergence alerts.
    """
    return _get_insights_by_type("SENTIMENT_DIVERGENCE", "SENTIMENT_ANALYST", ticker)


@skill("fundamental_analyst")
def get_technical_signals_for_fa(ticker: str = "") -> Dict[str, Any]:
    """
    Check if the Technical Analyst has detected any patterns.
    Technical breakouts/breakdowns can validate or invalidate
    your fundamental thesis.

    Args:
        ticker: Ticker to check.

    Returns:
        Dict with technical signal alerts.
    """
    return _get_insights_by_type("TECHNICAL_SIGNAL", "TECHNICAL_ANALYST", ticker)


@skill("sentiment_analyst")
def get_technical_signals_for_sa(ticker: str = "") -> Dict[str, Any]:
    """
    Check if the Technical Analyst has detected any patterns.
    If price is breaking out but sentiment is negative, that's
    a significant divergence signal.

    Args:
        ticker: Ticker to check.

    Returns:
        Dict with technical signal data.
    """
    return _get_insights_by_type("TECHNICAL_SIGNAL", "TECHNICAL_ANALYST", ticker)


def _get_insights_by_type(
    insight_type_str: str,
    source_agent: str,
    ticker: str,
) -> Dict[str, Any]:
    """Internal helper to fetch insights by type and source."""
    from core.models.insights import InsightType
    pub = _get_publisher()

    try:
        itype = InsightType(insight_type_str)
    except ValueError:
        return {"error": f"Unknown insight type: {insight_type_str}"}

    ticker_filter = ticker.upper().strip() if ticker else None
    insights = pub.get_recent_insights(
        insight_type=itype,
        source_agent=source_agent,
        ticker=ticker_filter,
        max_age_minutes=120,
        limit=5,
    )

    if not insights:
        return {
            "found": 0,
            "insights": [],
            "summary": f"No active {insight_type_str} insights from {source_agent}.",
        }

    formatted = []
    for ins in insights:
        formatted.append({
            "title": ins.title,
            "description": ins.description[:200],
            "confidence": ins.confidence,
            "ticker": ins.ticker,
            "age_minutes": round(ins.age_minutes, 1),
            "data": ins.data,
        })

    return {
        "found": len(formatted),
        "insights": formatted,
        "summary": f"{len(formatted)} active {insight_type_str} insight(s) from {source_agent}.",
    }
