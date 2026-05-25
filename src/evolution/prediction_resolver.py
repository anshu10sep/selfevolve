"""
Prediction Resolver — Continuous Background Loop

Resolves unresolved predictions by checking if their associated trades
have closed on Alpaca. This is THE critical bridge that connects trading
outcomes to the evolution loop's Brier scoring pipeline.

Without this, predictions are recorded but never resolved, Brier scores
never update, and the entire self-evolution loop runs on zero signal.

Runs every 5 minutes as a background task in main.py.

Resolution strategy:
  1. Query all unresolved predictions from DB (actual_outcome IS NULL)
  2. Get current positions from Alpaca
  3. For each unresolved trade:
     - If ticker still in positions → trade is still open, skip
     - If ticker not in positions → trade closed, resolve it
     - Look up the trade in DB for entry price, then check Alpaca
       for the exit price via order/activity data
  4. Also check crypto stops against current prices
  5. Publish TRADE_CLOSED events for each resolved trade
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(component="prediction_resolver")


class PredictionResolver:
    """Resolves unresolved predictions by reconciling with Alpaca positions."""

    def __init__(self):
        self._running = False
        self._resolved_count = 0
        self._cycle_count = 0
        self._history: list[dict] = []

    async def run_resolution_cycle(self) -> dict:
        """Run a single resolution cycle.

        Returns:
            Summary dict with counts of resolved predictions.
        """
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        stock_resolved = 0
        crypto_resolved = 0

        try:
            stock_resolved = await self._resolve_stock_predictions()
        except Exception as e:
            logger.error("stock_resolution_failed", error=str(e))

        try:
            crypto_resolved = await self._resolve_crypto_predictions()
        except Exception as e:
            logger.error("crypto_resolution_failed", error=str(e))

        total = stock_resolved + crypto_resolved
        self._resolved_count += total

        result = {
            "cycle": self._cycle_count,
            "timestamp": cycle_start.isoformat(),
            "stock_resolved": stock_resolved,
            "crypto_resolved": crypto_resolved,
            "total_resolved": total,
            "lifetime_resolved": self._resolved_count,
        }
        self._history.append(result)

        if total > 0:
            logger.info(
                "prediction_resolution_cycle",
                stock=stock_resolved,
                crypto=crypto_resolved,
                total=total,
            )

        return result

    async def _resolve_stock_predictions(self) -> int:
        """Resolve stock predictions by checking Alpaca positions.

        Strategy:
        - Get all unresolved trade_ids from DB
        - Get current open positions from Alpaca
        - If a trade's ticker is no longer in positions, the trade closed
        - Look up entry/exit prices from the trades table
        - Determine profitability and resolve all predictions for that trade
        """
        from persistence.db import (
            get_unresolved_trade_ids,
            get_recent_trades,
            update_trade,
        )
        from evolution.prediction_tracker import prediction_tracker

        # Get unresolved predictions
        unresolved = get_unresolved_trade_ids()
        if not unresolved:
            return 0

        # Get current Alpaca positions
        try:
            from broker.alpaca_client import AlpacaClient
            alpaca = AlpacaClient()
            positions = await alpaca.get_positions()
            await alpaca.close()
        except Exception as e:
            logger.warning("alpaca_positions_fetch_failed", error=str(e))
            return 0

        # Build set of currently held tickers
        open_tickers = {pos.get("symbol", "").upper() for pos in positions}

        # Build a position lookup for current P&L data
        position_data = {}
        for pos in positions:
            ticker = pos.get("symbol", "").upper()
            position_data[ticker] = {
                "current_price": float(pos.get("current_price", 0)),
                "avg_entry_price": float(pos.get("avg_entry_price", 0)),
                "unrealized_pl": float(pos.get("unrealized_pl", 0)),
                "market_value": float(pos.get("market_value", 0)),
            }

        resolved_count = 0

        for trade_info in unresolved:
            trade_id = trade_info["trade_id"]
            ticker = trade_info.get("ticker", "").upper()

            if not ticker:
                continue

            # If the position is still open, skip
            if ticker in open_tickers:
                continue

            # Position is GONE — the trade has closed.
            # Determine profitability by checking the trades table
            # or by querying Alpaca order history.
            profitable = await self._determine_profitability(
                trade_id, ticker
            )

            if profitable is None:
                # Can't determine — try via Alpaca order history
                profitable = await self._check_alpaca_order(trade_id)

            if profitable is None:
                # Still can't determine — skip for now
                # (the order might still be processing)
                logger.debug(
                    "resolution_skipped",
                    trade_id=trade_id[:8],
                    ticker=ticker,
                    reason="cannot_determine_profitability",
                )
                continue

            # Resolve all predictions for this trade
            try:
                count = prediction_tracker.resolve_trade(trade_id, profitable)
                if count > 0:
                    resolved_count += count
                    logger.info(
                        "predictions_resolved",
                        trade_id=trade_id[:8],
                        ticker=ticker,
                        profitable=profitable,
                        predictions=count,
                    )

                    # Also publish trade closed event for downstream consumers
                    await self._publish_trade_closed(
                        trade_id, ticker, profitable
                    )
            except Exception as e:
                logger.warning(
                    "resolution_commit_failed",
                    trade_id=trade_id[:8],
                    error=str(e),
                )

        return resolved_count

    async def _determine_profitability(
        self, trade_id: str, ticker: str
    ) -> Optional[bool]:
        """Check the trades table for entry/exit prices to determine profit.

        Returns True if profitable, False if loss, None if inconclusive.
        """
        try:
            from persistence.db import get_session
            from persistence.db import Trade

            with get_session() as s:
                trade = s.query(Trade).filter(Trade.id == trade_id).first()
                if not trade:
                    return None

                entry = trade.entry_price
                exit_price = trade.exit_price
                pnl = trade.realized_pnl

                # If we have realized P&L, use that directly
                if pnl is not None:
                    return pnl > 0

                # If we have both entry and exit, compute
                if entry and exit_price and entry > 0:
                    return exit_price > entry

                return None
        except Exception:
            return None

    async def _check_alpaca_order(self, trade_id: str) -> Optional[bool]:
        """Look up the Alpaca order by client_order_id to determine fill data.

        For bracket orders, check if the stop-loss or take-profit leg filled.
        """
        try:
            from broker.alpaca_client import AlpacaClient
            alpaca = AlpacaClient()
            order = await alpaca.get_order_by_client_id(trade_id)
            await alpaca.close()

            if not order:
                return None

            status = order.get("status", "")
            if status not in ("filled", "closed", "partially_filled"):
                return None

            # Check for bracket order legs
            legs = order.get("legs", [])
            filled_avg = float(order.get("filled_avg_price", 0) or 0)

            if legs:
                for leg in legs:
                    if leg.get("status") == "filled" and leg.get("side") == "sell":
                        sell_price = float(leg.get("filled_avg_price", 0) or 0)
                        if sell_price > 0 and filled_avg > 0:
                            return sell_price > filled_avg

            # Simple order: if it's a BUY that filled, we need to know
            # the current or exit price. Without a sell leg, we can't
            # determine profitability yet — return None.
            return None

        except Exception as e:
            logger.debug("alpaca_order_lookup_failed", trade_id=trade_id[:8], error=str(e))
            return None

    async def _resolve_crypto_predictions(self) -> int:
        """Resolve crypto predictions by checking prices against stops.

        Checks active crypto stops in the DB against current prices.
        If price hit SL or TP, resolves the prediction and updates the stop status.
        """
        from persistence.db import (
            get_active_crypto_stops,
            update_crypto_stop_status,
        )
        from evolution.prediction_tracker import prediction_tracker

        active_stops = get_active_crypto_stops()
        if not active_stops:
            return 0

        resolved_count = 0

        for stop in active_stops:
            ticker = stop.get("ticker", "")
            entry = stop.get("entry_price", 0)
            sl = stop.get("stop_loss", 0)
            tp = stop.get("take_profit", 0)
            order_id = stop.get("order_id", "")

            if not ticker or not entry:
                continue

            # Get current price
            try:
                from integrations.market_data import MarketDataClient
                mdc = MarketDataClient()
                quote = await mdc.get_crypto_quote(ticker)
                await mdc.close()
                current_price = float(quote.get("price", 0))
            except Exception:
                # Fallback: try Alpaca
                try:
                    from broker.alpaca_client import AlpacaClient
                    alpaca = AlpacaClient()
                    quote = await alpaca.get_latest_quote(ticker)
                    await alpaca.close()
                    current_price = float(
                        quote.get("quote", {}).get("ap", 0)
                        or quote.get("ask", 0)
                    )
                except Exception:
                    continue

            if current_price <= 0:
                continue

            # Check if stop-loss or take-profit was hit
            profitable = None
            close_reason = None

            if sl > 0 and current_price <= sl:
                profitable = False
                close_reason = "STOP_LOSS"
                update_crypto_stop_status(ticker, "STOPPED")
            elif tp > 0 and current_price >= tp:
                profitable = True
                close_reason = "TAKE_PROFIT"
                update_crypto_stop_status(ticker, "PROFIT_TAKEN")

            if profitable is not None and order_id:
                try:
                    count = prediction_tracker.resolve_trade(order_id, profitable)
                    if count > 0:
                        resolved_count += count
                        logger.info(
                            "crypto_prediction_resolved",
                            ticker=ticker,
                            reason=close_reason,
                            profitable=profitable,
                            entry=entry,
                            current=current_price,
                            predictions=count,
                        )

                        # Try to close the crypto position
                        try:
                            from broker.alpaca_client import AlpacaClient
                            alpaca = AlpacaClient()
                            await alpaca.close_position(ticker)
                            await alpaca.close()
                        except Exception:
                            pass

                        # Telegram alert
                        try:
                            from integrations.telegram_bot import send_alert
                            emoji = "🟢" if profitable else "🔴"
                            pnl_pct = ((current_price - entry) / entry * 100) if entry > 0 else 0
                            await send_alert(
                                f"{emoji} *Crypto {close_reason}*\n\n"
                                f"Ticker: `{ticker}`\n"
                                f"Entry: ${entry:,.2f}\n"
                                f"Exit: ${current_price:,.2f}\n"
                                f"P&L: {pnl_pct:+.1f}%"
                            )
                        except Exception:
                            pass

                except Exception as e:
                    logger.warning(
                        "crypto_resolution_failed",
                        ticker=ticker,
                        error=str(e),
                    )

        return resolved_count

    async def _publish_trade_closed(
        self, trade_id: str, ticker: str, profitable: bool
    ) -> None:
        """Publish a TRADE_CLOSED event for downstream consumers."""
        try:
            from core.event_bus import EventBus, EventChannels, Event
            from persistence.redis_client import get_redis_client
            redis = await get_redis_client()
            bus = EventBus(redis)
            event = Event(
                event_type="TRADE_CLOSED",
                data={
                    "trade_id": trade_id,
                    "ticker": ticker,
                    "profitable": profitable,
                    "source": "prediction_resolver",
                },
                source="prediction_resolver",
            )
            await bus.publish(EventChannels.TRADE_EVENTS, event)
        except Exception:
            pass  # Best-effort; don't crash resolution over pub/sub

    # ── Background Loop ──────────────────────────────────────────

    async def run_loop(self, interval_minutes: int = 5):
        """Background loop: resolve predictions every N minutes.

        Run as a background task in main.py:
            asyncio.create_task(prediction_resolver.run_loop())
        """
        self._running = True
        logger.info("prediction_resolver_started", interval=f"{interval_minutes}min")

        # Initial delay to let system stabilize
        await asyncio.sleep(30)

        while self._running:
            try:
                await self.run_resolution_cycle()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("prediction_resolver_error", error=str(e))
                await asyncio.sleep(60)

        self._running = False

    def stop(self):
        """Stop the resolution loop."""
        self._running = False

    def get_status(self) -> dict:
        """Get resolver status for dashboard."""
        return {
            "running": self._running,
            "total_cycles": self._cycle_count,
            "total_resolved": self._resolved_count,
            "recent_cycles": self._history[-10:],
        }


# Module-level singleton
prediction_resolver = PredictionResolver()
