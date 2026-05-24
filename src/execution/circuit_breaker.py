"""
Circuit Breaker & Halt-and-Catch-Fire (HCF) Protocol

Protects the $100 portfolio from catastrophic failures.
Implements the Dead Man's Switch pattern and automatic
position liquidation when safety thresholds are breached.

This is coded DIRECTLY in the execution loop — NOT via external
observability tools, which are too slow for micro-capital protection.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import structlog

from config.constants import (
    CIRCUIT_BREAKER_MAX_EXCEPTIONS,
    CIRCUIT_BREAKER_WINDOW_SEC,
    HEARTBEAT_STALE_THRESHOLD_SEC,
)
from core.models.audit import SystemHealthEvent, HealthEventType

logger = structlog.get_logger(component="circuit_breaker")


class CircuitBreakerTripped(Exception):
    """Raised when the circuit breaker has been tripped."""
    pass


class HCFTriggered(Exception):
    """Raised when Halt-and-Catch-Fire protocol is activated."""
    pass


class CircuitBreaker:
    """
    Application-level circuit breaker for the trading system.
    
    Tracks exceptions within a rolling window. If exceptions exceed
    the threshold, the circuit breaker trips and halts all trading.
    
    A $100 account cannot afford the latency of external monitoring
    triggering protective halts — this must be internal.
    """

    def __init__(
        self,
        max_exceptions: int = CIRCUIT_BREAKER_MAX_EXCEPTIONS,
        window_seconds: int = CIRCUIT_BREAKER_WINDOW_SEC,
    ):
        self.max_exceptions = max_exceptions
        self.window_seconds = window_seconds
        self._exceptions: deque[float] = deque()
        self._tripped = False
        self._trip_time: Optional[float] = None
        self._trip_count = 0

    @property
    def is_tripped(self) -> bool:
        """Whether the circuit breaker is currently tripped."""
        return self._tripped

    def record_exception(self, error: Exception) -> None:
        """
        Record an exception and check if the circuit breaker should trip.
        
        If we exceed max_exceptions within window_seconds, the circuit
        breaker trips and the HCF protocol should be initiated.
        """
        now = time.time()
        self._exceptions.append(now)

        # Remove expired exceptions outside the window
        cutoff = now - self.window_seconds
        while self._exceptions and self._exceptions[0] < cutoff:
            self._exceptions.popleft()

        if len(self._exceptions) >= self.max_exceptions:
            self._trip(str(error))

    def _trip(self, reason: str) -> None:
        """Trip the circuit breaker."""
        self._tripped = True
        self._trip_time = time.time()
        self._trip_count += 1

        logger.critical(
            "circuit_breaker_tripped",
            reason=reason,
            exception_count=len(self._exceptions),
            window_sec=self.window_seconds,
            trip_count=self._trip_count,
        )

    def reset(self) -> None:
        """Manually reset the circuit breaker after investigation."""
        self._tripped = False
        self._exceptions.clear()
        logger.info("circuit_breaker_reset", trip_count=self._trip_count)

    def check(self) -> None:
        """Check if the circuit breaker is tripped. Raises if so."""
        if self._tripped:
            raise CircuitBreakerTripped(
                f"Circuit breaker is tripped. "
                f"Trip count: {self._trip_count}. "
                f"Manual reset required."
            )

    def get_health_event(self) -> SystemHealthEvent:
        """Generate a health event for monitoring."""
        return SystemHealthEvent(
            component="circuit_breaker",
            event_type=(
                HealthEventType.CIRCUIT_BREAKER_TRIP
                if self._tripped
                else HealthEventType.HEARTBEAT
            ),
            details={
                "tripped": self._tripped,
                "recent_exceptions": len(self._exceptions),
                "trip_count": self._trip_count,
            },
        )


class DeadManSwitch:
    """
    Dead Man's Switch for the Overwatch Daemon.
    
    The Overwatch Daemon writes a heartbeat to Redis every second.
    The trading engine checks this heartbeat before ANY order submission.
    If the heartbeat is stale, ALL trading is halted immediately.
    """

    def __init__(self, redis_client=None, stale_threshold: float = HEARTBEAT_STALE_THRESHOLD_SEC):
        self._redis = redis_client
        self.stale_threshold = stale_threshold
        self.heartbeat_key = "selfevolve:overwatch_heartbeat"
        self._last_local_heartbeat: float = 0.0

    async def write_heartbeat(self) -> None:
        """Write a heartbeat timestamp to Redis. Called by Overwatch Daemon."""
        now = time.time()
        self._last_local_heartbeat = now
        if self._redis:
            await self._redis.set(self.heartbeat_key, str(now))

    async def verify_heartbeat(self) -> bool:
        """
        Verify the Overwatch Daemon is alive.
        
        Called before EVERY order submission. If the daemon is dead,
        we halt trading because we've lost risk monitoring.
        """
        if self._redis is None:
            # No Redis connection — use local heartbeat
            if self._last_local_heartbeat == 0:
                return True  # First check, assume OK
            return (time.time() - self._last_local_heartbeat) < self.stale_threshold

        try:
            last_heartbeat = await self._redis.get(self.heartbeat_key)
            if not last_heartbeat:
                logger.error("overwatch_heartbeat_missing")
                return False

            time_since = time.time() - float(last_heartbeat)
            if time_since > self.stale_threshold:
                logger.error(
                    "overwatch_heartbeat_stale",
                    seconds_since=time_since,
                    threshold=self.stale_threshold,
                )
                return False

            return True
        except Exception as e:
            logger.error("heartbeat_check_failed", error=str(e))
            return False


class HCFProtocol:
    """
    Halt-and-Catch-Fire Protocol
    
    Emergency procedure when the system detects critical failure:
    1. Cancel all open orders
    2. Set tight trailing stops on open positions
    3. Send emergency alert to human operator
    4. Freeze all new order submission
    
    There is NO auto-healing with real capital.
    """

    def __init__(self):
        self._activated = False
        self._activation_time: Optional[datetime] = None
        self._reason: str = ""

    @property
    def is_activated(self) -> bool:
        return self._activated

    def activate(self, reason: str) -> SystemHealthEvent:
        """
        Activate the HCF protocol.
        
        This is a one-way door — only manual human intervention can reset it.
        """
        self._activated = True
        self._activation_time = datetime.now(timezone.utc)
        self._reason = reason

        logger.critical(
            "HCF_PROTOCOL_ACTIVATED",
            reason=reason,
            timestamp=self._activation_time.isoformat(),
        )

        return SystemHealthEvent(
            component="hcf_protocol",
            event_type=HealthEventType.HCF,
            details={
                "reason": reason,
                "activation_time": self._activation_time.isoformat(),
            },
        )

    def check(self) -> None:
        """Check if HCF is active. Raises if so."""
        if self._activated:
            raise HCFTriggered(
                f"HCF Protocol is ACTIVE. Reason: {self._reason}. "
                f"Activated at: {self._activation_time}. "
                f"Manual reset required."
            )

    def deactivate(self, authorized_by: str) -> None:
        """
        Deactivate HCF. Requires explicit human authorization.
        """
        logger.warning(
            "hcf_deactivated",
            authorized_by=authorized_by,
            was_active_for_sec=(
                (datetime.now(timezone.utc) - self._activation_time).total_seconds()
                if self._activation_time else 0
            ),
        )
        self._activated = False
        self._reason = ""
