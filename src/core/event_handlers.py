"""
Event Handlers (Subscribers)

Central module registering all event handlers for the Event Bus.
Each handler is an async function that reacts to a specific event type.

Handlers are designed for error isolation — one handler failure
does NOT crash the event bus or block other handlers.

Channels handled:
- MARKET_EVENTS: Volume spikes → trigger reactive analysis
- TRADE_EVENTS: Order fills, closes → update dashboard + journal
- EVOLUTION_EVENTS: Trust/prompt changes → update dashboard
- HEALTH_EVENTS: Degradation → alert + circuit breaker
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

PST_TZ = ZoneInfo('America/Los_Angeles')

import structlog

logger = structlog.get_logger(component="event_handlers")


# ═══════════════════════════════════════════════════════════════════
# MARKET EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def handle_market_event(event: dict[str, Any]) -> None:
    """React to market events (volume spikes, price moves, gaps)."""
    event_type = event.get("event_type", "")
    data = event.get("data", {})
    ticker = data.get("ticker", "?")

    logger.info("market_event_received", event_type=event_type, ticker=ticker)

    if event_type == "VOLUME_SPIKE":
        await _handle_volume_spike(data)
    elif event_type == "PRICE_MOVE":
        await _handle_price_move(data)
    elif event_type == "GAP_OPEN":
        await _handle_gap_open(data)


async def _handle_volume_spike(data: dict) -> None:
    """React to a volume spike — trigger immediate analysis if warranted."""
    ticker = data.get("ticker", "?")
    multiplier = data.get("multiplier", 0)
    price = data.get("price", 0)

    logger.info(
        "volume_spike_detected",
        ticker=ticker, multiplier=f"{multiplier:.1f}x",
        price=f"${price:.2f}",
    )

    # Alert via Telegram for significant spikes
    try:
        from integrations.telegram_bot import send_alert
        await send_alert(
            f"📊 *Volume Spike: {ticker}*\n\n"
            f"🔊 Volume: *{multiplier:.1f}x* average\n"
            f"💰 Price: *${price:,.2f}*\n"
            f"⏰ {datetime.now(PST_TZ).strftime('%I:%M %p PST')}\n\n"
            f"_Triggered reactive analysis..._"
        )
    except Exception:
        pass

    # Trigger reactive analysis
    await _trigger_reactive_analysis(ticker, data)


async def _handle_price_move(data: dict) -> None:
    """React to a significant price move — check if we hold a position."""
    ticker = data.get("ticker", "?")
    change_pct = data.get("change_pct", 0)
    direction = data.get("direction", "?")

    # Check if we hold this position
    try:
        from dashboard.api.main import system_state
        positions = system_state.get("portfolio", {}).get("positions", {})

        if ticker in positions:
            # We hold this — alert about the significant move
            from integrations.telegram_bot import send_alert
            emoji = "🟢" if direction == "UP" else "🔴"
            await send_alert(
                f"{emoji} *Price Alert: {ticker}*\n\n"
                f"📈 {direction} *{abs(change_pct):.1f}%* intraday\n"
                f"💰 Price: *${data.get('price', 0):,.2f}*\n"
                f"📦 *You hold this position*"
            )
    except Exception as e:
        logger.debug("price_move_check_failed", ticker=ticker, error=str(e))


async def _handle_gap_open(data: dict) -> None:
    """React to a gap open — log and alert if significant."""
    ticker = data.get("ticker", "?")
    gap_pct = data.get("gap_pct", 0)
    direction = data.get("direction", "?")

    try:
        from integrations.telegram_bot import send_alert
        emoji = "⬆️" if direction == "UP" else "⬇️"
        await send_alert(
            f"{emoji} *Gap Open: {ticker}*\n\n"
            f"Gap: *{abs(gap_pct):.1f}%* {direction}\n"
            f"Prev close: *${data.get('prev_close', 0):,.2f}*\n"
            f"Open: *${data.get('open_price', 0):,.2f}*"
        )
    except Exception:
        pass


async def _trigger_reactive_analysis(ticker: str, market_data: dict) -> None:
    """Trigger an immediate analysis for a ticker based on a market event.
    
    This is the reactive complement to the cron-based intraday scan.
    Instead of waiting for the next scheduled scan, we analyze NOW.
    """
    try:
        from dashboard.api.main import system_state

        # Guard: don't trade if we already hold this
        positions = system_state.get("portfolio", {}).get("positions", {})
        if ticker in positions:
            logger.info("reactive_skip_existing_position", ticker=ticker)
            return

        # Guard: don't trade if we have too many positions
        if len(positions) >= 5:
            logger.info("reactive_skip_max_positions", ticker=ticker)
            return

        # Guard: only during market hours
        from integrations.market_data import MarketDataClient
        mdc = MarketDataClient()
        if not await mdc.is_market_open():
            await mdc.close()
            return

        # Get fresh quote for analysis context
        quote = await mdc.get_latest_quote(ticker)
        current_price = quote.get("ask", market_data.get("price", 0))
        await mdc.close()

        if current_price <= 0:
            return

        # Run a lightweight LLM analysis
        from core.llm_factory import get_efficient_llm
        llm = get_efficient_llm()

        event_context = ""
        multiplier = market_data.get("multiplier")
        if multiplier:
            event_context = f"ALERT: Volume spike detected at {multiplier:.1f}x average. "
        change_pct = market_data.get("change_pct")
        if change_pct:
            event_context += f"Intraday move: {change_pct:+.1f}%. "

        response = await llm.ainvoke(
            f"REACTIVE ANALYSIS triggered by market event.\n"
            f"{event_context}\n"
            f"Ticker: {ticker} at ${current_price:.2f}\n\n"
            f"Should this trigger an immediate trade? "
            f"Consider: is this a real opportunity or noise? "
            f"Volume spikes can indicate institutional activity or just news-driven volatility.\n\n"
            f"Respond: ACTION: BUY or PASS, CONFIDENCE: 1-10, REASONING: one line"
        )

        from main import extract_text
        analysis = extract_text(response.content)

        if "ACTION: BUY" in analysis.upper():
            from integrations.telegram_bot import send_alert
            await send_alert(
                f"⚡ *Reactive Signal: {ticker}*\n\n"
                f"🎯 Analysis suggests BUY\n"
                f"💰 Price: *${current_price:,.2f}*\n"
                f"```\n{analysis[:200]}\n```\n\n"
                f"_Use /approve to act on this signal_"
            )
        else:
            logger.info("reactive_analysis_pass", ticker=ticker)

    except Exception as e:
        logger.error("reactive_analysis_failed", ticker=ticker, error=str(e))


# ═══════════════════════════════════════════════════════════════════
# TRADE EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def handle_trade_event(event: dict[str, Any]) -> None:
    """React to trade lifecycle events."""
    event_type = event.get("event_type", "")
    data = event.get("data", {})

    logger.info("trade_event_received", event_type=event_type, trade_id=data.get("trade_id", "?")[:8])

    if event_type == "ORDER_FILLED":
        await _handle_order_filled(data)
    elif event_type == "TRADE_CLOSED":
        await _handle_trade_closed(data)
    elif event_type == "ORDER_REJECTED":
        await _handle_order_rejected(data)


async def _handle_order_filled(data: dict) -> None:
    """Log fill to dashboard state."""
    try:
        from dashboard.api.main import system_state
        fills = system_state.setdefault("recent_fills", [])
        fills.append({
            "trade_id": data.get("trade_id", ""),
            "ticker": data.get("ticker", ""),
            "fill_price": data.get("fill_price", 0),
            "fill_qty": data.get("fill_qty", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 50 fills
        if len(fills) > 50:
            system_state["recent_fills"] = fills[-50:]
    except Exception as e:
        logger.debug("fill_logging_failed", error=str(e))


async def _handle_trade_closed(data: dict) -> None:
    """Update dashboard with trade close info."""
    try:
        from dashboard.api.main import system_state
        closed = system_state.setdefault("recent_closed_trades", [])
        closed.append({
            "trade_id": data.get("trade_id", ""),
            "ticker": data.get("ticker", ""),
            "pnl": data.get("pnl", 0),
            "pnl_pct": data.get("pnl_pct", 0),
            "profitable": data.get("profitable", False),
            "close_reason": data.get("close_reason", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(closed) > 100:
            system_state["recent_closed_trades"] = closed[-100:]
    except Exception as e:
        logger.debug("close_logging_failed", error=str(e))


async def _handle_order_rejected(data: dict) -> None:
    """Alert on order rejections."""
    try:
        from integrations.telegram_bot import send_alert
        await send_alert(
            f"❌ *Order Rejected*\n\n"
            f"Ticker: `{data.get('ticker', '?')}`\n"
            f"Reason: {data.get('reason', 'Unknown')}"
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# EVOLUTION EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def handle_evolution_event(event: dict[str, Any]) -> None:
    """React to evolution cycle events — update dashboard."""
    event_type = event.get("event_type", "")
    data = event.get("data", {})

    logger.info("evolution_event_received", event_type=event_type)

    try:
        from dashboard.api.main import system_state

        # Store latest evolution event for dashboard
        evo_events = system_state.setdefault("evolution_events", [])
        evo_events.append({
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(evo_events) > 50:
            system_state["evolution_events"] = evo_events[-50:]

        # Forward significant events to Telegram
        if event_type in ("SHADOW_PROMOTED", "SHADOW_DISCARDED"):
            from integrations.telegram_bot import send_alert
            emoji = "🏆" if event_type == "SHADOW_PROMOTED" else "🗑"
            agent = data.get("agent", data.get("agent_role", "?"))
            await send_alert(
                f"{emoji} *Prompt {event_type.split('_')[1].title()}*\n\n"
                f"Agent: `{agent}`\n"
                f"Version: v{data.get('version', '?')}\n"
                f"p-value: `{data.get('p_value', '?')}`"
            )

    except Exception as e:
        logger.debug("evolution_event_handling_failed", error=str(e))


# ═══════════════════════════════════════════════════════════════════
# HEALTH EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def handle_health_event(event: dict[str, Any]) -> None:
    """React to system health events."""
    event_type = event.get("event_type", "")
    data = event.get("data", {})
    status = data.get("status", "")

    logger.info("health_event_received", event_type=event_type, status=status)

    if status == "DEGRADED":
        await _handle_health_degradation(data)
    elif status == "RECOVERED":
        await _handle_health_recovery(data)


async def _handle_health_degradation(data: dict) -> None:
    """React to system health degradation."""
    component = data.get("component", "unknown")
    reason = data.get("reason", "Unknown issue")

    try:
        from integrations.telegram_bot import send_alert
        await send_alert(
            f"⚠️ *System Health: DEGRADED*\n\n"
            f"Component: `{component}`\n"
            f"Reason: {reason}\n"
            f"⏰ {datetime.now(PST_TZ).strftime('%I:%M %p PST')}"
        )
    except Exception:
        pass


async def _handle_health_recovery(data: dict) -> None:
    """React to system health recovery."""
    component = data.get("component", "unknown")

    try:
        from integrations.telegram_bot import send_alert
        await send_alert(
            f"✅ *System Health: RECOVERED*\n\n"
            f"Component: `{component}`\n"
            f"⏰ {datetime.now(PST_TZ).strftime('%I:%M %p PST')}"
        )
    except Exception:
        pass
