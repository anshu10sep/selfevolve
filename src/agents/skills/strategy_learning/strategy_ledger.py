"""
Strategy Ledger — Immutable Audit Trail

Records every parameter version, every trade decision, and every
evolution event. This is the "source of truth" for the self-evolution
system — nothing can be evolved without a record in the ledger.

Storage: JSON Lines on disk (designed for easy PostgreSQL migration).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.skills.validator import skill

logger = structlog.get_logger(component="strategy_ledger")


# Persistence directory
LEDGER_DIR = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")),
    "data", "strategy_ledger",
)


class StrategyLedger:
    """
    Immutable ledger for strategy evolution events.

    Every entry is append-only — nothing is ever deleted or modified.
    This provides a complete audit trail for regulatory compliance
    and post-mortem analysis.
    """

    def __init__(self, data_dir: str = LEDGER_DIR):
        self._data_dir = data_dir
        os.makedirs(self._data_dir, exist_ok=True)

    def _append(self, category: str, record: dict) -> str:
        """Append a record to a category-specific ledger file."""
        filepath = os.path.join(self._data_dir, f"{category}.jsonl")
        record["_ledger_timestamp"] = datetime.now(timezone.utc).isoformat()

        with open(filepath, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

        return filepath

    def _read(self, category: str, limit: int = 100) -> list[dict]:
        """Read recent entries from a category-specific ledger."""
        filepath = os.path.join(self._data_dir, f"{category}.jsonl")
        if not os.path.exists(filepath):
            return []

        entries = []
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))

        return entries[-limit:]

    # ── Parameter Versions ─────────────────────────────────────────

    def record_parameter_version(
        self,
        strategy_name: str,
        version: int,
        params: dict,
        status: str,
        change_reason: str = "",
        parent_version: Optional[int] = None,
    ) -> None:
        """Record a new parameter version (LIVE, SHADOW, or RETIRED)."""
        self._append("parameter_versions", {
            "strategy_name": strategy_name,
            "version": version,
            "params": params,
            "status": status,
            "change_reason": change_reason,
            "parent_version": parent_version,
        })
        logger.info(
            "parameter_version_recorded",
            strategy=strategy_name,
            version=version,
            status=status,
        )

    def record_parameter_promotion(
        self,
        strategy_name: str,
        from_version: int,
        to_version: int,
        test_result: dict,
    ) -> None:
        """Record a parameter promotion from SHADOW to LIVE."""
        self._append("parameter_promotions", {
            "strategy_name": strategy_name,
            "from_version": from_version,
            "to_version": to_version,
            "p_value": test_result.get("p_value"),
            "t_statistic": test_result.get("t_statistic"),
            "improvement_pct": test_result.get("improvement_pct"),
            "test_result": test_result,
        })
        logger.info(
            "parameter_promoted",
            strategy=strategy_name,
            from_version=from_version,
            to_version=to_version,
            p_value=test_result.get("p_value"),
        )

    def get_parameter_history(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get parameter version history."""
        entries = self._read("parameter_versions", limit=limit * 2)
        if strategy_name:
            entries = [e for e in entries if e.get("strategy_name") == strategy_name]
        return entries[-limit:]

    # ── Trade Decisions ────────────────────────────────────────────

    def record_trade_decision(
        self,
        strategy_name: str,
        ticker: str,
        decision: str,
        signal_strength: float,
        params_version: int,
        market_data_snapshot: dict,
        reasoning: str = "",
    ) -> None:
        """Record every trade decision (including PASS decisions)."""
        self._append("trade_decisions", {
            "strategy_name": strategy_name,
            "ticker": ticker,
            "decision": decision,  # BUY, SELL, HOLD, PASS
            "signal_strength": signal_strength,
            "params_version": params_version,
            "market_data_snapshot": market_data_snapshot,
            "reasoning": reasoning,
        })

    def record_trade_result(
        self,
        strategy_name: str,
        trade_id: str,
        ticker: str,
        pnl_usd: float,
        pnl_pct: float,
        is_winner: bool,
        params_version: int,
        learning_report: Optional[dict] = None,
    ) -> None:
        """Record the outcome of a completed trade."""
        self._append("trade_results", {
            "strategy_name": strategy_name,
            "trade_id": trade_id,
            "ticker": ticker,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "is_winner": is_winner,
            "params_version": params_version,
            "learning_report": learning_report,
        })

    # ── Evolution Events ───────────────────────────────────────────

    def record_evolution_event(
        self,
        strategy_name: str,
        event_type: str,
        details: dict,
    ) -> None:
        """
        Record a self-evolution event.

        Event types:
          - PARAMETER_PROPOSED: New parameters proposed for shadow testing
          - PARAMETER_PROMOTED: Shadow params promoted to live
          - PARAMETER_REJECTED: Shadow params rejected (didn't pass t-test)
          - PARAMETER_ROLLED_BACK: Live params rolled back to previous version
          - STRATEGY_PAUSED: Strategy paused due to drawdown
          - STRATEGY_RETIRED: Strategy retired due to persistent underperformance
          - STRATEGY_SPAWNED: New strategy agent created
          - REGIME_SHIFT: Market regime changed, affecting allocations
          - ALLOCATION_CHANGED: Portfolio Manager updated allocations
        """
        self._append("evolution_events", {
            "strategy_name": strategy_name,
            "event_type": event_type,
            "details": details,
        })
        logger.info(
            "evolution_event",
            strategy=strategy_name,
            event_type_name=event_type,
        )

    def record_allocation_change(
        self,
        old_allocations: dict[str, float],
        new_allocations: dict[str, float],
        regime: str,
        reasoning: str = "",
    ) -> None:
        """Record a Portfolio Manager allocation change."""
        self._append("allocation_changes", {
            "old_allocations": old_allocations,
            "new_allocations": new_allocations,
            "regime": regime,
            "reasoning": reasoning,
            "total_shift": sum(
                abs(new_allocations.get(k, 0) - old_allocations.get(k, 0))
                for k in set(old_allocations) | set(new_allocations)
            ),
        })

    # ── Queries ────────────────────────────────────────────────────

    def get_trade_results(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get trade results, optionally filtered by strategy."""
        entries = self._read("trade_results", limit=limit * 2)
        if strategy_name:
            entries = [e for e in entries if e.get("strategy_name") == strategy_name]
        return entries[-limit:]

    def get_evolution_events(
        self,
        strategy_name: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get evolution events with optional filters."""
        entries = self._read("evolution_events", limit=limit * 2)
        if strategy_name:
            entries = [e for e in entries if e.get("strategy_name") == strategy_name]
        if event_type:
            entries = [e for e in entries if e.get("event_type") == event_type]
        return entries[-limit:]

    def get_allocation_history(self, limit: int = 30) -> list[dict]:
        """Get allocation change history."""
        return self._read("allocation_changes", limit=limit)

    def get_strategy_evolution_summary(self, strategy_name: str) -> dict:
        """
        Get a comprehensive evolution summary for a strategy.

        Returns counts of all evolution events, latest parameter version,
        and learning trajectory.
        """
        events = self.get_evolution_events(strategy_name=strategy_name, limit=500)
        params = self.get_parameter_history(strategy_name=strategy_name, limit=100)
        trades = self.get_trade_results(strategy_name=strategy_name, limit=500)

        event_counts = {}
        for e in events:
            et = e.get("event_type", "unknown")
            event_counts[et] = event_counts.get(et, 0) + 1

        latest_version = params[-1].get("version", 1) if params else 1

        winners = sum(1 for t in trades if t.get("is_winner", False))
        total_pnl = sum(t.get("pnl_usd", 0) for t in trades)

        return {
            "strategy_name": strategy_name,
            "total_events": len(events),
            "event_counts": event_counts,
            "total_parameter_versions": len(params),
            "latest_version": latest_version,
            "total_trades_recorded": len(trades),
            "win_rate": round(winners / len(trades), 4) if trades else 0,
            "total_pnl": round(total_pnl, 2),
        }


# ── Skill-decorated access functions ──────────────────────────────

@skill("strategy_agent")
def record_evolution(
    strategy_name: str,
    event_type: str,
    details: dict,
) -> str:
    """
    Record a strategy evolution event in the immutable ledger.

    Args:
        strategy_name: Strategy that evolved
        event_type: Type of evolution event
        details: Event-specific data

    Returns:
        Confirmation message
    """
    ledger = StrategyLedger()
    ledger.record_evolution_event(strategy_name, event_type, details)
    return f"Recorded {event_type} for {strategy_name}"


@skill("strategy_agent")
def get_evolution_summary(strategy_name: str) -> dict:
    """
    Get the complete evolution summary for a strategy.

    Args:
        strategy_name: Strategy to summarize

    Returns:
        Evolution summary with event counts, versions, and performance
    """
    ledger = StrategyLedger()
    return ledger.get_strategy_evolution_summary(strategy_name)


# Module-level singleton
strategy_ledger = StrategyLedger()
