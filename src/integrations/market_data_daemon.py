"""
Market Data Daemon

Background async task that monitors Alpaca snapshots for significant
market events and publishes them to the Event Bus.

Detects:
- Volume spikes (current volume > VOLUME_SPIKE_MULTIPLIER × 20-day avg)
- Significant price moves (> 3% intraday change)
- Gap opens (> 2% gap from previous close)

Runs every 60 seconds during market hours.
Uses Redis key deduplication to prevent re-firing the same event
within a 30-minute cooldown window.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from config.constants import (
    DEFAULT_WATCHLIST,
    VOLUME_SPIKE_MULTIPLIER,
)
from core.event_bus import EventBus, EventChannels, Event

logger = structlog.get_logger(component="market_data_daemon")

# Thresholds
PRICE_MOVE_THRESHOLD_PCT = 3.0      # Trigger on > 3% intraday move
GAP_OPEN_THRESHOLD_PCT = 2.0        # Trigger on > 2% gap from prev close
POLL_INTERVAL_SEC = 60              # Poll every 60 seconds
EVENT_COOLDOWN_SEC = 1800           # 30-minute cooldown per event per ticker
DAEMON_CHECK_MARKET_INTERVAL = 300  # Re-check market open every 5 minutes


class MarketDataDaemon:
    """Background monitor that publishes market events to the Event Bus."""

    def __init__(self, event_bus: EventBus, redis_client=None):
        self._event_bus = event_bus
        self._redis = redis_client
        self._running = False
        self._market_open = False
        # In-memory fallback for dedup when Redis unavailable
        self._recent_events: dict[str, float] = {}

    async def run_loop(self) -> None:
        """Main daemon loop — polls during market hours, sleeps otherwise."""
        self._running = True
        logger.info("market_data_daemon_started")

        market_check_counter = 0

        while self._running:
            try:
                # Periodically check if market is open
                if market_check_counter <= 0:
                    await self._check_market_status()
                    market_check_counter = DAEMON_CHECK_MARKET_INTERVAL // POLL_INTERVAL_SEC

                if self._market_open:
                    await self._poll_and_detect()

                market_check_counter -= 1
                await asyncio.sleep(POLL_INTERVAL_SEC)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("market_daemon_error", error=str(e))
                await asyncio.sleep(POLL_INTERVAL_SEC)

        logger.info("market_data_daemon_stopped")

    async def stop(self) -> None:
        """Signal the daemon to stop."""
        self._running = False

    async def _check_market_status(self) -> None:
        """Check if the US equities market is currently open."""
        try:
            from integrations.market_data import MarketDataClient
            mdc = MarketDataClient()
            self._market_open = await mdc.is_market_open()
            await mdc.close()
        except Exception as e:
            logger.warning("market_status_check_failed", error=str(e))
            # Assume open during weekday business hours as fallback
            now = datetime.now(timezone.utc)
            weekday = now.weekday()
            hour = now.hour
            self._market_open = weekday < 5 and 13 <= hour < 21  # ~9:30 ET to 4 PM ET

    async def _poll_and_detect(self) -> None:
        """Poll Alpaca snapshots for the watchlist and detect events."""
        try:
            from integrations.market_data import MarketDataClient
            mdc = MarketDataClient()

            # Get snapshots for watchlist
            snapshots = await mdc.get_snapshots(DEFAULT_WATCHLIST)
            await mdc.close()

            if not snapshots:
                return

            events_detected = 0

            for ticker, snap in snapshots.items():
                try:
                    events = self._analyze_snapshot(ticker, snap)
                    for event in events:
                        if await self._should_fire(event["dedup_key"]):
                            await self._publish_event(event)
                            events_detected += 1
                except Exception as e:
                    logger.debug("snapshot_analysis_failed", ticker=ticker, error=str(e))

            if events_detected > 0:
                logger.info("market_events_detected", count=events_detected)

        except Exception as e:
            logger.error("poll_and_detect_failed", error=str(e))

    def _analyze_snapshot(self, ticker: str, snap: dict) -> list[dict]:
        """Analyze a single ticker snapshot for significant events."""
        events = []

        daily_bar = snap.get("dailyBar", {})
        prev_bar = snap.get("prevDailyBar", {})
        latest_trade = snap.get("latestTrade", {})

        current_price = float(latest_trade.get("p", daily_bar.get("c", 0)))
        today_open = float(daily_bar.get("o", 0))
        today_volume = int(daily_bar.get("v", 0))
        prev_close = float(prev_bar.get("c", 0))
        prev_volume = int(prev_bar.get("v", 1))  # Avoid div/0

        if current_price <= 0 or prev_close <= 0:
            return events

        # ── Volume Spike Detection ─────────────────────────────────
        volume_multiplier = today_volume / max(prev_volume, 1)
        if volume_multiplier >= VOLUME_SPIKE_MULTIPLIER:
            events.append({
                "event_type": "VOLUME_SPIKE",
                "dedup_key": f"volume_spike:{ticker}",
                "data": {
                    "ticker": ticker,
                    "current_volume": today_volume,
                    "avg_volume": prev_volume,
                    "multiplier": round(volume_multiplier, 1),
                    "price": current_price,
                },
            })

        # ── Significant Price Move ─────────────────────────────────
        intraday_change_pct = ((current_price - today_open) / today_open * 100) if today_open > 0 else 0
        if abs(intraday_change_pct) >= PRICE_MOVE_THRESHOLD_PCT:
            direction = "UP" if intraday_change_pct > 0 else "DOWN"
            events.append({
                "event_type": "PRICE_MOVE",
                "dedup_key": f"price_move:{ticker}:{direction}",
                "data": {
                    "ticker": ticker,
                    "price": current_price,
                    "change_pct": round(intraday_change_pct, 2),
                    "direction": direction,
                    "open_price": today_open,
                },
            })

        # ── Gap Open Detection ─────────────────────────────────────
        gap_pct = ((today_open - prev_close) / prev_close * 100) if prev_close > 0 else 0
        if abs(gap_pct) >= GAP_OPEN_THRESHOLD_PCT:
            direction = "UP" if gap_pct > 0 else "DOWN"
            events.append({
                "event_type": "GAP_OPEN",
                "dedup_key": f"gap_open:{ticker}",
                "data": {
                    "ticker": ticker,
                    "gap_pct": round(gap_pct, 2),
                    "direction": direction,
                    "prev_close": prev_close,
                    "open_price": today_open,
                },
            })

        return events

    async def _should_fire(self, dedup_key: str) -> bool:
        """Check if this event should fire (respects cooldown window)."""
        now = datetime.now(timezone.utc).timestamp()

        # Try Redis-based deduplication first
        if self._redis:
            try:
                redis_key = f"selfevolve:event_dedup:{dedup_key}"
                existing = await self._redis.get(redis_key)
                if existing:
                    return False
                await self._redis.setex(redis_key, EVENT_COOLDOWN_SEC, "1")
                return True
            except Exception:
                pass  # Fall through to in-memory

        # In-memory fallback
        last_fired = self._recent_events.get(dedup_key, 0)
        if now - last_fired < EVENT_COOLDOWN_SEC:
            return False
        self._recent_events[dedup_key] = now

        # Cleanup old entries
        cutoff = now - EVENT_COOLDOWN_SEC * 2
        self._recent_events = {
            k: v for k, v in self._recent_events.items() if v > cutoff
        }

        return True

    async def _publish_event(self, event_info: dict) -> None:
        """Publish a market event to the Event Bus."""
        event = Event(
            event_type=event_info["event_type"],
            data=event_info["data"],
            source="market_data_daemon",
        )
        await self._event_bus.publish(EventChannels.MARKET_EVENTS, event)
        logger.info(
            "market_event_published",
            event_type=event_info["event_type"],
            ticker=event_info["data"].get("ticker", "?"),
        )
