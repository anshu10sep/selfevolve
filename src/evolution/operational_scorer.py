"""
Operational Scorer — Trust Metrics for Non-Prediction Agents

Prediction-based agents (analysts, judge, bull/bear) are scored via
Brier scores on their trade predictions. But operational agents
(CTO, CSO, QA, Developer, Auditor, etc.) don't make trade predictions.

This module provides ALTERNATIVE scoring metrics for those agents
so they can also participate in the self-evolution loop:

  Agent           | Metric
  ───────────────────────────────────────────────────────
  DEVELOPER       | Bug fix success rate (bugs_fixed / bugs_assigned)
  AUDITOR         | Finding accuracy (valid_findings / total_findings)
  QA              | System stability score (1 - error_rate)
  META_REVIEW     | Evolution ROI (avg Δ performance post-evolution)
  CTO             | Architecture quality (1 - bug_density)
  CSO             | Security coverage (scans_passed / total_scans)
  CRO             | Risk-adjusted returns (Sharpe ratio normalized 0-1)
  CEO/MASTER      | Overall portfolio return (handled by Brier already)
  PRODUCT         | Strategy approval ROI (avg return of approved strategies)
  PERFORMANCE_ANALYST | Report accuracy (cross-validated)

All scores are normalized to 0.0 - 1.0 range:
  0.0 = terrible performance (trust should decay)
  0.5 = baseline (no change)
  1.0 = excellent performance (trust should boost)

These scores feed into the same TrustDecayManager as Brier scores.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger(component="operational_scorer")


def score_operational_agent(role: str) -> Optional[dict[str, Any]]:
    """Score a non-prediction agent using operational metrics.

    Args:
        role: Agent role string (e.g., "DEVELOPER", "AUDITOR")

    Returns:
        Dict with score (0-1), metric_name, raw_data, and interpretation.
        None if insufficient data to score.
    """
    scorers = {
        "DEVELOPER": _score_developer,
        "AUDITOR": _score_auditor,
        "QA": _score_qa,
        "META_REVIEW": _score_meta_review,
        "CTO": _score_cto,
        "CSO": _score_cso,
        "CRO": _score_cro,
        "PRODUCT": _score_product,
        "CEO": _score_ceo,
        "PERFORMANCE_ANALYST": _score_performance_analyst,
    }

    scorer = scorers.get(role)
    if not scorer:
        return None

    try:
        return scorer()
    except Exception as e:
        logger.warning("operational_score_failed", role=role, error=str(e))
        return None


def _score_developer() -> Optional[dict[str, Any]]:
    """Score DEVELOPER by bug fix success rate.

    Metric: bugs_fixed_successfully / bugs_assigned
    Source: bug_tasks table (via bug_scanner → bug_worker pipeline)
    """
    try:
        from persistence.db import get_session
        from sqlalchemy import text

        with get_session() as session:
            result = session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('FIXED', 'VERIFIED')) as fixed,
                    COUNT(*) FILTER (WHERE status IN ('FAILED', 'ABANDONED')) as failed,
                    COUNT(*) as total
                FROM bug_tasks
                WHERE created_at > :cutoff
            """), {"cutoff": _cutoff_30d()}).fetchone()

            if not result or result.total < 3:
                return None

            score = result.fixed / result.total if result.total > 0 else 0.5
            return {
                "score": round(score, 4),
                "metric_name": "bug_fix_success_rate",
                "raw_data": {
                    "bugs_fixed": result.fixed,
                    "bugs_failed": result.failed,
                    "bugs_total": result.total,
                },
                "interpretation": (
                    f"Developer: {result.fixed}/{result.total} bugs fixed "
                    f"({score:.0%} success rate)"
                ),
            }
    except Exception:
        return _score_from_activity("DEVELOPER", "bug_fix_success")


def _score_auditor() -> Optional[dict[str, Any]]:
    """Score AUDITOR by activity and success rate.

    Since we don't track audit findings in a structured table,
    use activity tracker success rate as proxy.
    """
    return _score_from_activity("AUDITOR", "audit_accuracy")


