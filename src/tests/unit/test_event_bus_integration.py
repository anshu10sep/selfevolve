"""
Tests for Phase 2: Event Bus Integration

Tests the event-driven infrastructure:
1. MarketDataDaemon: volume spike / price move / gap open detection
2. TradeEventPublisher: prediction recording on submission, resolution on close
3. Event handler dispatch: correct handler called for each channel
4. HealthPublisher: state transition detection
5. Deduplication: same event within cooldown → no duplicate fire
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════
# TEST 1: Market Data Daemon — Snapshot Analysis
# ═══════════════════════════════════════════════════════════════════

class TestMarketDataDaemonDetection:
    """Test the daemon's ability to detect market events from snapshots."""

    def test_volume_spike_detection(self):
        """Volume > 5x average → VOLUME_SPIKE event."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus)

        snapshot = {
            "dailyBar": {"o": 150.0, "c": 152.0, "v": 50_000_000},
            "prevDailyBar": {"c": 149.0, "v": 5_000_000},
            "latestTrade": {"p": 152.0},
        }

        events = daemon._analyze_snapshot("AAPL", snapshot)

        volume_events = [e for e in events if e["event_type"] == "VOLUME_SPIKE"]
        assert len(volume_events) == 1
        assert volume_events[0]["data"]["multiplier"] == 10.0
        assert volume_events[0]["data"]["ticker"] == "AAPL"

    def test_no_volume_spike_normal_volume(self):
        """Normal volume → no VOLUME_SPIKE event."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus)

        snapshot = {
            "dailyBar": {"o": 150.0, "c": 151.0, "v": 6_000_000},
            "prevDailyBar": {"c": 149.5, "v": 5_000_000},
            "latestTrade": {"p": 151.0},
        }

        events = daemon._analyze_snapshot("AAPL", snapshot)
        volume_events = [e for e in events if e["event_type"] == "VOLUME_SPIKE"]
        assert len(volume_events) == 0

    def test_price_move_detection(self):
        """Intraday move > 3% → PRICE_MOVE event."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus)

        snapshot = {
            "dailyBar": {"o": 150.0, "c": 156.0, "v": 5_000_000},
            "prevDailyBar": {"c": 149.5, "v": 5_000_000},
            "latestTrade": {"p": 156.0},
        }

        events = daemon._analyze_snapshot("TSLA", snapshot)
        price_events = [e for e in events if e["event_type"] == "PRICE_MOVE"]
        assert len(price_events) == 1
        assert price_events[0]["data"]["direction"] == "UP"
        assert price_events[0]["data"]["change_pct"] == 4.0  # (156-150)/150*100

    def test_gap_open_detection(self):
        """Gap > 2% from previous close → GAP_OPEN event."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus)

        snapshot = {
            "dailyBar": {"o": 155.0, "c": 156.0, "v": 5_000_000},
            "prevDailyBar": {"c": 150.0, "v": 5_000_000},
            "latestTrade": {"p": 156.0},
        }

        events = daemon._analyze_snapshot("NVDA", snapshot)
        gap_events = [e for e in events if e["event_type"] == "GAP_OPEN"]
        assert len(gap_events) == 1
        assert gap_events[0]["data"]["direction"] == "UP"
        # Gap: (155-150)/150*100 = 3.33%
        assert abs(gap_events[0]["data"]["gap_pct"] - 3.33) < 0.1

    def test_no_events_on_flat_day(self):
        """Flat day → no events."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus)

        snapshot = {
            "dailyBar": {"o": 150.0, "c": 150.5, "v": 5_000_000},
            "prevDailyBar": {"c": 149.9, "v": 5_000_000},
            "latestTrade": {"p": 150.5},
        }

        events = daemon._analyze_snapshot("MSFT", snapshot)
        assert len(events) == 0

    def test_handles_zero_price(self):
        """Zero/missing price → no crash, no events."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus)

        snapshot = {
            "dailyBar": {"o": 0, "c": 0, "v": 0},
            "prevDailyBar": {"c": 0, "v": 0},
            "latestTrade": {"p": 0},
        }

        events = daemon._analyze_snapshot("BAD", snapshot)
        assert len(events) == 0


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Market Data Daemon — Deduplication
# ═══════════════════════════════════════════════════════════════════

