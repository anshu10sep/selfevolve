"""
Memory Tools — Shared Agent Memory Access

Production-grade tools that give agents access to the VectorStore
for reflexive learning. Registered for all analyst roles so every
agent can recall past lessons and store new ones.

These tools bridge the gap between the evolution pipeline (which
generates post-mortems) and the analysis loop (where agents make
predictions). By recalling past mistakes, agents avoid repeating
them — this is the core of the self-evolution thesis.
"""

from typing import Dict, Any, List, Optional
import logging

from agents.skills.validator import skill

logger = logging.getLogger(__name__)


def _get_store():
    """Lazy-load the VectorStore singleton."""
    from memory.vector_store import get_vector_store
    return get_vector_store()


# ═══════════════════════════════════════════════════════════════════
# RECALL TOOLS — Read from vector store
# ═══════════════════════════════════════════════════════════════════


@skill("technical_analyst")
def recall_technical_lessons(
    query: str,
    market_regime: str = "",
    limit: int = 3,
) -> Dict[str, Any]:
    """
    Recall past lessons from the Technical Analyst's trade post-mortems.
    Use this before making a prediction to check if you've made similar
    mistakes before.

    Args:
        query: Natural language description of the current setup (e.g., "RSI overbought with declining volume on AAPL")
        market_regime: Filter by market regime (BULL, BEAR, SIDEWAYS, PANIC). Leave empty for all.
        limit: Maximum number of lessons to retrieve (default 3).

    Returns:
        Dict with lessons (list of past post-mortems with relevance scores).
    """
    import asyncio
    store = _get_store()

    filters = {"agent_role": "TECHNICAL_ANALYST"}
    if market_regime:
        filters["market_regime"] = market_regime

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — use a synchronous fallback
            results = store._fallback_search("reflexion_memory", filters, limit)
        else:
            results = loop.run_until_complete(
                store.retrieve_relevant(query, metadata_filters=filters, limit=limit)
            )
    except Exception as e:
        logger.warning(f"recall_technical_lessons failed: {e}")
        results = []

    if not results:
        return {
            "lessons_found": 0,
            "lessons": [],
            "interpretation": "No past lessons found for this query. Proceed with fresh analysis.",
        }

    lessons = []
    for r in results:
        lessons.append({
            "lesson": r.get("text", "")[:300],
            "relevance_score": round(r.get("score", 0), 3),
            "regime": r.get("metadata", {}).get("market_regime", "unknown"),
            "brier_score": r.get("metadata", {}).get("brier_score"),
        })

    return {
        "lessons_found": len(lessons),
        "lessons": lessons,
        "interpretation": f"Found {len(lessons)} relevant past lessons. Review them before making your prediction.",
    }


@skill("fundamental_analyst")
def recall_fundamental_lessons(
    query: str,
    market_regime: str = "",
    limit: int = 3,
) -> Dict[str, Any]:
    """
    Recall past lessons from the Fundamental Analyst's trade post-mortems.
    Use this to check for biases in your financial analysis approach.

    Args:
        query: Description of current analysis (e.g., "high P/E growth stock with declining margins")
        market_regime: Filter by market regime. Leave empty for all.
        limit: Maximum lessons to retrieve (default 3).

    Returns:
        Dict with lessons from past fundamental analysis post-mortems.
    """
    import asyncio
    store = _get_store()

    filters = {"agent_role": "FUNDAMENTAL_ANALYST"}
    if market_regime:
        filters["market_regime"] = market_regime

    try:
        results = store._fallback_search("reflexion_memory", filters, limit)
    except Exception:
        results = []

    return _format_lessons(results, "Fundamental")


@skill("sentiment_analyst")
def recall_sentiment_lessons(
    query: str,
    market_regime: str = "",
    limit: int = 3,
) -> Dict[str, Any]:
    """
    Recall past lessons from the Sentiment Analyst's trade post-mortems.
    Use this to avoid repeating sentiment analysis mistakes.

    Args:
        query: Description of current sentiment (e.g., "bullish news but price declining")
        market_regime: Filter by market regime. Leave empty for all.
        limit: Maximum lessons to retrieve (default 3).

    Returns:
        Dict with lessons from past sentiment analysis post-mortems.
    """
    import asyncio
    store = _get_store()

    filters = {"agent_role": "SENTIMENT_ANALYST"}
    if market_regime:
        filters["market_regime"] = market_regime

    try:
        results = store._fallback_search("reflexion_memory", filters, limit)
    except Exception:
        results = []

    return _format_lessons(results, "Sentiment")


