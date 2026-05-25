"""
Event Bus

Redis Pub/Sub based event bus for inter-component communication.
Decouples market data ingestion from agent orchestration, allowing
independent scaling and crash isolation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(component="event_bus")


class EventChannels:
    """Predefined event channels for the system."""
    MARKET_EVENTS = "selfevolve:events:market"
    TRADE_EVENTS = "selfevolve:events:trade"
    AGENT_EVENTS = "selfevolve:events:agent"
    AGENT_INSIGHTS = "selfevolve:events:agent_insights"  # Inter-agent intelligence sharing
    EVOLUTION_EVENTS = "selfevolve:events:evolution"
    ALERT_EVENTS = "selfevolve:events:alert"
    HEALTH_EVENTS = "selfevolve:events:health"
    HITL_EVENTS = "selfevolve:events:hitl"


class Event(dict):
    """Structured event payload."""

    def __init__(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        source: str = "system",
        **kwargs: Any,
    ):
        super().__init__(
            event_type=event_type,
            data=data or {},
            source=source,
            timestamp=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )


# Type alias for event handler callbacks
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """
    Async event bus using Redis Pub/Sub.
    
    Provides decoupled communication between system components:
    - Market Data Daemon → publishes price/volume events
    - Trading DAG → subscribes to market events, publishes trade events
    - Evolution Engine → subscribes to trade events
    - Alerting → subscribes to all channels
    """

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client
        self._pubsub: aioredis.client.PubSub | None = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._listener_task: asyncio.Task | None = None
        self._running = False

    async def publish(self, channel: str, event: Event | dict) -> int:
        """
        Publish an event to a channel.
        
        Args:
            channel: Target channel (use EventChannels constants)
            event: Event payload
            
        Returns:
            Number of subscribers that received the event
        """
        payload = json.dumps(event if isinstance(event, dict) else dict(event))
        count = await self._redis.publish(channel, payload)
        await logger.adebug(
            "event_published",
            channel=channel,
            event_type=event.get("event_type", "unknown"),
            subscribers=count,
        )
        return count

    def subscribe(self, channel: str, handler: EventHandler) -> None:
        """
        Register an async handler for a channel.
        
        Args:
            channel: Channel to subscribe to
            handler: Async callback function
        """
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)

    async def start_listening(self) -> None:
        """Start the background event listener."""
        if self._running:
            return

        self._pubsub = self._redis.pubsub()
        channels = list(self._handlers.keys())

        if not channels:
            await logger.awarning("no_channels_subscribed")
            return

        await self._pubsub.subscribe(*channels)
        self._running = True
        self._listener_task = asyncio.create_task(self._listen_loop())
        await logger.ainfo("event_bus_started", channels=channels)

    async def stop_listening(self) -> None:
        """Stop the background event listener."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
        await logger.ainfo("event_bus_stopped")

    async def _listen_loop(self) -> None:
        """Background loop processing incoming events."""
        try:
            while self._running and self._pubsub:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message["type"] == "message":
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()

                    try:
                        data = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue

                    # Dispatch to all handlers for this channel
                    handlers = self._handlers.get(channel, [])
                    for handler in handlers:
                        try:
                            await handler(data)
                        except Exception as e:
                            # Error isolation: one handler failure doesn't
                            # crash the entire event bus
                            await logger.aerror(
                                "event_handler_error",
                                channel=channel,
                                error=str(e),
                                exc_info=True,
                            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await logger.aerror("event_bus_crash", error=str(e), exc_info=True)

    # ── Convenience Publishers ──────────────────────────────────────

    async def publish_market_event(
        self, ticker: str, event_type: str, data: dict
    ) -> None:
        """Publish a market event (volume spike, price move, etc.)."""
        await self.publish(
            EventChannels.MARKET_EVENTS,
            Event(event_type=event_type, data={"ticker": ticker, **data}, source="market_data"),
        )

    async def publish_trade_event(
        self, trade_id: str, action: str, data: dict
    ) -> None:
        """Publish a trade event (executed, rejected, filled)."""
        await self.publish(
            EventChannels.TRADE_EVENTS,
            Event(event_type=action, data={"trade_id": trade_id, **data}, source="execution"),
        )

    async def publish_alert(
        self, alert_type: str, message: str, severity: str = "INFO"
    ) -> None:
        """Publish an alert event."""
        await self.publish(
            EventChannels.ALERT_EVENTS,
            Event(
                event_type=alert_type,
                data={"message": message, "severity": severity},
                source="alerting",
            ),
        )