class TestDeduplication:
    """Test the event deduplication system."""

    @pytest.mark.asyncio
    async def test_in_memory_dedup_fires_once(self):
        """Same dedup key within cooldown → fires only once."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus, redis_client=None)

        # First call should fire
        result1 = await daemon._should_fire("volume_spike:AAPL")
        assert result1 is True

        # Second call within cooldown should not fire
        result2 = await daemon._should_fire("volume_spike:AAPL")
        assert result2 is False

    @pytest.mark.asyncio
    async def test_different_keys_both_fire(self):
        """Different dedup keys → both fire."""
        from integrations.market_data_daemon import MarketDataDaemon

        mock_bus = MagicMock()
        daemon = MarketDataDaemon(event_bus=mock_bus, redis_client=None)

        result1 = await daemon._should_fire("volume_spike:AAPL")
        result2 = await daemon._should_fire("volume_spike:TSLA")
        assert result1 is True
        assert result2 is True


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Trade Event Publisher
# ═══════════════════════════════════════════════════════════════════

class TestTradeEventPublisher:
    """Test the TradeEventPublisher."""

    @pytest.mark.asyncio
    async def test_order_submission_records_prediction(self):
        """on_order_submitted records a prediction for each agent."""
        from core.trade_event_publisher import TradeEventPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = TradeEventPublisher(event_bus=mock_bus)

        with patch("core.trade_event_publisher.prediction_tracker") as mock_tracker:
            mock_tracker.record_prediction = MagicMock(return_value={"id": "test"})

            await publisher.on_order_submitted(
                trade_id="trade-123",
                ticker="AAPL",
                side="BUY",
                notional=10000.0,
                analysis="ACTION: BUY\nCONFIDENCE: 8\nREASONING: Strong momentum",
                confidence=8.0,
                current_price=150.0,
            )

            # Should have recorded a prediction
            mock_tracker.record_prediction.assert_called_once()
            call_args = mock_tracker.record_prediction.call_args
            assert call_args.kwargs["trade_id"] == "trade-123"
            assert call_args.kwargs["ticker"] == "AAPL"
            assert call_args.kwargs["predicted_probability"] == 0.8  # 8/10

            # Should have published to TRADE_EVENTS
            mock_bus.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_order_submission_custom_agent_predictions(self):
        """on_order_submitted records multiple agent predictions."""
        from core.trade_event_publisher import TradeEventPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = TradeEventPublisher(event_bus=mock_bus)

        agent_preds = {
            "FUNDAMENTAL_ANALYST": 0.8,
            "TECHNICAL_ANALYST": 0.65,
            "SENTIMENT_ANALYST": 0.7,
        }

        with patch("core.trade_event_publisher.prediction_tracker") as mock_tracker:
            mock_tracker.record_prediction = MagicMock(return_value={"id": "test"})

            await publisher.on_order_submitted(
                trade_id="trade-456",
                ticker="NVDA",
                side="BUY",
                notional=10000.0,
                analysis="test analysis",
                confidence=7.0,
                current_price=800.0,
                agent_predictions=agent_preds,
            )

            # Should have recorded 3 predictions
            assert mock_tracker.record_prediction.call_count == 3

    @pytest.mark.asyncio
    async def test_trade_close_resolves_predictions(self):
        """on_trade_closed resolves prediction outcomes."""
        from core.trade_event_publisher import TradeEventPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = TradeEventPublisher(event_bus=mock_bus)

        with patch("core.trade_event_publisher.prediction_tracker") as mock_tracker:
            mock_tracker.resolve_trade = MagicMock(return_value=3)

            await publisher.on_trade_closed(
                trade_id="trade-123",
                ticker="AAPL",
                pnl=350.0,
                entry_price=150.0,
                exit_price=155.3,
            )

            # Should have resolved predictions
            mock_tracker.resolve_trade.assert_called_once_with("trade-123", True)

    @pytest.mark.asyncio
    async def test_trade_close_loss_resolves_as_not_profitable(self):
        """Negative P&L → profitable=False in prediction resolution."""
        from core.trade_event_publisher import TradeEventPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = TradeEventPublisher(event_bus=mock_bus)

        with patch("core.trade_event_publisher.prediction_tracker") as mock_tracker:
            mock_tracker.resolve_trade = MagicMock(return_value=2)

            await publisher.on_trade_closed(
                trade_id="trade-789",
                ticker="TSLA",
                pnl=-200.0,
                entry_price=250.0,
                exit_price=248.0,
            )

            mock_tracker.resolve_trade.assert_called_once_with("trade-789", False)

    @pytest.mark.asyncio
    async def test_publisher_survives_no_event_bus(self):
        """Publisher with no event_bus doesn't crash."""
        from core.trade_event_publisher import TradeEventPublisher

        publisher = TradeEventPublisher(event_bus=None)

        with patch("core.trade_event_publisher.prediction_tracker") as mock_tracker:
            mock_tracker.record_prediction = MagicMock(return_value={"id": "test"})
            mock_tracker.resolve_trade = MagicMock(return_value=1)

            # These should not crash
            await publisher.on_order_submitted(
                trade_id="t1", ticker="X", side="BUY",
                notional=100, analysis="", confidence=5, current_price=10,
            )
            await publisher.on_order_filled(
                trade_id="t1", ticker="X", fill_price=10, fill_qty=10,
            )
            await publisher.on_trade_closed(
                trade_id="t1", ticker="X", pnl=5.0,
            )


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Health Publisher — State Transitions
# ═══════════════════════════════════════════════════════════════════