def _score_qa() -> Optional[dict[str, Any]]:
    """Score QA by system stability.

    Metric: 1 - (error_events / total_events) over last 30 days
    Source: activity_tracker success/failure rates
    """
    return _score_from_activity("QA", "system_stability")


def _score_meta_review() -> Optional[dict[str, Any]]:
    """Score META_REVIEW by evolution effectiveness.

    Metric: How much do agent scores improve after evolution events?
    Source: evolution_events table
    """
    try:
        from persistence.db import get_session
        from sqlalchemy import text

        with get_session() as session:
            # Count evolution events and their outcomes
            result = session.execute(text("""
                SELECT
                    COUNT(*) as total_events,
                    COUNT(*) FILTER (WHERE details::text LIKE '%IMPROVED%') as improvements,
                    COUNT(*) FILTER (WHERE details::text LIKE '%DECAYED%') as decays
                FROM evolution_events
                WHERE created_at > :cutoff
            """), {"cutoff": _cutoff_30d()}).fetchone()

            if not result or result.total_events < 3:
                return None

            # Score: improvement ratio
            positive = result.improvements
            total = result.total_events
            score = positive / total if total > 0 else 0.5

            return {
                "score": round(score, 4),
                "metric_name": "evolution_effectiveness",
                "raw_data": {
                    "total_events": result.total_events,
                    "improvements": result.improvements,
                    "decays": result.decays,
                },
                "interpretation": (
                    f"Meta-Review: {result.improvements}/{result.total_events} "
                    f"evolution events improved performance ({score:.0%})"
                ),
            }
    except Exception:
        return _score_from_activity("META_REVIEW", "evolution_effectiveness")


def _score_cto() -> Optional[dict[str, Any]]:
    """Score CTO by architecture quality.

    Proxy: inverse bug density (fewer bugs = better architecture)
    """
    try:
        from persistence.db import get_session
        from sqlalchemy import text

        with get_session() as session:
            # Bug density: bugs per day
            result = session.execute(text("""
                SELECT COUNT(*) as bug_count
                FROM bug_tasks
                WHERE created_at > :cutoff
            """), {"cutoff": _cutoff_30d()}).fetchone()

            if not result:
                return None

            bugs_per_day = result.bug_count / 30.0
            # Score: fewer bugs = higher score
            # 0 bugs/day → 1.0, 5+ bugs/day → 0.0
            score = max(0.0, min(1.0, 1.0 - (bugs_per_day / 5.0)))

            return {
                "score": round(score, 4),
                "metric_name": "architecture_quality",
                "raw_data": {
                    "bugs_30d": result.bug_count,
                    "bugs_per_day": round(bugs_per_day, 2),
                },
                "interpretation": (
                    f"CTO: {result.bug_count} bugs in 30d "
                    f"({bugs_per_day:.1f}/day → quality score {score:.2f})"
                ),
            }
    except Exception:
        return _score_from_activity("CTO", "architecture_quality")


def _score_cso() -> Optional[dict[str, Any]]:
    """Score CSO by security posture.

    Proxy: activity success rate (security scans that pass)
    """
    return _score_from_activity("CSO", "security_posture")


def _score_cro() -> Optional[dict[str, Any]]:
    """Score CRO by risk-adjusted returns.

    Metric: Sharpe ratio of portfolio, normalized to 0-1 score.
    Source: Portfolio returns from trade history
    """
    try:
        from persistence.db import get_session
        from sqlalchemy import text
        import math

        with get_session() as session:
            result = session.execute(text("""
                SELECT
                    AVG(pnl_percent) as avg_return,
                    STDDEV(pnl_percent) as std_return,
                    COUNT(*) as trade_count
                FROM trades
                WHERE status = 'CLOSED'
                AND created_at > :cutoff
            """), {"cutoff": _cutoff_30d()}).fetchone()

            if not result or result.trade_count < 5:
                return None

            avg = float(result.avg_return or 0)
            std = float(result.std_return or 1)

            # Annualized Sharpe (assume ~252 trading days)
            sharpe = (avg / std) * math.sqrt(252) if std > 0 else 0

            # Normalize: Sharpe -2 → 0.0, Sharpe 0 → 0.5, Sharpe 2 → 1.0
            score = max(0.0, min(1.0, (sharpe + 2) / 4))

            return {
                "score": round(score, 4),
                "metric_name": "risk_adjusted_returns",
                "raw_data": {
                    "avg_return": round(avg, 4),
                    "std_return": round(std, 4),
                    "sharpe_ratio": round(sharpe, 4),
                    "trade_count": result.trade_count,
                },
                "interpretation": (
                    f"CRO: Sharpe={sharpe:.2f}, "
                    f"Avg return={avg:.2%}, Trades={result.trade_count}"
                ),
            }
    except Exception:
        return _score_from_activity("CRO", "risk_management")


