"""
HITL Gateway — Human-In-The-Loop Approval System

Manages the full lifecycle of trade approval requests:
  1. Evaluate whether a trade needs human approval
  2. Create a HITL request and notify via Telegram + Dashboard
  3. Async wait for owner response (approve/reject/modify)
  4. Return resolution to the trading engine

The gateway supports dual-channel approval — the owner can respond
from Telegram (inline buttons) or the Dashboard (API), and the first
response wins. Both channels are notified of the resolution.

Timeout: If no response within HITL_TIMEOUT_SECONDS (default 60s),
the trade auto-approves to avoid missing the price window.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog

from config.constants import (
    HITL_TIMEOUT_SECONDS,
    HITL_CONFIDENCE_DIVERGENCE_THRESHOLD,
    JUDGE_MIN_CONFIDENCE_FOR_EXECUTION,
)

logger = structlog.get_logger(component="hitl_gateway")


# ═══════════════════════════════════════════════════════════════════
# ENUMS & DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

class HITLStatus(str, Enum):
    """Status of a HITL approval request."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class HITLSource(str, Enum):
    """Source of the HITL resolution."""
    TELEGRAM = "TELEGRAM"
    DASHBOARD = "DASHBOARD"
    TIMEOUT = "TIMEOUT"
    SYSTEM = "SYSTEM"


