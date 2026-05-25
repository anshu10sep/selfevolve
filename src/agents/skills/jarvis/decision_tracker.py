"""
Decision Tracker — Strategic decision logging for Jarvis.

Tracks Jarvis's strategic decisions (evolution tasks, agent spawns,
code changes, risk escalations) and logs them as evolution events
for scoring and review.

This enables Jarvis to be held accountable for its decisions and
feeds into the trust weight system (Jarvis is in SCORABLE_ROLES).

This module is imported by Jarvis.__init__() to trigger @skill("master")
registration before BaseAgent._load_skills() runs.
"""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory decision log (persisted to DB as evolution events) ──
_decision_log: list[dict[str, Any]] = []


def _persist_decision(decision: dict) -> dict:
    """Persist a decision to both memory and DB."""
    _decision_log.append(decision)

    try:
        from persistence.db import create_evolution_event
        return create_evolution_event(
            id=decision["id"],
            event_type=decision["event_type"],
            description=decision["description"],
            agent_role="MASTER",
            details=decision.get("details"),
        )
    except Exception as e:
        logger.error(f"Failed to persist decision to DB: {e}")
        return decision


# ── LLM Tool-Calling Registration ─────────────────────────────────
from agents.skills.validator import skill


@skill("master")
def log_strategic_decision(
    decision_type: str,
    description: str,
    rationale: str,
    expected_outcome: str = "",
    confidence: str = "0.7",
) -> str:
    """Log a strategic decision made by Jarvis for accountability and evolution tracking.
    Every significant action should be logged so it can be reviewed and scored.

    Decision types: AGENT_SPAWN, CODE_CHANGE, RISK_ESCALATION, STRATEGY_SHIFT,
    EVOLUTION_TASK, AGENT_RETIREMENT, PROMPT_UPDATE, CONFIGURATION_CHANGE.

    Args:
        decision_type: Category of decision (e.g., "CODE_CHANGE", "AGENT_SPAWN").
        description: What was decided (e.g., "Created CTO Agent to monitor infrastructure").
        rationale: Why this decision was made (e.g., "System audit showed no infra monitoring").
        expected_outcome: What success looks like (e.g., "CTO detects latency issues within 6h").
        confidence: Jarvis's confidence in this decision (0.0-1.0, default "0.7").

    Returns:
        Confirmation message with the decision ID.
    """
    try:
        conf = float(confidence)
    except ValueError:
        conf = 0.7

    decision = {
        "id": str(uuid.uuid4()),
        "event_type": f"JARVIS_DECISION_{decision_type.upper()}",
        "description": description,
        "details": {
            "decision_type": decision_type.upper(),
            "rationale": rationale,
            "expected_outcome": expected_outcome,
            "confidence": conf,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    result = _persist_decision(decision)
    logger.info(
        f"Strategic decision logged: [{decision_type}] {description[:80]}"
    )
    return (
        f"✅ Decision logged (ID: {decision['id'][:8]}...)\n"
        f"Type: {decision_type}\n"
        f"Description: {description}\n"
        f"Confidence: {conf:.0%}"
    )


@skill("master")
def get_decision_history(limit: str = "10") -> str:
    """Get Jarvis's recent strategic decisions for review and self-reflection.
    Use this to review past decisions and assess their outcomes.

    Args:
        limit: Maximum number of decisions to return (default "10").

    Returns:
        Formatted list of recent decisions with types, descriptions, and rationale.
    """
    try:
        count = int(limit)
    except ValueError:
        count = 10

    # First try from DB (more durable)
    try:
        from persistence.db import get_evolution_events
        events = get_evolution_events(limit=50)
        # Filter to Jarvis decisions only
        decisions = [e for e in events if e.get("event_type", "").startswith("JARVIS_DECISION")][:count]
    except Exception:
        decisions = _decision_log[-count:]

    if not decisions:
        return "No strategic decisions logged yet. Use log_strategic_decision to track decisions."

    lines = [f"# Jarvis Decision History (last {count})", ""]

    for d in decisions:
        ts = d.get("created_at", d.get("details", {}).get("timestamp", "?"))
        etype = d.get("event_type", "?").replace("JARVIS_DECISION_", "")
        desc = d.get("description", "")
        details = d.get("details", {})
        rationale = details.get("rationale", "")
        conf = details.get("confidence", "?")

        lines.append(f"### [{etype}] {desc[:100]}")
        lines.append(f"- **When**: {ts}")
        if isinstance(conf, (int, float)):
            lines.append(f"- **Confidence**: {conf:.0%}")
        if rationale:
            lines.append(f"- **Rationale**: {rationale[:150]}")
        expected = details.get("expected_outcome", "")
        if expected:
            lines.append(f"- **Expected Outcome**: {expected[:150]}")
        lines.append("")

    return "\n".join(lines)


@skill("master")
def log_evolution_milestone(
    milestone: str,
    details: str,
    metrics: str = "",
) -> str:
    """Log a significant system evolution milestone.
    Use this when something noteworthy happens: first trade, new agent operational,
    trust weights updated, system audit passed, etc.

    Args:
        milestone: Short name of the milestone (e.g., "First Trade Executed").
        details: Description of what happened and its significance.
        metrics: Optional JSON string with numeric metrics to track.

    Returns:
        Confirmation message.
    """
    metrics_dict = {}
    if metrics:
        try:
            metrics_dict = json.loads(metrics)
        except json.JSONDecodeError:
            metrics_dict = {"raw": metrics}

    decision = {
        "id": str(uuid.uuid4()),
        "event_type": "EVOLUTION_MILESTONE",
        "description": f"🏁 {milestone}: {details}",
        "details": {
            "milestone": milestone,
            "details": details,
            "metrics": metrics_dict,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

    _persist_decision(decision)
    logger.info(f"Evolution milestone: {milestone}")
    return f"✅ Milestone logged: {milestone}\n{details}"
