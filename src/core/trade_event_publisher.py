"""
Trade Event Publisher

Publishes trade lifecycle events to the Event Bus and records
predictions for the evolution loop's Brier scoring pipeline.

This bridges the trading execution flow with:
1. The Event Bus (TRADE_EVENTS channel) for reactive subscribers
2. The Prediction Tracker (Phase 1) for Brier score calculation

Usage:
    publisher = TradeEventPublisher(event_bus)
    
    # On order submission — records predictions
    await publisher.on_order_submitted(
        trade_id="abc-123", ticker="AAPL", side="BUY",
        notional=10000, analysis="...", confidence=8,
        current_price=150.0, agent_predictions={...},
    )
    
    # On fill
    await publisher.on_order_filled(
        trade_id="abc-123", ticker="AAPL",
        fill_price=150.05, fill_qty=66,
    )
    
    # On close — resolves prediction outcomes
    await publisher.on_trade_closed(
        trade_id="abc-123", ticker="AAPL",
        pnl=350.0, entry_price=150.0, exit_price=155.30,
    )
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from core.event_bus import EventBus, EventChannels, Event
from evolution.prediction_tracker import prediction_tracker

logger = structlog.get_logger(component="trade_event_publisher")


class TradeEventPublisher:
    """Publishes trade lifecycle events and records predictions."""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus

    async def on_order_submitted(
        self,
        trade_id: str,
        ticker: str,
        side: str,
        notional: float,
        analysis: str,
        confidence: float,
        current_price: float,
        agent_predictions: Optional[dict[str, float]] = None,
    ) -> None:
        """Called when an order is submitted to the broker.
        
        Records predictions from each analyst agent for Brier scoring.
        
        Args:
            trade_id: Unique trade identifier (client_order_id)
            ticker: Stock/crypto ticker
            side: BUY or SELL
            notional: Dollar amount
            analysis: Raw LLM analysis text
            confidence: Confidence level (1-10 scale, converted to 0-1)
            current_price: Price at submission time
            agent_predictions: Optional dict of {agent_role: predicted_probability}
                             If not provided, a single prediction from the
                             analysis confidence level is recorded.
        """
        # Normalize confidence from 1-10 to 0-1
        normalized_confidence = max(0.0, min(1.0, confidence / 10.0))
        
        # Default: a single "SYSTEM" prediction derived from the LLM confidence
        if not agent_predictions:
            agent_predictions = {
                "SYSTEM_ANALYST": normalized_confidence,
            }

        # Record each agent's prediction
        for agent_role, predicted_prob in agent_predictions.items():
            try:
                prediction_tracker.record_prediction(
                    agent_role=agent_role,
                    trade_id=trade_id,
                    ticker=ticker,
                    predicted_probability=predicted_prob,
                    confidence=normalized_confidence,
                )
            except Exception as e:
                logger.warning(
                    "prediction_recording_failed",
                    agent=agent_role, trade=trade_id[:8], error=str(e),
                )

        # Publish event
        await self._publish(
            EventChannels.TRADE_EVENTS,
            "ORDER_SUBMITTED",
            {
                "trade_id": trade_id,
                "ticker": ticker,
                "side": side,
                "notional": notional,
                "price": current_price,
                "confidence": normalized_confidence,
                "analysis_preview": analysis[:200] if analysis else "",
                "agents_recorded": list(agent_predictions.keys()),
            },
        )

        logger.info(
            "trade_submitted",
            trade_id=trade_id[:8], ticker=ticker, side=side,
            notional=f"${notional:,.0f}", confidence=normalized_confidence,
            predictions_recorded=len(agent_predictions),
        )

    async def on_order_filled(
        self,
        trade_id: str,
        ticker: str,
        fill_price: float,
        fill_qty: float,
    ) -> None:
        """Called when a broker order is filled."""
        await self._publish(
            EventChannels.TRADE_EVENTS,
            "ORDER_FILLED",
            {
                "trade_id": trade_id,
                "ticker": ticker,
                "fill_price": fill_price,
                "fill_qty": fill_qty,
            },
        )

        logger.info(
            "trade_filled",
            trade_id=trade_id[:8], ticker=ticker,
            price=f"${fill_price:.2f}", qty=fill_qty,
        )

    async def on_trade_closed(
        self,
        trade_id: str,
        ticker: str,
        pnl: float,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        hold_duration_hours: float = 0.0,
        close_reason: str = "NORMAL",
    ) -> None:
        """Called when a trade is closed (profit taken, stop loss, or manual).
        
        Resolves prediction outcomes for Brier scoring.
        
        Args:
            trade_id: Trade identifier
            ticker: Ticker symbol
            pnl: Realized P&L in dollars
            entry_price: Entry price
            exit_price: Exit price
            hold_duration_hours: How long the position was held
            close_reason: NORMAL, STOP_LOSS, TAKE_PROFIT, MANUAL
        """
        profitable = pnl > 0

        # Resolve predictions for Brier scoring
        try:
            resolved_count = prediction_tracker.resolve_trade(trade_id, profitable)
            logger.info(
                "predictions_resolved",
                trade_id=trade_id[:8], ticker=ticker,
                profitable=profitable, resolved=resolved_count,
            )
        except Exception as e:
            logger.warning(
                "prediction_resolution_failed",
                trade_id=trade_id[:8], error=str(e),
            )

        # Publish event
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        await self._publish(
            EventChannels.TRADE_EVENTS,
            "TRADE_CLOSED",
            {
                "trade_id": trade_id,
                "ticker": ticker,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "profitable": profitable,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "hold_duration_hours": round(hold_duration_hours, 1),
                "close_reason": close_reason,
            },
        )

        logger.info(
            "trade_closed",
            trade_id=trade_id[:8], ticker=ticker,
            pnl=f"${pnl:+,.2f}", profitable=profitable,
            reason=close_reason,
        )

    async def on_trade_rejected(
        self,
        trade_id: str,
        ticker: str,
        reason: str,
    ) -> None:
        """Called when an order is rejected by the broker or guardrails."""
        await self._publish(
            EventChannels.TRADE_EVENTS,
            "ORDER_REJECTED",
            {
                "trade_id": trade_id,
                "ticker": ticker,
                "reason": reason,
            },
        )

        logger.warning("trade_rejected", trade_id=trade_id[:8], ticker=ticker, reason=reason)

    async def _publish(self, channel: str, event_type: str, data: dict) -> None:
        """Publish an event to the Event Bus (safe — no-ops if bus unavailable)."""
        if not self._event_bus:
            return
        try:
            event = Event(event_type=event_type, data=data, source="trade_publisher")
            await self._event_bus.publish(channel, event)
        except Exception as e:
            logger.warning("event_publish_failed", channel=channel, error=str(e))
