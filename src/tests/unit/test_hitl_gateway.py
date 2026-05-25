"""
Tests for Phase 3: HITL Gateway

Tests the Human-In-The-Loop approval system:
1. Trigger logic — all 7 conditions
2. Approval flow — create → approve → verify
3. Rejection flow — create → reject → verify
4. Modify flow — create → modify SL/TP → verify
5. Timeout flow — create → wait → auto-approve
6. Concurrent requests — multiple pending, no interference
7. Dashboard resolve — resolve via DASHBOARD source
8. Double-resolve — second resolve is no-op
9. History tracking — resolved requests are stored
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
# TEST 1: Trigger Logic — all 7 conditions
# ═══════════════════════════════════════════════════════════════════

class TestHITLTriggerLogic:
    """Test the should_trigger_hitl function."""

    def test_low_confidence_triggers(self):
        """Confidence below JUDGE_MIN triggers HITL."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=4.0, notional=5000, equity=100000,
        )
        assert should is True
        assert "Low confidence" in reason

    def test_high_confidence_no_trigger(self):
        """High confidence alone doesn't trigger (if other conditions pass)."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=3, drawdown_pct=1.0,
        )
        assert should is False
        assert reason == ""

    def test_high_notional_triggers(self):
        """Trade > 15% of portfolio triggers HITL."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=20000, equity=100000,
            num_positions=3,
        )
        assert should is True
        assert "High notional" in reason

    def test_first_trade_triggers(self):
        """No existing positions triggers HITL."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=0,
        )
        assert should is True
        assert "First trade" in reason

    def test_analyst_disagreement_triggers(self):
        """Large spread between analyst scores triggers HITL."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=3, analyst_scores=[0.3, 0.95],
        )
        assert should is True
        assert "Analyst disagreement" in reason

    def test_high_drawdown_triggers(self):
        """Portfolio drawdown > 5% triggers HITL."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=3, drawdown_pct=7.5,
        )
        assert should is True
        assert "High drawdown" in reason

    def test_reactive_trade_triggers(self):
        """Event-driven trade always triggers HITL."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=3, is_reactive=True,
        )
        assert should is True
        assert "Event-driven" in reason

    def test_manual_flag_triggers(self):
        """Manual flag always triggers HITL."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=3, is_manual_flag=True,
        )
        assert should is True
        assert "Manually flagged" in reason

    def test_multiple_triggers_combined(self):
        """Multiple trigger reasons are combined with '|'."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=3.0, notional=20000, equity=100000,
            num_positions=0, drawdown_pct=8.0,
        )
        assert should is True
        assert reason.count("|") >= 2  # At least 3 reasons


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Approval Flow
# ═══════════════════════════════════════════════════════════════════

class TestHITLApprovalFlow:
    """Test the HITL approval lifecycle."""

    @pytest.mark.asyncio
    async def test_create_request(self):
        """Creating a request returns a PENDING HITLRequest."""
        from core.hitl_gateway import HITLGateway, HITLStatus

        gw = HITLGateway()
        # Mock Telegram and dashboard
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    req = await gw.request_approval(
                        ticker="AAPL", side="BUY", notional=10000,
                        price=192.50, stop_loss=188.65, take_profit=202.13,
                        confidence=6.5, trigger_reason="Low confidence",
                    )

        assert req.status == HITLStatus.PENDING
        assert req.ticker == "AAPL"
        assert req.notional == 10000
        assert req.id is not None

    @pytest.mark.asyncio
    async def test_approve_request(self):
        """Approving a pending request sets status to APPROVED."""
        from core.hitl_gateway import HITLGateway, HITLStatus, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req = await gw.request_approval(
                            ticker="TSLA", side="BUY", notional=10000,
                            price=250.0, stop_loss=245.0, take_profit=262.5,
                            confidence=7.0, trigger_reason="First trade",
                        )

                        resolved = await gw.resolve(
                            req.id, "APPROVED", HITLSource.TELEGRAM,
                        )

        assert resolved.status == HITLStatus.APPROVED
        assert resolved.resolved_by == "TELEGRAM"
        assert resolved.resolved_at is not None

    @pytest.mark.asyncio
    async def test_reject_request(self):
        """Rejecting a request sets status to REJECTED with notes."""
        from core.hitl_gateway import HITLGateway, HITLStatus, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req = await gw.request_approval(
                            ticker="NVDA", side="BUY", notional=10000,
                            price=800.0, stop_loss=784.0, take_profit=840.0,
                            confidence=5.0, trigger_reason="Low confidence",
                        )

                        resolved = await gw.resolve(
                            req.id, "REJECTED", HITLSource.DASHBOARD,
                            notes="Too risky right now",
                        )

        assert resolved.status == HITLStatus.REJECTED
        assert resolved.resolved_by == "DASHBOARD"
        assert resolved.human_notes == "Too risky right now"

    @pytest.mark.asyncio
    async def test_modify_request(self):
        """Modifying SL/TP sets status to MODIFIED with new values."""
        from core.hitl_gateway import HITLGateway, HITLStatus, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req = await gw.request_approval(
                            ticker="AAPL", side="BUY", notional=10000,
                            price=192.50, stop_loss=188.65, take_profit=202.13,
                            confidence=6.5, trigger_reason="Low confidence",
                        )

                        resolved = await gw.resolve(
                            req.id, "MODIFIED", HITLSource.TELEGRAM,
                            modified_sl=185.00, modified_tp=210.00,
                        )

        assert resolved.status == HITLStatus.MODIFIED
        assert resolved.modified_sl == 185.00
        assert resolved.modified_tp == 210.00


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Timeout Flow
# ═══════════════════════════════════════════════════════════════════

