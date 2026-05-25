"""
Insight Publisher

Central hub for inter-agent intelligence sharing.
Agents publish AgentInsight objects here, and other agents
query them during their reasoning loop.

Dual storage:
1. Redis Event Bus — for real-time subscribers (push)
2. In-memory deque — for on-demand queries (pull)

The in-memory cache ensures agents can query insights even
when Redis is unavailable. It auto-prunes expired insights
and caps at MAX_CACHED_INSIGHTS to prevent memory bloat.

Usage:
    from core.insight_publisher import insight_publisher

    # Publish an insight
    await insight_publisher.publish(AgentInsight(
        source_agent="MACRO_ANALYST",
        insight_type=InsightType.REGIME_CHANGE,
        title="Regime Change: BULL → BEAR",
        ...
    ))

    # Query insights
    regime = insight_publisher.get_active_regime()
    signals = insight_publisher.get_recent_insights(
        insight_type=InsightType.TECHNICAL_SIGNAL,
        ticker="AAPL",
    )
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from core.models.insights import (
    AgentInsight,
    InsightType,
    InsightUrgency,
)

logger = structlog.get_logger(component="insight_publisher")

# Maximum insights in the in-memory cache
MAX_CACHED_INSIGHTS = 500


class InsightPublisher:
    """
    Publish and retrieve agent insights.

    Thread-safe singleton that manages the flow of intelligence
    between agents in the SelfEvolve system.
    """

    def __init__(self):
        self._cache: deque[AgentInsight] = deque(maxlen=MAX_CACHED_INSIGHTS)
        self._lock = threading.Lock()
        self._event_bus = None  # Lazy-loaded
        self._total_published = 0
        self._total_expired = 0

    def set_event_bus(self, event_bus) -> None:
        """Wire the Event Bus (called during system startup)."""
        self._event_bus = event_bus

    async def publish(self, insight: AgentInsight) -> None:
        """
        Broadcast an insight to the AGENT_INSIGHTS channel
        and cache it in memory for on-demand queries.

        Args:
            insight: The AgentInsight to publish
        """
        # Store in local cache
        with self._lock:
            self._cache.append(insight)
            self._total_published += 1

        # Publish to Event Bus (if available)
        if self._event_bus:
            try:
                from core.event_bus import EventChannels, Event
                event = Event(
                    event_type="AGENT_INSIGHT",
                    data=insight.to_event_dict(),
                    source=insight.source_agent,
                )
                await self._event_bus.publish(
                    EventChannels.AGENT_INSIGHTS, event
                )
            except Exception as e:
                logger.debug(
                    "insight_event_bus_publish_failed",
                    error=str(e),
                )

        logger.info(
            "insight_published",
            source=insight.source_agent,
            type=insight.insight_type.value,
            ticker=insight.ticker,
            title=insight.title[:80],
            urgency=insight.urgency.value,
            confidence=f"{insight.confidence:.0%}",
        )

    def get_recent_insights(
        self,
        insight_type: Optional[InsightType] = None,
        source_agent: Optional[str] = None,
        ticker: Optional[str] = None,
        urgency: Optional[InsightUrgency] = None,
        max_age_minutes: int = 60,
        limit: int = 10,
    ) -> list[AgentInsight]:
        """
        Retrieve recent, non-expired insights matching filters.

        Args:
            insight_type: Filter by type (e.g., REGIME_CHANGE)
            source_agent: Filter by publishing agent role
            ticker: Filter by ticker (None matches system-wide insights)
            urgency: Filter by minimum urgency level
            max_age_minutes: Max age in minutes (default 60)
            limit: Max results (default 10)

        Returns:
            List of matching AgentInsight objects, newest first.
        """
        self._prune_expired()

        results = []
        now = datetime.now(timezone.utc)

        urgency_levels = {
            InsightUrgency.LOW: 0,
            InsightUrgency.MEDIUM: 1,
            InsightUrgency.HIGH: 2,
            InsightUrgency.CRITICAL: 3,
        }
        min_urgency_level = urgency_levels.get(urgency, 0) if urgency else 0

        with self._lock:
            # Iterate newest-first
            for insight in reversed(self._cache):
                # Skip expired
                if insight.is_expired:
                    continue

                # Age filter
                age = (now - insight.timestamp).total_seconds() / 60.0
                if age > max_age_minutes:
                    continue

                # Type filter
                if insight_type and insight.insight_type != insight_type:
                    continue

                # Source filter
                if source_agent and insight.source_agent != source_agent:
                    continue

                # Ticker filter
                if ticker:
                    # Match specific ticker OR system-wide insights (ticker=None)
                    if insight.ticker and insight.ticker != ticker.upper():
                        continue

                # Urgency filter
                insight_level = urgency_levels.get(insight.urgency, 0)
                if insight_level < min_urgency_level:
                    continue

                results.append(insight)
                if len(results) >= limit:
                    break

        return results

    def get_active_regime(self) -> Optional[AgentInsight]:
        """
        Shortcut: get the latest non-expired regime classification.

        Returns:
            The most recent REGIME_CHANGE insight, or None.
        """
        results = self.get_recent_insights(
            insight_type=InsightType.REGIME_CHANGE,
            max_age_minutes=1440,  # 24 hours
            limit=1,
        )
        return results[0] if results else None

    def get_all_active_signals(
        self,
        ticker: Optional[str] = None,
        max_age_minutes: int = 60,
    ) -> list[AgentInsight]:
        """
        Get all active signals from all agents for the Judge.

        Returns insights of types: TECHNICAL_SIGNAL, FUNDAMENTAL_FLAG,
        SENTIMENT_DIVERGENCE, STRATEGY_SIGNAL, REGIME_CHANGE.

        Args:
            ticker: Optional ticker filter
            max_age_minutes: Max age (default 60)

        Returns:
            List of active analysis insights, newest first.
        """
        signal_types = {
            InsightType.TECHNICAL_SIGNAL,
            InsightType.FUNDAMENTAL_FLAG,
            InsightType.SENTIMENT_DIVERGENCE,
            InsightType.STRATEGY_SIGNAL,
            InsightType.REGIME_CHANGE,
        }

        self._prune_expired()
        results = []
        now = datetime.now(timezone.utc)

        with self._lock:
            for insight in reversed(self._cache):
                if insight.is_expired:
                    continue
                age = (now - insight.timestamp).total_seconds() / 60.0
                if age > max_age_minutes:
                    continue
                if insight.insight_type not in signal_types:
                    continue
                if ticker and insight.ticker and insight.ticker != ticker.upper():
                    continue
                results.append(insight)

        return results

    def get_risk_alerts(
        self, max_age_minutes: int = 120,
    ) -> list[AgentInsight]:
        """Get all active risk and compliance alerts."""
        risk_types = {InsightType.RISK_ALERT, InsightType.COMPLIANCE_ALERT}

        self._prune_expired()
        results = []
        now = datetime.now(timezone.utc)

        with self._lock:
            for insight in reversed(self._cache):
                if insight.is_expired:
                    continue
                age = (now - insight.timestamp).total_seconds() / 60.0
                if age > max_age_minutes:
                    continue
                if insight.insight_type not in risk_types:
                    continue
                results.append(insight)

        return results

    def format_insights_for_context(
        self,
        insights: list[AgentInsight],
        max_insights: int = 5,
    ) -> str:
        """
        Format insights as a text block for LLM context injection.

        Args:
            insights: List of AgentInsight objects
            max_insights: Maximum to include (default 5)

        Returns:
            Formatted string ready for system prompt injection.
        """
        if not insights:
            return ""

        lines = ["Active Intelligence from Other Agents:"]
        for i, insight in enumerate(insights[:max_insights], 1):
            lines.append(f"  {i}. {insight.to_context_string()}")

        return "\n".join(lines)

    def _prune_expired(self) -> None:
        """Remove expired insights from the cache."""
        with self._lock:
            initial_len = len(self._cache)
            # deque doesn't support efficient removal, so rebuild
            active = [i for i in self._cache if not i.is_expired]
            pruned_count = initial_len - len(active)

            if pruned_count > 0:
                self._cache.clear()
                self._cache.extend(active)
                self._total_expired += pruned_count
                logger.debug(
                    "insights_pruned",
                    pruned=pruned_count,
                    remaining=len(active),
                )

    def get_stats(self) -> dict[str, Any]:
        """Get publisher statistics for monitoring."""
        with self._lock:
            active_count = sum(1 for i in self._cache if not i.is_expired)
            type_counts = {}
            for i in self._cache:
                if not i.is_expired:
                    t = i.insight_type.value
                    type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_published": self._total_published,
            "total_expired": self._total_expired,
            "active_insights": active_count,
            "cache_size": len(self._cache),
            "has_event_bus": self._event_bus is not None,
            "type_breakdown": type_counts,
        }


# ═══════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════

insight_publisher = InsightPublisher()
"""Global singleton. Import and use directly:
    from core.insight_publisher import insight_publisher
"""


async def handle_incoming_insight(event: dict) -> None:
    """
    Event Bus handler for incoming agent insights.

    When agents publish via Event Bus, this handler deserializes
    the insight and adds it to the local cache (for agents
    running in different processes).
    """
    if event.get("event_type") != "AGENT_INSIGHT":
        return

    try:
        data = event.get("data", {})
        insight = AgentInsight.from_event_dict(data)

        # Avoid duplicates
        with insight_publisher._lock:
            existing_ids = {i.insight_id for i in insight_publisher._cache}
            if insight.insight_id not in existing_ids:
                insight_publisher._cache.append(insight)

    except Exception as e:
        logger.debug("incoming_insight_parse_failed", error=str(e))