def _score_product() -> Optional[dict[str, Any]]:
    """Score PRODUCT by strategy approval quality.

    Proxy: activity success rate
    """
    return _score_from_activity("PRODUCT", "strategy_approval_quality")


def _score_ceo() -> Optional[dict[str, Any]]:
    """Score CEO/MASTER by overall system performance.

    This role is typically scored via Brier in the main trust_updater,
    but as a fallback we use total P&L direction.
    """
    try:
        from persistence.db import get_session
        from sqlalchemy import text

        with get_session() as session:
            result = session.execute(text("""
                SELECT
                    SUM(pnl_usd) as total_pnl,
                    COUNT(*) as trade_count,
                    COUNT(*) FILTER (WHERE pnl_usd > 0) as winners
                FROM trades
                WHERE status = 'CLOSED'
                AND created_at > :cutoff
            """), {"cutoff": _cutoff_30d()}).fetchone()

            if not result or result.trade_count < 3:
                return None

            win_rate = result.winners / result.trade_count if result.trade_count > 0 else 0.5
            total_pnl = float(result.total_pnl or 0)

            # Score based on win rate (adjusted for P&L direction)
            score = win_rate
            if total_pnl < 0:
                score *= 0.8  # Penalize negative total P&L

            return {
                "score": round(score, 4),
                "metric_name": "system_performance",
                "raw_data": {
                    "total_pnl": round(total_pnl, 2),
                    "trade_count": result.trade_count,
                    "win_rate": round(win_rate, 4),
                },
                "interpretation": (
                    f"CEO: {result.winners}/{result.trade_count} wins "
                    f"({win_rate:.0%}), Total P&L: ${total_pnl:.2f}"
                ),
            }
    except Exception:
        return _score_from_activity("MASTER", "system_performance")


def _score_performance_analyst() -> Optional[dict[str, Any]]:
    """Score PERFORMANCE_ANALYST by activity success rate."""
    return _score_from_activity("PERFORMANCE_ANALYST", "reporting_accuracy")


# ── Shared Helpers ───────────────────────────────────────────────

def _score_from_activity(role: str, metric_name: str) -> Optional[dict[str, Any]]:
    """Fallback scorer using the activity_tracker success/failure rates.

    Works for any agent — uses the centralized activity tracker data.
    Returns a score based on invocation success rate.
    """
    try:
        from core.activity_tracker import tracker

        data = tracker.get(role)
        if not data:
            return None

        total = data.get("tasks_alltime", 0)
        consecutive_failures = data.get("consecutive_failures", 0)

        if total < 3:
            return None

        # Success rate approximation: use consecutive failures as a signal
        # If no failures, score = 1.0
        # Each consecutive failure reduces score by 0.15
        failure_penalty = min(1.0, consecutive_failures * 0.15)
        score = max(0.0, 1.0 - failure_penalty)

        # Also factor in activity volume — agents that run more are more valuable
        # (but cap the boost so it doesn't overwhelm failure signals)
        if total > 50:
            score = min(1.0, score * 1.05)

        return {
            "score": round(score, 4),
            "metric_name": metric_name,
            "raw_data": {
                "total_calls": total,
                "consecutive_failures": consecutive_failures,
            },
            "interpretation": (
                f"{role}: {total} invocations, "
                f"{consecutive_failures} consecutive failures "
                f"(score {score:.2f})"
            ),
        }
    except Exception as e:
        logger.debug("activity_score_fallback_failed", role=role, error=str(e))
        return None


def _cutoff_30d() -> datetime:
    """Return a datetime 30 days ago (UTC)."""
    return datetime.now(timezone.utc) - timedelta(days=30)
