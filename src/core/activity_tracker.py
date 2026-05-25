"""
Agent Activity Tracker

Centralized, thread-safe singleton that records agent task completions,
token usage, and costs.  The dashboard API reads from this tracker so
that live agent metrics are always up-to-date.

The tracker is intentionally decoupled from both the BaseAgent and the
dashboard API — it only holds counters in memory and provides
helpers that the persistence layer can call to save / restore them.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone, date
from typing import Any

import structlog

logger = structlog.get_logger(component="activity_tracker")


class _AgentCounters:
    """Mutable counters for a single agent role."""

    __slots__ = (
        "tasks_today",
        "tasks_alltime",
        "cost_today",
        "cost_alltime",
        "tokens_today",
        "tokens_alltime",
        "consecutive_failures",
        "last_activity",
        "_date",            # tracks which calendar day `*_today` refers to
    )

    def __init__(self) -> None:
        self.tasks_today: int = 0
        self.tasks_alltime: int = 0
        self.cost_today: float = 0.0
        self.cost_alltime: float = 0.0
        self.tokens_today: int = 0
        self.tokens_alltime: int = 0
        self.consecutive_failures: int = 0
        self.last_activity: str | None = None
        self._date: date = date.today()

    def _maybe_reset_daily(self) -> None:
        """Reset ``*_today`` counters at the start of a new calendar day."""
        today = date.today()
        if today != self._date:
            self.tasks_today = 0
            self.cost_today = 0.0
            self.tokens_today = 0
            self._date = today

    def record(
        self,
        cost: float = 0.0,
        tokens: int = 0,
        success: bool = True,
    ) -> None:
        self._maybe_reset_daily()
        self.tasks_today += 1
        self.tasks_alltime += 1
        self.cost_today += cost
        self.cost_alltime += cost
        self.tokens_today += tokens
        self.tokens_alltime += tokens
        self.last_activity = datetime.now(timezone.utc).isoformat()
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

    def to_dict(self) -> dict[str, Any]:
        self._maybe_reset_daily()
        return {
            "tasks_today": self.tasks_today,
            "tasks_alltime": self.tasks_alltime,
            "cost_today": round(self.cost_today, 6),
            "cost_alltime": round(self.cost_alltime, 6),
            "tokens_today": self.tokens_today,
            "tokens_alltime": self.tokens_alltime,
            "consecutive_failures": self.consecutive_failures,
            "last_activity": self.last_activity,
        }


class ActivityTracker:
    """
    Process-wide singleton that accumulates per-agent counters.

    Usage
    -----
    >>> from core.activity_tracker import tracker
    >>> tracker.record("MASTER", cost=0.0012, tokens=350)
    >>> tracker.get("MASTER")
    {'tasks_today': 1, ...}
    """

    _instance: ActivityTracker | None = None
    _lock = threading.Lock()

    def __new__(cls) -> ActivityTracker:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._counters: dict[str, _AgentCounters] = {}
                cls._instance._mu = threading.Lock()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────

    def record(
        self,
        agent_role: str,
        cost: float = 0.0,
        tokens: int = 0,
        success: bool = True,
    ) -> None:
        """Record a completed task (invocation) for *agent_role*."""
        with self._mu:
            if agent_role not in self._counters:
                self._counters[agent_role] = _AgentCounters()
            self._counters[agent_role].record(cost, tokens, success)

        logger.debug(
            "activity_recorded",
            agent_role=agent_role,
            cost=cost,
            tokens=tokens,
            success=success,
        )

    def get(self, agent_role: str) -> dict[str, Any]:
        """Return the current counters for *agent_role*."""
        with self._mu:
            ctr = self._counters.get(agent_role)
            return ctr.to_dict() if ctr else _AgentCounters().to_dict()

    def get_all(self) -> dict[str, dict[str, Any]]:
        """Return counters for every agent that has reported activity."""
        with self._mu:
            return {role: ctr.to_dict() for role, ctr in self._counters.items()}

    # ── Persistence Helpers ───────────────────────────────────────

    def load_from_dict(self, data: dict[str, dict[str, Any]]) -> None:
        """
        Restore counters from a previously-persisted dict (e.g. from DB
        or state.json).  Only *alltime* fields are restored; daily
        counters start fresh on each restart.
        """
        with self._mu:
            for role, values in data.items():
                ctr = self._counters.setdefault(role, _AgentCounters())
                ctr.tasks_alltime = values.get("tasks_alltime", values.get("tasks_total", 0))
                ctr.cost_alltime = values.get("cost_alltime", values.get("cost_total", 0.0))
                ctr.tokens_alltime = values.get("tokens_alltime", 0)
                ctr.last_activity = values.get("last_activity")

        logger.info("activity_counters_restored", agents=len(data))

    def snapshot_for_persist(self) -> dict[str, dict[str, Any]]:
        """Return a serialisable snapshot suitable for persisting."""
        return self.get_all()

    def merge_into_agents_list(self, agents: list[dict]) -> None:
        """
        Mutate *agents* (the dashboard in-memory list) in-place so each
        agent dict carries live counters from the tracker.
        """
        with self._mu:
            for agent in agents:
                role = agent.get("role", "")
                ctr = self._counters.get(role)
                if ctr:
                    d = ctr.to_dict()
                    agent["tasks_today"] = d["tasks_today"]
                    agent["tasks_alltime"] = d["tasks_alltime"]
                    agent["cost_today"] = d["cost_today"]
                    agent["cost_alltime"] = d["cost_alltime"]
                    agent["tokens_today"] = d["tokens_today"]
                    agent["last_activity"] = d["last_activity"]
                    agent["consecutive_failures"] = d["consecutive_failures"]


# Module-level singleton — importable everywhere as:
#   from core.activity_tracker import tracker
tracker = ActivityTracker()