class TestHealthPublisher:
    """Test health publisher state transitions."""

    @pytest.mark.asyncio
    async def test_initial_state_healthy(self):
        """Initial state is HEALTHY, no events published."""
        from core.health_publisher import HealthPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = HealthPublisher(event_bus=mock_bus)

        status = await publisher.check_and_publish(redis_ok=True)
        assert status == "HEALTHY"
        assert publisher.is_healthy is True
        # No state change → no event published
        mock_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_healthy_to_degraded_transition(self):
        """HEALTHY → DEGRADED publishes HEALTH_DEGRADED event."""
        from core.health_publisher import HealthPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = HealthPublisher(event_bus=mock_bus)

        status = await publisher.check_and_publish(redis_ok=False)
        assert status == "DEGRADED"
        assert publisher.is_healthy is False
        mock_bus.publish.assert_called_once()

        # Verify event type
        call_args = mock_bus.publish.call_args
        event = call_args[0][1]  # Second positional arg is the Event
        assert event["event_type"] == "HEALTH_DEGRADED"
        assert "redis" in event["data"]["components"]

    @pytest.mark.asyncio
    async def test_degraded_to_recovered_transition(self):
        """DEGRADED → HEALTHY publishes HEALTH_RECOVERED event."""
        from core.health_publisher import HealthPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = HealthPublisher(event_bus=mock_bus)

        # First: go to DEGRADED
        await publisher.check_and_publish(redis_ok=False)
        mock_bus.publish.reset_mock()

        # Then: recover
        status = await publisher.check_and_publish(redis_ok=True)
        assert status == "HEALTHY"
        assert publisher.is_healthy is True
        mock_bus.publish.assert_called_once()

        call_args = mock_bus.publish.call_args
        event = call_args[0][1]
        assert event["event_type"] == "HEALTH_RECOVERED"

    @pytest.mark.asyncio
    async def test_staying_degraded_no_duplicate_event(self):
        """DEGRADED → still DEGRADED (same components) → no new event."""
        from core.health_publisher import HealthPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = HealthPublisher(event_bus=mock_bus)

        # Go degraded
        await publisher.check_and_publish(redis_ok=False)
        mock_bus.publish.reset_mock()

        # Still degraded, same component
        await publisher.check_and_publish(redis_ok=False)
        # Should NOT publish another HEALTH_DEGRADED for the same component
        mock_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_degradation(self):
        """Circuit breaker trip → HEALTH_DEGRADED with circuit_breaker component."""
        from core.health_publisher import HealthPublisher

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        publisher = HealthPublisher(event_bus=mock_bus)

        status = await publisher.check_and_publish(
            redis_ok=True, circuit_breaker_tripped=True,
        )
        assert status == "DEGRADED"
        mock_bus.publish.assert_called_once()

        call_args = mock_bus.publish.call_args
        event = call_args[0][1]
        assert "circuit_breaker" in event["data"]["components"]

    @pytest.mark.asyncio
    async def test_publisher_survives_no_bus(self):
        """Publisher with no bus doesn't crash."""
        from core.health_publisher import HealthPublisher

        publisher = HealthPublisher(event_bus=None)
        status = await publisher.check_and_publish(redis_ok=False)
        assert status == "DEGRADED"
        # No crash even without bus


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Event Bus — Event Structure
# ═══════════════════════════════════════════════════════════════════

