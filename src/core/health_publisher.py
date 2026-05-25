"""
Health Publisher

Publishes system health status events to the Event Bus.
Wraps the existing Overwatch/Dead Man's Switch health checks
with event bus integration.

Tracks state transitions: HEALTHY → DEGRADED → RECOVERED
Only publishes events on state changes to avoid flooding.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from core.event_bus import EventBus, EventChannels, Event

logger = structlog.get_logger(component="health_publisher")


class HealthPublisher:
    """Publishes health status changes to the Event Bus."""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._last_status: str = "HEALTHY"
        self._degraded_components: set[str] = set()

    async def check_and_publish(
        self,
        redis_ok: bool = True,
        api_errors: int = 0,
        circuit_breaker_tripped: bool = False,
    ) -> str:
        """Check system health and publish events on state changes.
        
        Args:
            redis_ok: Whether Redis is responsive
            api_errors: Number of API errors in the current window
            circuit_breaker_tripped: Whether the circuit breaker has tripped
            
        Returns:
            Current health status: HEALTHY, DEGRADED
        """
        degraded_reasons = []
        degraded_components = set()

        if not redis_ok:
            degraded_reasons.append("Redis unavailable")
            degraded_components.add("redis")

        if api_errors > 5:
            degraded_reasons.append(f"High API error rate ({api_errors} errors)")
            degraded_components.add("api")

        if circuit_breaker_tripped:
            degraded_reasons.append("Circuit breaker tripped")
            degraded_components.add("circuit_breaker")

        current_status = "DEGRADED" if degraded_reasons else "HEALTHY"

        # Detect state transitions
        if current_status == "DEGRADED" and self._last_status != "DEGRADED":
            # Transition: HEALTHY → DEGRADED
            await self._publish_health_event(
                "HEALTH_DEGRADED",
                {
                    "status": "DEGRADED",
                    "components": list(degraded_components),
                    "reason": "; ".join(degraded_reasons),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            self._degraded_components = degraded_components

        elif current_status == "HEALTHY" and self._last_status == "DEGRADED":
            # Transition: DEGRADED → RECOVERED
            await self._publish_health_event(
                "HEALTH_RECOVERED",
                {
                    "status": "RECOVERED",
                    "recovered_components": list(self._degraded_components),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            self._degraded_components.clear()

        # Check for partial recovery (some components recovered but others still degraded)
        elif current_status == "DEGRADED" and self._last_status == "DEGRADED":
            recovered = self._degraded_components - degraded_components
            newly_degraded = degraded_components - self._degraded_components

            if recovered:
                await self._publish_health_event(
                    "HEALTH_PARTIAL_RECOVERY",
                    {
                        "status": "DEGRADED",
                        "recovered_components": list(recovered),
                        "still_degraded": list(degraded_components),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

            if newly_degraded:
                await self._publish_health_event(
                    "HEALTH_DEGRADED",
                    {
                        "status": "DEGRADED",
                        "components": list(newly_degraded),
                        "reason": "; ".join(
                            r for r, c in zip(degraded_reasons, degraded_components)
                            if c in newly_degraded
                        ) or "Additional degradation detected",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

            self._degraded_components = degraded_components

        self._last_status = current_status
        return current_status

    async def publish_heartbeat_ok(self) -> None:
        """Publish a periodic heartbeat (low frequency, for monitoring)."""
        # Only publish every ~5 minutes to avoid flooding
        # The caller is responsible for rate-limiting
        await self._publish_health_event(
            "HEARTBEAT",
            {
                "status": self._last_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _publish_health_event(self, event_type: str, data: dict) -> None:
        """Publish a health event (safe — no-ops if bus unavailable)."""
        if not self._event_bus:
            return
        try:
            event = Event(event_type=event_type, data=data, source="health_publisher")
            await self._event_bus.publish(EventChannels.HEALTH_EVENTS, event)
            logger.info("health_event_published", event_type=event_type, status=data.get("status", "?"))
        except Exception as e:
            # Health publisher must never crash — just log
            logger.debug("health_event_publish_failed", error=str(e))

    @property
    def is_healthy(self) -> bool:
        """Return whether the system is currently healthy."""
        return self._last_status == "HEALTHY"

    @property
    def status(self) -> str:
        """Return the current health status."""
        return self._last_status
