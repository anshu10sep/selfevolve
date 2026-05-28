# 10 — Operational Scoring

## Purpose

Not all agents make trade predictions. Operational agents (CTO, Developer, QA, etc.) need alternative metrics for the trust system.

## Current Implementation

**File**: `evolution/operational_scorer.py`

| Agent | Metric | Data Source |
|-------|--------|-------------|
| DEVELOPER | Bug fix success rate | `bug_tasks` table |
| AUDITOR | Activity success rate | Activity tracker (fallback) |
| QA | System stability | Activity tracker (fallback) |
| META_REVIEW | Evolution effectiveness | `evolution_events` table |
| CTO | Architecture quality (1 - bug density) | `bug_tasks` table |
| CSO | Security posture | Activity tracker (fallback) |
| CRO | Risk-adjusted returns (Sharpe) | `trades` table |
| PRODUCT | Strategy approval quality | Activity tracker (fallback) |
| CEO | Win rate + P&L direction | `trades` table |
| PERFORMANCE_ANALYST | Reporting accuracy | Activity tracker (fallback) |

## Problems

### 1. Most Use Fallback Scorer
6 of 10 operational agents use `_score_from_activity()`, which only measures "consecutive failures" — not actual performance quality. This is a crude proxy.

### 2. No Real-Time Data for Most Agents
Agents like CSO and AUDITOR don't have structured activity logs. Their scores are essentially random noise.

### 3. Operational Scores Don't Affect Behavior
Even if an operational agent scores poorly, there's no feedback mechanism — these agents don't have evolving prompts or behavior that changes based on trust.

## Proposed Improvements

### Better Metrics per Agent

```python
OPERATIONAL_METRICS = {
    "DEVELOPER": {
        "primary": "bug_fix_success_rate",  # Fixed correctly / assigned
        "secondary": "fix_time_hours",       # Average time to fix
        "tertiary": "regression_rate",       # Fixed bugs that recurred
    },
    "QA": {
        "primary": "test_pass_rate",         # Tests passing / total
        "secondary": "uptime_percentage",    # System uptime
        "tertiary": "mean_time_to_detect",   # How fast bugs are caught
    },
    "META_REVIEW": {
        "primary": "evolution_roi",          # Avg trust delta post-evolution
        "secondary": "prompt_promotion_rate",# Candidates that get promoted
        "tertiary": "time_to_evolve",        # Cycle time for evolution
    },
    "CRO": {
        "primary": "sharpe_ratio",           # Risk-adjusted returns
        "secondary": "max_drawdown_pct",     # Worst drawdown
        "tertiary": "var_breach_count",      # VaR violations
    },
}
```

### Structured Activity Tracking

Add explicit success/failure tracking for every operational agent invocation:

```python
class OperationalActivityLog:
    """Log every operational agent action with outcome."""

    @staticmethod
    def log_action(
        agent_role: str,
        action_type: str,
        success: bool,
        details: dict = None,
    ):
        create_operational_log(
            agent_role=agent_role,
            action_type=action_type,  # "BUG_FIX", "AUDIT", "SECURITY_SCAN"
            success=success,
            details=details or {},
            created_at=datetime.now(timezone.utc),
        )
```

### Composite Scoring

Instead of a single metric, use a weighted composite:

```python
def score_agent_composite(role: str) -> float:
    metrics = OPERATIONAL_METRICS.get(role, {})
    scores = []
    weights = [0.5, 0.3, 0.2]  # Primary, secondary, tertiary

    for (metric_name, weight) in zip(
        ["primary", "secondary", "tertiary"],
        weights
    ):
        if metric_name in metrics:
            value = compute_metric(role, metrics[metric_name])
            if value is not None:
                scores.append((value, weight))

    if not scores:
        return None

    total_weight = sum(w for _, w in scores)
    composite = sum(s * w for s, w in scores) / total_weight
    return composite
```