@skill("macro_analyst")
def recall_macro_lessons(
    query: str,
    market_regime: str = "",
    limit: int = 3,
) -> Dict[str, Any]:
    """
    Recall past lessons from the Macro Analyst's trade post-mortems.
    Use this to review how past macro calls performed.

    Args:
        query: Description of current macro setup (e.g., "inverted yield curve with rising unemployment")
        market_regime: Filter by market regime. Leave empty for all.
        limit: Maximum lessons to retrieve (default 3).

    Returns:
        Dict with lessons from past macro analysis post-mortems.
    """
    import asyncio
    store = _get_store()

    filters = {"agent_role": "MACRO_ANALYST"}
    if market_regime:
        filters["market_regime"] = market_regime

    try:
        results = store._fallback_search("reflexion_memory", filters, limit)
    except Exception:
        results = []

    return _format_lessons(results, "Macro")


# ═══════════════════════════════════════════════════════════════════
# CROSS-AGENT RECALL — Read from trade_context collection
# ═══════════════════════════════════════════════════════════════════


@skill("judge")
def recall_similar_trades(
    query: str,
    market_regime: str = "",
    outcome: str = "",
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Recall similar past trade decisions and their outcomes.
    Use this to check how the team performed on similar setups.
    Available to the Judge for historical pattern matching.

    Args:
        query: Description of current trade setup (e.g., "AAPL BUY with high conviction in bull market")
        market_regime: Filter by regime (BULL, BEAR, RISK_OFF, PANIC). Leave empty for all.
        outcome: Filter by outcome (win, loss). Leave empty for all.
        limit: Maximum results (default 5).

    Returns:
        Dict with past trade decisions, team scores, and outcomes.
    """
    import asyncio
    store = _get_store()

    filters = {}
    if market_regime:
        filters["market_regime"] = market_regime
    if outcome:
        filters["outcome"] = outcome

    try:
        results = store._fallback_search("trade_context", filters, limit)
    except Exception:
        results = []

    if not results:
        return {
            "trades_found": 0,
            "trades": [],
            "interpretation": "No similar past trades found.",
        }

    trades = []
    for r in results:
        meta = r.get("metadata", {})
        trades.append({
            "ticker": meta.get("ticker", "?"),
            "action": meta.get("action", "?"),
            "regime": meta.get("market_regime", "?"),
            "outcome": meta.get("outcome", "pending"),
            "pnl": meta.get("pnl"),
            "judge_reasoning": meta.get("judge_reasoning", "")[:150],
        })

    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = sum(1 for t in trades if t["outcome"] == "loss")

    return {
        "trades_found": len(trades),
        "wins": wins,
        "losses": losses,
        "trades": trades,
        "interpretation": (
            f"Found {len(trades)} similar trades. "
            f"Record: {wins}W/{losses}L. "
            f"Review before making your decision."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


def _format_lessons(results: list[str], analyst_type: str) -> Dict[str, Any]:
    """Format retrieval results into a standard lessons response."""
    if not results:
        return {
            "lessons_found": 0,
            "lessons": [],
            "interpretation": f"No past {analyst_type} lessons found. Proceed with fresh analysis.",
        }

    lessons = []
    for r in results:
        lessons.append({
            "lesson": r.get("text", "")[:300],
            "relevance_score": round(r.get("score", 0), 3),
            "regime": r.get("metadata", {}).get("market_regime", "unknown"),
            "brier_score": r.get("metadata", {}).get("brier_score"),
        })

    return {
        "lessons_found": len(lessons),
        "lessons": lessons,
        "interpretation": (
            f"Found {len(lessons)} relevant past {analyst_type} lessons. "
            f"Review them before making your prediction."
        ),
    }