class TestHITLTimeout:
    """Test the timeout auto-approval."""

    @pytest.mark.asyncio
    async def test_timeout_auto_approves(self):
        """Timeout → status APPROVED with source TIMEOUT."""
        from core.hitl_gateway import HITLGateway, HITLStatus, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req = await gw.request_approval(
                            ticker="AAPL", side="BUY", notional=10000,
                            price=192.50, stop_loss=188.65, take_profit=202.13,
                            confidence=4.0, trigger_reason="Low confidence",
                        )

                        # Wait with a very short timeout
                        resolved = await gw.wait_for_resolution(req.id, timeout=0.1)

        assert resolved.status == HITLStatus.APPROVED
        assert resolved.resolved_by == "TIMEOUT"
        assert "Auto-approved" in (resolved.human_notes or "")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Async Wait + Resolve
# ═══════════════════════════════════════════════════════════════════

class TestHITLAsyncWait:
    """Test that wait_for_resolution unblocks on resolve."""

    @pytest.mark.asyncio
    async def test_resolve_unblocks_wait(self):
        """Resolving a request wakes up wait_for_resolution."""
        from core.hitl_gateway import HITLGateway, HITLStatus, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req = await gw.request_approval(
                            ticker="MSFT", side="BUY", notional=10000,
                            price=420.0, stop_loss=411.6, take_profit=441.0,
                            confidence=7.0, trigger_reason="First trade",
                        )

                        # Resolve in 50ms (before the 10s timeout)
                        async def delayed_approve():
                            await asyncio.sleep(0.05)
                            await gw.resolve(req.id, "APPROVED", HITLSource.TELEGRAM)

                        asyncio.create_task(delayed_approve())

                        resolved = await gw.wait_for_resolution(req.id, timeout=10)

        assert resolved.status == HITLStatus.APPROVED
        assert resolved.resolved_by == "TELEGRAM"


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Concurrent Requests
# ═══════════════════════════════════════════════════════════════════

class TestHITLConcurrent:
    """Test multiple HITL requests don't interfere."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_independent(self):
        """Two pending requests can be resolved independently."""
        from core.hitl_gateway import HITLGateway, HITLStatus, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req1 = await gw.request_approval(
                            ticker="AAPL", side="BUY", notional=10000,
                            price=192.50, stop_loss=188.65, take_profit=202.13,
                            confidence=5.0, trigger_reason="Low confidence",
                        )
                        req2 = await gw.request_approval(
                            ticker="TSLA", side="BUY", notional=10000,
                            price=250.0, stop_loss=245.0, take_profit=262.5,
                            confidence=4.0, trigger_reason="Low confidence",
                        )

                        # Approve first, reject second
                        r1 = await gw.resolve(req1.id, "APPROVED", HITLSource.TELEGRAM)
                        r2 = await gw.resolve(req2.id, "REJECTED", HITLSource.DASHBOARD)

        assert r1.status == HITLStatus.APPROVED
        assert r2.status == HITLStatus.REJECTED
        assert r1.ticker == "AAPL"
        assert r2.ticker == "TSLA"

    @pytest.mark.asyncio
    async def test_get_pending_only_pending(self):
        """get_pending() returns only PENDING requests."""
        from core.hitl_gateway import HITLGateway, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req1 = await gw.request_approval(
                            ticker="A", side="BUY", notional=5000,
                            price=100, stop_loss=98, take_profit=105,
                            confidence=5.0, trigger_reason="test",
                        )
                        req2 = await gw.request_approval(
                            ticker="B", side="BUY", notional=5000,
                            price=200, stop_loss=196, take_profit=210,
                            confidence=5.0, trigger_reason="test",
                        )

                        # Resolve req1
                        await gw.resolve(req1.id, "APPROVED", HITLSource.TELEGRAM)

                        pending = gw.get_pending()

        assert len(pending) == 1
        assert pending[0].ticker == "B"


# ═══════════════════════════════════════════════════════════════════
# TEST 6: Double Resolve
# ═══════════════════════════════════════════════════════════════════

class TestHITLDoubleResolve:
    """Test that resolving an already-resolved request is a no-op."""

    @pytest.mark.asyncio
    async def test_double_resolve_no_change(self):
        """Second resolve doesn't change the status."""
        from core.hitl_gateway import HITLGateway, HITLStatus, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req = await gw.request_approval(
                            ticker="AAPL", side="BUY", notional=10000,
                            price=192.50, stop_loss=188.65, take_profit=202.13,
                            confidence=5.0, trigger_reason="test",
                        )

                        r1 = await gw.resolve(req.id, "APPROVED", HITLSource.TELEGRAM)
                        r2 = await gw.resolve(req.id, "REJECTED", HITLSource.DASHBOARD)

        assert r1.status == HITLStatus.APPROVED
        assert r2.status == HITLStatus.APPROVED  # Not changed to REJECTED
        assert r2.resolved_by == "TELEGRAM"  # Original resolver stays