@dataclass
class HITLRequest:
    """A single HITL approval request."""
    id: str
    status: HITLStatus = HITLStatus.PENDING
    # Trade details
    ticker: str = ""
    side: str = "BUY"
    notional: float = 0.0
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: float = 0.0
    # HITL metadata
    trigger_reason: str = ""
    analysis_preview: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # "TELEGRAM" | "DASHBOARD" | "TIMEOUT"
    human_notes: Optional[str] = None
    # Modifications (if owner changes SL/TP)
    modified_sl: Optional[float] = None
    modified_tp: Optional[float] = None
    # Telegram message ID for editing
    telegram_message_id: Optional[int] = None
    telegram_chat_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for API/WebSocket serialization."""
        return {
            "id": self.id,
            "status": self.status.value if isinstance(self.status, HITLStatus) else self.status,
            "ticker": self.ticker,
            "side": self.side,
            "notional": self.notional,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence": self.confidence,
            "trigger_reason": self.trigger_reason,
            "analysis_preview": self.analysis_preview[:300],
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "human_notes": self.human_notes,
            "modified_sl": self.modified_sl,
            "modified_tp": self.modified_tp,
        }


# ═══════════════════════════════════════════════════════════════════
# HITL TRIGGER LOGIC
# ═══════════════════════════════════════════════════════════════════

# Thresholds
HITL_HIGH_NOTIONAL_PCT = 0.15      # Trade > 15% of portfolio
HITL_DRAWDOWN_THRESHOLD_PCT = 5.0  # Portfolio drawdown > 5%
HITL_ANALYST_DIVERGENCE = 0.60     # Max - min confidence > 0.60


def should_trigger_hitl(
    confidence: float,
    notional: float,
    equity: float,
    num_positions: int = 0,
    drawdown_pct: float = 0.0,
    is_reactive: bool = False,
    is_manual_flag: bool = False,
    analyst_scores: Optional[list[float]] = None,
) -> tuple[bool, str]:
    """Determine if a trade needs HITL approval and why.
    
    Args:
        confidence: Judge/LLM confidence score (1-10 scale)
        notional: Dollar amount of the trade
        equity: Current portfolio equity
        num_positions: Number of open positions
        drawdown_pct: Current portfolio drawdown percentage
        is_reactive: True if triggered by event (volume spike, etc.)
        is_manual_flag: True if explicitly flagged for review
        analyst_scores: List of analyst confidence scores for divergence check
        
    Returns:
        Tuple of (should_trigger: bool, reason: str)
    """
    reasons = []

    # 1. Low confidence
    if confidence < JUDGE_MIN_CONFIDENCE_FOR_EXECUTION:
        reasons.append(f"Low confidence ({confidence:.1f}/{JUDGE_MIN_CONFIDENCE_FOR_EXECUTION})")

    # 2. High notional relative to portfolio
    if equity > 0 and (notional / equity) > HITL_HIGH_NOTIONAL_PCT:
        pct = notional / equity * 100
        reasons.append(f"High notional ({pct:.0f}% of portfolio)")

    # 3. First trade of the day
    if num_positions == 0:
        reasons.append("First trade of the day")

    # 4. Analyst disagreement
    if analyst_scores and len(analyst_scores) >= 2:
        divergence = max(analyst_scores) - min(analyst_scores)
        if divergence > HITL_ANALYST_DIVERGENCE:
            reasons.append(f"Analyst disagreement (spread: {divergence:.2f})")

    # 5. Drawdown approaching
    if drawdown_pct > HITL_DRAWDOWN_THRESHOLD_PCT:
        reasons.append(f"High drawdown ({drawdown_pct:.1f}%)")

    # 6. Reactive/event-driven trade (always requires HITL)
    if is_reactive:
        reasons.append("Event-driven trade (requires approval)")

    # 7. Manual flag
    if is_manual_flag:
        reasons.append("Manually flagged for review")

    if reasons:
        return True, " | ".join(reasons)
    return False, ""


# ═══════════════════════════════════════════════════════════════════
# HITL GATEWAY
# ═══════════════════════════════════════════════════════════════════

class HITLGateway:
    """Manages the HITL approval queue and async resolution."""

    def __init__(self):
        # Active requests: id -> HITLRequest
        self._requests: dict[str, HITLRequest] = {}
        # Async events: id -> asyncio.Event (set when resolved)
        self._events: dict[str, asyncio.Event] = {}
        # History (resolved requests)
        self._history: list[HITLRequest] = []

    async def request_approval(
        self,
        ticker: str,
        side: str,
        notional: float,
        price: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        trigger_reason: str,
        analysis: str = "",
    ) -> HITLRequest:
        """Create a new HITL request and notify the owner.
        
        Returns:
            The created HITLRequest (status=PENDING)
        """
        request_id = str(uuid.uuid4())[:8]  # Short ID for Telegram buttons

        request = HITLRequest(
            id=request_id,
            ticker=ticker,
            side=side,
            notional=notional,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            trigger_reason=trigger_reason,
            analysis_preview=analysis[:500] if analysis else "",
        )

        # Store request and create async event
        self._requests[request_id] = request
        self._events[request_id] = asyncio.Event()

        # Update dashboard state
        self._sync_to_dashboard(request)

        # Publish HITL_TRIGGERED event to Event Bus
        await self._publish_event("HITL_TRIGGERED", request)

        # Send Telegram notification with inline buttons
        await self._send_telegram_notification(request)

        logger.info(
            "hitl_request_created",
            request_id=request_id,
            ticker=ticker,
            side=side,
            notional=f"${notional:,.0f}",
            trigger=trigger_reason,
        )

        return request

    async def wait_for_resolution(
        self, request_id: str, timeout: Optional[float] = None,
    ) -> HITLRequest:
        """Wait for the owner to approve/reject or until timeout.
        
        Args:
            request_id: The HITL request ID
            timeout: Override timeout in seconds (default: HITL_TIMEOUT_SECONDS)
            
        Returns:
            The resolved HITLRequest
        """
        if timeout is None:
            timeout = HITL_TIMEOUT_SECONDS

        event = self._events.get(request_id)
        if not event:
            raise ValueError(f"Unknown HITL request: {request_id}")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            # Auto-approve on timeout
            await self.resolve(
                request_id=request_id,
                action="APPROVED",
                source=HITLSource.TIMEOUT,
                notes=f"Auto-approved after {timeout}s timeout",
            )

        request = self._requests.get(request_id)
        if request is None:
            raise ValueError(f"HITL request {request_id} was removed")

        return request

    async def resolve(
        self,
        request_id: str,
        action: str,
        source: HITLSource = HITLSource.SYSTEM,
        notes: Optional[str] = None,
        modified_sl: Optional[float] = None,
        modified_tp: Optional[float] = None,
    ) -> Optional[HITLRequest]:
        """Resolve a pending HITL request.
        
        Args:
            request_id: The HITL request ID
            action: "APPROVED", "REJECTED", or "MODIFIED"
            source: Where the resolution came from
            notes: Optional human notes
            modified_sl: Modified stop loss (for MODIFIED action)
            modified_tp: Modified take profit (for MODIFIED action)
            
        Returns:
            The resolved request, or None if not found
        """
        request = self._requests.get(request_id)
        if not request:
            logger.warning("hitl_resolve_not_found", request_id=request_id)
            return None

        if request.status != HITLStatus.PENDING:
            logger.warning(
                "hitl_already_resolved",
                request_id=request_id,
                current_status=request.status,
            )
            return request

        # Set resolution
        action_upper = action.upper()
        if action_upper == "APPROVED":
            request.status = HITLStatus.APPROVED
        elif action_upper == "REJECTED":
            request.status = HITLStatus.REJECTED
        elif action_upper == "MODIFIED":
            request.status = HITLStatus.MODIFIED
            request.modified_sl = modified_sl
            request.modified_tp = modified_tp
        else:
            request.status = HITLStatus.APPROVED  # Default to approved

        request.resolved_at = datetime.now(timezone.utc)
        request.resolved_by = source.value if isinstance(source, HITLSource) else str(source)
        request.human_notes = notes

        # Signal the waiting coroutine
        event = self._events.get(request_id)
        if event:
            event.set()

        # Move to history
        self._history.append(request)
        if len(self._history) > 100:
            self._history = self._history[-100:]

        # Update dashboard state
        self._sync_to_dashboard(request)

        # Publish resolution event
        await self._publish_event("HITL_RESOLVED", request)

        # Update Telegram message
        await self._update_telegram_message(request)

        logger.info(
            "hitl_resolved",
            request_id=request_id,
            ticker=request.ticker,
            action=action_upper,
            source=request.resolved_by,
            notes=notes,
        )

        return request

    def get_pending(self) -> list[HITLRequest]:
        """Get all pending HITL requests."""
        return [
            r for r in self._requests.values()
            if r.status == HITLStatus.PENDING
        ]

    def get_request(self, request_id: str) -> Optional[HITLRequest]:
        """Get a specific request by ID."""
        return self._requests.get(request_id)

    def get_history(self, limit: int = 50) -> list[dict]:
        """Get resolved HITL requests as dicts."""
        return [r.to_dict() for r in self._history[-limit:]]

    # ── Internal Methods ──────────────────────────────────────────

    def _sync_to_dashboard(self, request: HITLRequest) -> None:
        """Sync HITL request to dashboard system_state."""
        try:
            from dashboard.api.main import system_state

            # Update or add to hitl_queue
            queue = system_state.setdefault("hitl_queue", [])
            # Find existing entry
            for i, item in enumerate(queue):
                if item.get("id") == request.id:
                    queue[i] = request.to_dict()
                    return
            # Not found — add new
            queue.append(request.to_dict())

            # Keep queue manageable
            if len(queue) > 100:
                # Remove old resolved items
                queue[:] = [
                    q for q in queue
                    if q.get("status") == "PENDING"
                ] + [
                    q for q in queue
                    if q.get("status") != "PENDING"
                ][-50:]

        except Exception as e:
            logger.debug("hitl_dashboard_sync_failed", error=str(e))

    async def _send_telegram_notification(self, request: HITLRequest) -> None:
        """Send a rich Telegram message with inline approval buttons."""
        try:
            from integrations.telegram_bot import send_hitl_approval_request
            msg_id, chat_id = await send_hitl_approval_request(request)
            request.telegram_message_id = msg_id
            request.telegram_chat_id = chat_id
        except Exception as e:
            logger.warning("hitl_telegram_notification_failed", error=str(e))

    async def _update_telegram_message(self, request: HITLRequest) -> None:
        """Edit the Telegram message to reflect the resolution."""
        try:
            from integrations.telegram_bot import update_hitl_message
            await update_hitl_message(request)
        except Exception as e:
            logger.debug("hitl_telegram_update_failed", error=str(e))

    async def _publish_event(self, event_type: str, request: HITLRequest) -> None:
        """Publish HITL event to the Event Bus."""
        try:
            from core.event_bus import EventBus, EventChannels, Event
            from persistence.redis_client import get_redis_client
            redis = await get_redis_client()
            bus = EventBus(redis)
            event = Event(
                event_type=event_type,
                data=request.to_dict(),
                source="hitl_gateway",
            )
            await bus.publish(EventChannels.HITL_EVENTS, event)
        except Exception as e:
            logger.debug("hitl_event_publish_failed", error=str(e))

    async def _broadcast_ws(self, event_type: str, data: dict) -> None:
        """Broadcast HITL update via WebSocket."""
        try:
            from dashboard.api.main import _broadcast
            await _broadcast({"type": event_type, "data": data})
        except Exception as e:
            logger.debug("hitl_ws_broadcast_failed", error=str(e))


# Singleton instance
hitl_gateway = HITLGateway()