class TestEventStructure:
    """Test the Event class structure."""

    def test_event_has_required_fields(self):
        """Events contain event_type, data, source, timestamp."""
        from core.event_bus import Event

        event = Event(
            event_type="VOLUME_SPIKE",
            data={"ticker": "AAPL", "multiplier": 5.2},
            source="market_data_daemon",
        )

        assert event["event_type"] == "VOLUME_SPIKE"
        assert event["data"]["ticker"] == "AAPL"
        assert event["source"] == "market_data_daemon"
        assert "timestamp" in event

    def test_event_default_source(self):
        """Default source is 'system'."""
        from core.event_bus import Event

        event = Event(event_type="TEST")
        assert event["source"] == "system"
        assert event["data"] == {}


# ═══════════════════════════════════════════════════════════════════
# TEST 6: Event Handlers — Dispatch Logic
# ═══════════════════════════════════════════════════════════════════

class TestEventHandlerDispatch:
    """Test that event handlers route to the correct sub-handlers."""

    @pytest.mark.asyncio
    async def test_market_event_dispatches_volume_spike(self):
        """VOLUME_SPIKE event → _handle_volume_spike called."""
        from core import event_handlers

        with patch.object(event_handlers, "_handle_volume_spike", new_callable=AsyncMock) as mock_handler:
            event = {
                "event_type": "VOLUME_SPIKE",
                "data": {"ticker": "AAPL", "multiplier": 6.0},
            }
            await event_handlers.handle_market_event(event)
            mock_handler.assert_called_once_with(event["data"])

    @pytest.mark.asyncio
    async def test_market_event_dispatches_price_move(self):
        """PRICE_MOVE event → _handle_price_move called."""
        from core import event_handlers

        with patch.object(event_handlers, "_handle_price_move", new_callable=AsyncMock) as mock_handler:
            event = {
                "event_type": "PRICE_MOVE",
                "data": {"ticker": "TSLA", "change_pct": 5.0},
            }
            await event_handlers.handle_market_event(event)
            mock_handler.assert_called_once_with(event["data"])

    @pytest.mark.asyncio
    async def test_trade_event_dispatches_closed(self):
        """TRADE_CLOSED event → _handle_trade_closed called."""
        from core import event_handlers

        with patch.object(event_handlers, "_handle_trade_closed", new_callable=AsyncMock) as mock_handler:
            event = {
                "event_type": "TRADE_CLOSED",
                "data": {"trade_id": "t1", "pnl": 100},
            }
            await event_handlers.handle_trade_event(event)
            mock_handler.assert_called_once_with(event["data"])

    @pytest.mark.asyncio
    async def test_health_event_dispatches_degraded(self):
        """HEALTH event with status DEGRADED → _handle_health_degradation called."""
        from core import event_handlers

        with patch.object(event_handlers, "_handle_health_degradation", new_callable=AsyncMock) as mock_handler:
            event = {
                "event_type": "HEALTH_DEGRADED",
                "data": {"status": "DEGRADED", "component": "redis"},
            }
            await event_handlers.handle_health_event(event)
            mock_handler.assert_called_once_with(event["data"])

    @pytest.mark.asyncio
    async def test_health_event_dispatches_recovered(self):
        """HEALTH event with status RECOVERED → _handle_health_recovery called."""
        from core import event_handlers

        with patch.object(event_handlers, "_handle_health_recovery", new_callable=AsyncMock) as mock_handler:
            event = {
                "event_type": "HEALTH_RECOVERED",
                "data": {"status": "RECOVERED", "component": "redis"},
            }
            await event_handlers.handle_health_event(event)
            mock_handler.assert_called_once_with(event["data"])