# ═══════════════════════════════════════════════════════════════════
# TEST 7: History Tracking
# ═══════════════════════════════════════════════════════════════════

class TestHITLHistory:
    """Test the history tracking."""

    @pytest.mark.asyncio
    async def test_resolved_added_to_history(self):
        """Resolved requests appear in history."""
        from core.hitl_gateway import HITLGateway, HITLSource

        gw = HITLGateway()
        with patch.object(gw, "_send_telegram_notification", new_callable=AsyncMock):
            with patch.object(gw, "_publish_event", new_callable=AsyncMock):
                with patch.object(gw, "_sync_to_dashboard"):
                    with patch.object(gw, "_update_telegram_message", new_callable=AsyncMock):
                        req = await gw.request_approval(
                            ticker="AAPL", side="BUY", notional=10000,
                            price=192.50, stop_loss=188.65, take_profit=202.13,
                            confidence=5.0, trigger_reason="test",
                        )
                        await gw.resolve(req.id, "APPROVED", HITLSource.TELEGRAM)

                        history = gw.get_history()

        assert len(history) == 1
        assert history[0]["ticker"] == "AAPL"
        assert history[0]["status"] == "APPROVED"


# ═══════════════════════════════════════════════════════════════════
# TEST 8: to_dict Serialization
# ═══════════════════════════════════════════════════════════════════

class TestHITLSerialization:
    """Test HITLRequest.to_dict() for API/WebSocket."""

    def test_to_dict_has_all_fields(self):
        """to_dict() returns all required fields."""
        from core.hitl_gateway import HITLRequest, HITLStatus

        req = HITLRequest(
            id="test-123",
            ticker="AAPL",
            side="BUY",
            notional=10000,
            price=192.50,
            stop_loss=188.65,
            take_profit=202.13,
            confidence=6.5,
            trigger_reason="Low confidence",
            analysis_preview="ACTION: BUY\nCONFIDENCE: 6.5",
        )

        d = req.to_dict()
        assert d["id"] == "test-123"
        assert d["ticker"] == "AAPL"
        assert d["status"] == "PENDING"
        assert d["notional"] == 10000
        assert d["trigger_reason"] == "Low confidence"
        assert d["analysis_preview"] == "ACTION: BUY\nCONFIDENCE: 6.5"

    def test_to_dict_resolved_has_timestamps(self):
        """Resolved request to_dict includes resolved_at."""
        from core.hitl_gateway import HITLRequest, HITLStatus

        req = HITLRequest(
            id="test-456",
            ticker="TSLA",
            status=HITLStatus.APPROVED,
            resolved_at=datetime(2026, 5, 24, tzinfo=timezone.utc),
            resolved_by="TELEGRAM",
        )

        d = req.to_dict()
        assert d["status"] == "APPROVED"
        assert d["resolved_at"] is not None
        assert d["resolved_by"] == "TELEGRAM"


# ═══════════════════════════════════════════════════════════════════
# TEST 9: Resolve Unknown Request
# ═══════════════════════════════════════════════════════════════════

class TestHITLEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_resolve_unknown_id(self):
        """Resolving an unknown ID returns None."""
        from core.hitl_gateway import HITLGateway, HITLSource

        gw = HITLGateway()
        result = await gw.resolve("nonexistent", "APPROVED", HITLSource.TELEGRAM)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_request_unknown_id(self):
        """Getting an unknown ID returns None."""
        from core.hitl_gateway import HITLGateway

        gw = HITLGateway()
        result = gw.get_request("nonexistent")
        assert result is None

    def test_zero_equity_no_crash(self):
        """Zero equity doesn't crash the trigger logic."""
        from core.hitl_gateway import should_trigger_hitl
        should, reason = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=0,
            num_positions=3,
        )
        # Shouldn't crash; equity=0 means no high-notional trigger
        assert isinstance(should, bool)

    def test_empty_analyst_scores(self):
        """Empty or single analyst score doesn't trigger divergence."""
        from core.hitl_gateway import should_trigger_hitl
        should1, _ = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=3, analyst_scores=[],
        )
        should2, _ = should_trigger_hitl(
            confidence=9.0, notional=5000, equity=100000,
            num_positions=3, analyst_scores=[0.8],
        )
        # Neither should trigger from analyst_scores alone
        assert should1 is False
        assert should2 is False
