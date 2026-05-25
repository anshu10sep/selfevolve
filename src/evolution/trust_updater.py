"""
Trust Weight Updater

Computes rolling Brier scores from real prediction data and
updates agent trust weights deterministically.

Run frequency: Every 6 hours via _run_continuous_evolution()

Flow:
  1. For each agent role, fetch resolved predictions (last 30)
  2. Compute Brier score via BrierScoreEngine
  3. Compare to previous Brier score
  4. Apply trust decay (if worse) or boost (if better)
  5. Write updated scores to agent_scores table
  6. Log evolution event
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from config.constants import BRIER_WINDOW_SIZE, TRUST_DECAY_RATE, MIN_TRUST_WEIGHT
from evolution.reflexion import BrierScoreEngine, TrustDecayManager
from evolution.prediction_tracker import prediction_tracker
from persistence.db import (
    upsert_agent_score,
    get_agent_scores,
    create_evolution_event,
)

logger = structlog.get_logger(component="trust_updater")

# Agent roles that participate in trust scoring via Brier predictions
PREDICTION_BASED_ROLES = {
    "FUNDAMENTAL_ANALYST",
    "TECHNICAL_ANALYST",
    "SENTIMENT_ANALYST",
    "MACRO_ANALYST",
    "JUDGE",
    "BULL",
    "BEAR",
    "PORTFOLIO_MANAGER",
    "STRATEGY_RESEARCHER",
    "MASTER",
    "CRYPTO_ANALYST",
}

# Agent roles scored via operational metrics (not trade predictions)
OPERATIONAL_ROLES = {
    "CTO",
    "CSO",
    "CRO",
    "CEO",
    "QA",
    "PRODUCT",
    "META_REVIEW",
    "DEVELOPER",
    "AUDITOR",
    "PERFORMANCE_ANALYST",
}

# All roles that participate in trust scoring
SCORABLE_ROLES = sorted(PREDICTION_BASED_ROLES | OPERATIONAL_ROLES)

# Human-readable names for each role
ROLE_NAMES = {
    "FUNDAMENTAL_ANALYST": "Fundamental Analyst",
    "TECHNICAL_ANALYST": "Technical Analyst",
    "SENTIMENT_ANALYST": "Sentiment Analyst",
    "MACRO_ANALYST": "Macro Analyst",
    "JUDGE": "Judge Agent",
    "BULL": "Bull Agent",
    "BEAR": "Bear Agent",
    "PORTFOLIO_MANAGER": "Portfolio Manager",
    "STRATEGY_RESEARCHER": "Strategy Researcher",
    "MASTER": "Jarvis (CEO)",
    "CRYPTO_ANALYST": "Crypto Analyst",
    "CTO": "CTO",
    "CSO": "CSO",
    "CRO": "Chief Risk Officer",
    "CEO": "CEO",
    "QA": "QA Director",
    "PRODUCT": "Product Director",
    "META_REVIEW": "Evolution Director",
    "DEVELOPER": "Developer Agent",
    "AUDITOR": "Auditor Agent",
    "PERFORMANCE_ANALYST": "Performance Analyst",
}

# Brier score thresholds
BRIER_GOOD = 0.20       # Below this = well-calibrated
BRIER_BASELINE = 0.25   # Random guessing at 50%
BRIER_POOR = 0.35       # Above this = underperforming


def update_all_trust_weights() -> dict[str, Any]:
    """Compute Brier scores and update trust weights for all scorable agents.
    
    Returns:
        Summary dict with per-agent results for reporting.
    """
    results = {}
    total_updated = 0
    
    # Get current scores from DB for comparison
    current_scores = {s["role"]: s for s in get_agent_scores()}
    
    for role in SCORABLE_ROLES:
        try:
            if role in PREDICTION_BASED_ROLES:
                result = _update_agent_trust(role, current_scores.get(role, {}))
            else:
                # Operational agent — use operational scorer
                result = _update_operational_trust(role, current_scores.get(role, {}))
            results[role] = result
            if result.get("updated"):
                total_updated += 1
        except Exception as e:
            logger.error("trust_update_failed", agent=role, error=str(e))
            results[role] = {"error": str(e), "updated": False}
    
    logger.info(
        "trust_weights_updated",
        total_agents=len(SCORABLE_ROLES),
        updated=total_updated,
    )
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_evaluated": len(SCORABLE_ROLES),
        "agents_updated": total_updated,
        "results": results,
    }


def _update_agent_trust(role: str, current: dict) -> dict[str, Any]:
    """Update trust weight for a single agent based on Brier score."""
    name = ROLE_NAMES.get(role, role)
    
    # Fetch resolved predictions
    predictions = prediction_tracker.get_resolved_predictions(
        agent_role=role, window=BRIER_WINDOW_SIZE,
    )
    
    if len(predictions) < 5:
        # Not enough data to compute meaningful Brier score
        return {
            "updated": False,
            "reason": f"Insufficient predictions ({len(predictions)}/5 minimum)",
            "prediction_count": len(predictions),
        }
    
    # Compute Brier score
    probs, outcomes = prediction_tracker.extract_brier_inputs(predictions)
    brier = BrierScoreEngine.calculate(probs, outcomes)
    
    # Get previous values
    old_brier = current.get("brier_score") or 0.5
    old_trust = current.get("trust_weight") or 1.0
    
    # Determine trust adjustment
    if brier < old_brier:
        # Improvement — boost trust
        new_trust = TrustDecayManager.boost_trust(old_trust)
        consecutive_failures = 0
        direction = "IMPROVED"
    elif brier > BRIER_POOR:
        # Poor calibration — decay trust
        consecutive_failures = _count_consecutive_poor(predictions)
        new_trust = TrustDecayManager.decay_trust(
            old_trust, consecutive_failures, TRUST_DECAY_RATE, MIN_TRUST_WEIGHT,
        )
        direction = "DECAYED"
    else:
        # Stable — no change
        new_trust = old_trust
        consecutive_failures = 0
        direction = "STABLE"
    
    # Write to DB
    upsert_agent_score(
        role=role,
        name=name,
        trust_weight=new_trust,
        brier_score=brier,
        last_activity=datetime.now(timezone.utc),
    )
    
    # Log evolution event if trust changed significantly
    if abs(new_trust - old_trust) > 0.01:
        create_evolution_event(
            id=str(uuid.uuid4()),
            event_type="TRUST_DECAY" if direction == "DECAYED" else "BACKTEST",
            description=(
                f"{name}: trust {old_trust:.3f} → {new_trust:.3f} "
                f"(Brier {old_brier:.4f} → {brier:.4f}, {direction})"
            ),
            agent_role=role,
            details={
                "old_trust": old_trust,
                "new_trust": new_trust,
                "old_brier": old_brier,
                "new_brier": brier,
                "prediction_count": len(predictions),
                "direction": direction,
            },
        )
    
    logger.info(
        "agent_trust_updated",
        agent=role,
        brier=f"{brier:.4f}",
        trust=f"{old_trust:.3f} → {new_trust:.3f}",
        direction=direction,
        predictions=len(predictions),
    )
    
    return {
        "updated": True,
        "brier_score": brier,
        "old_trust": old_trust,
        "new_trust": new_trust,
        "direction": direction,
        "prediction_count": len(predictions),
    }


def _count_consecutive_poor(predictions: list[dict]) -> int:
    """Count consecutive predictions where the agent was wrong.
    
    A prediction is considered 'wrong' if the predicted probability
    and actual outcome are on opposite sides of 0.5.
    """
    count = 0
    for p in predictions:  # Already sorted by created_at desc
        prob = p.get("predicted_probability", 0.5)
        outcome = p.get("actual_outcome")
        if outcome is None:
            continue
        # Was the prediction directionally correct?
        predicted_win = prob >= 0.5
        actual_win = outcome == 1
        if predicted_win != actual_win:
            count += 1
        else:
            break  # Streak broken
    return count


def get_trust_summary() -> list[dict]:
    """Get current trust weight summary for all agents (for dashboard/reports)."""
    scores = get_agent_scores()
    summary = []
    for s in scores:
        brier = s.get("brier_score")
        if brier is not None:
            if brier < BRIER_GOOD:
                calibration = "EXCELLENT"
            elif brier < BRIER_BASELINE:
                calibration = "GOOD"
            elif brier < BRIER_POOR:
                calibration = "FAIR"
            else:
                calibration = "POOR"
        else:
            calibration = "NO_DATA"
        
        summary.append({
            "role": s["role"],
            "name": s.get("name", s["role"]),
            "trust_weight": s.get("trust_weight", 1.0),
            "brier_score": brier,
            "calibration": calibration,
        })
    return summary


# ════════════════════════════════════════════════════════════════════
# OPERATIONAL TRUST SCORING (for non-prediction agents)
# ════════════════════════════════════════════════════════════════════

def _update_operational_trust(role: str, current: dict) -> dict[str, Any]:
    """Update trust weight for an operational agent using operational metrics.

    Instead of Brier scores, operational agents are scored by:
    - Bug fix success rate (Developer)
    - Evolution effectiveness (Meta-Review)
    - System stability (QA)
    - etc.

    The operational score (0-1) is treated like an inverse Brier score:
    - score > 0.6 → trust boost
    - score < 0.4 → trust decay
    - 0.4-0.6 → stable
    """
    from evolution.operational_scorer import score_operational_agent

    name = ROLE_NAMES.get(role, role)
    score_result = score_operational_agent(role)

    if score_result is None:
        return {
            "updated": False,
            "reason": "Insufficient operational data for scoring",
            "scoring_method": "operational",
        }

    op_score = score_result["score"]
    old_trust = current.get("trust_weight") or 1.0

    # Convert operational score to trust adjustment
    if op_score > 0.6:
        # Good performance — boost trust
        new_trust = TrustDecayManager.boost_trust(old_trust)
        direction = "IMPROVED"
    elif op_score < 0.4:
        # Poor performance — decay trust
        consecutive_failures = max(1, int((0.5 - op_score) * 10))
        new_trust = TrustDecayManager.decay_trust(
            old_trust, consecutive_failures, TRUST_DECAY_RATE, MIN_TRUST_WEIGHT,
        )
        direction = "DECAYED"
    else:
        # Stable — no change
        new_trust = old_trust
        direction = "STABLE"

    # Write to DB (store operational score as brier_score for unified interface)
    upsert_agent_score(
        role=role,
        name=name,
        trust_weight=new_trust,
        brier_score=1.0 - op_score,  # Invert: lower brier = better
        last_activity=datetime.now(timezone.utc),
    )

    # Log evolution event if trust changed significantly
    if abs(new_trust - old_trust) > 0.01:
        create_evolution_event(
            id=str(uuid.uuid4()),
            event_type="OPERATIONAL_TRUST" if direction != "DECAYED" else "TRUST_DECAY",
            description=(
                f"{name}: trust {old_trust:.3f} → {new_trust:.3f} "
                f"(operational score {op_score:.4f}, {direction})"
            ),
            agent_role=role,
            details={
                "old_trust": old_trust,
                "new_trust": new_trust,
                "operational_score": op_score,
                "metric_name": score_result["metric_name"],
                "direction": direction,
                "raw_data": score_result.get("raw_data", {}),
            },
        )

    logger.info(
        "operational_trust_updated",
        agent=role,
        score=f"{op_score:.4f}",
        trust=f"{old_trust:.3f} → {new_trust:.3f}",
        direction=direction,
        metric=score_result["metric_name"],
    )

    return {
        "updated": True,
        "scoring_method": "operational",
        "operational_score": op_score,
        "metric_name": score_result["metric_name"],
        "old_trust": old_trust,
        "new_trust": new_trust,
        "direction": direction,
        "interpretation": score_result.get("interpretation", ""),
    }
