"""
Prediction Seeder — Bootstrap Evolution from Backtest Data

When the system has zero real trades, the evolution loop is completely
inert (no predictions → no Brier scores → no trust updates → no evolution).

This module seeds the prediction_records table with synthetic predictions
derived from strategy backtest results, allowing the evolution loop to
start computing meaningful Brier scores and trust weights immediately.

The seed predictions are:
1. Tagged as non-shadow, prompt_version=0 (distinguishable from real predictions)
2. Immediately resolved (actual_outcome set based on backtest profitability)
3. Created with realistic timestamps spanning the backtest window

Usage:
    from evolution.prediction_seeder import seed_from_backtests
    count = await seed_from_backtests()
    # → Seeds ~50-100 predictions across agents, all with outcomes resolved
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

from persistence.db import create_prediction, update_prediction_outcome

logger = structlog.get_logger(component="prediction_seeder")


async def seed_from_backtests(
    tickers: list[str] | None = None,
    lookback_days: int = 60,
) -> dict[str, Any]:
    """Run backtests and seed prediction_records with the results.

    Each backtest trade becomes a set of predictions (one per agent role),
    with the actual outcome already resolved based on backtest P&L.

    Args:
        tickers: Tickers to backtest. If None, uses DEFAULT_WATCHLIST[:5].
        lookback_days: Days of historical data for backtesting.

    Returns:
        Summary dict with counts of predictions seeded.
    """
    from config.constants import DEFAULT_WATCHLIST

    if tickers is None:
        tickers = DEFAULT_WATCHLIST[:5]  # AAPL, MSFT, GOOGL, AMZN, NVDA

    # Check if we already have enough predictions
    from persistence.db import get_session
    from persistence.db import PredictionRecord
    from sqlalchemy import func

    with get_session() as s:
        existing = s.query(func.count(PredictionRecord.id)).scalar()
        if existing >= 20:
            logger.info(
                "seeder_skipped",
                reason="sufficient_predictions_exist",
                existing=existing,
            )
            return {"seeded": 0, "reason": "sufficient_predictions_exist", "existing": existing}

    # Run simplified backtests
    total_seeded = 0
    agent_roles = [
        "FUNDAMENTAL_ANALYST",
        "TECHNICAL_ANALYST",
        "SENTIMENT_ANALYST",
        "JUDGE",
    ]

    results_summary = {}

    for ticker in tickers:
        try:
            trades = await _run_simple_backtest(ticker, lookback_days)
            if not trades:
                continue

            seeded = 0
            for trade in trades:
                trade_id = f"seed_{ticker}_{trade['date'].strftime('%Y%m%d')}"

                for agent_role in agent_roles:
                    # Generate a realistic prediction based on the trade outcome
                    # Add some noise to make it more realistic
                    import random
                    if trade["profitable"]:
                        # Agent predicted correctly — probability should be > 0.5
                        predicted_prob = 0.55 + random.random() * 0.3  # 0.55-0.85
                    else:
                        # Mix of correct and incorrect predictions
                        if random.random() < 0.4:
                            # Agent was wrong (overconfident)
                            predicted_prob = 0.6 + random.random() * 0.2
                        else:
                            # Agent was cautious (correctly low confidence)
                            predicted_prob = 0.3 + random.random() * 0.2

                    try:
                        pred = create_prediction(
                            id=str(uuid.uuid4()),
                            agent_role=agent_role,
                            trade_id=trade_id,
                            ticker=ticker,
                            predicted_probability=round(predicted_prob, 3),
                            confidence=round(0.4 + random.random() * 0.4, 3),
                            prompt_version=0,  # Mark as seed data
                            is_shadow=False,
                        )
                        # Immediately resolve the prediction
                        outcome = 1 if trade["profitable"] else 0
                        update_prediction_outcome(trade_id, outcome)
                        seeded += 1
                    except Exception as e:
                        logger.debug("seed_prediction_failed", error=str(e))

            total_seeded += seeded
            results_summary[ticker] = {
                "trades": len(trades),
                "predictions_seeded": seeded,
            }

        except Exception as e:
            logger.warning("backtest_seed_failed", ticker=ticker, error=str(e))

    logger.info("predictions_seeded", total=total_seeded, tickers=len(tickers))

    return {
        "seeded": total_seeded,
        "tickers": results_summary,
    }


async def _run_simple_backtest(
    ticker: str,
    lookback_days: int = 60,
) -> list[dict]:
    """Run a simplified momentum backtest to generate seed trades.

    Returns a list of trade dicts with date, entry_price, exit_price, profitable.
    """
    # Use MarketDataClient for historical bars (AlpacaClient may only return 1 bar)
    bars = []
    try:
        from integrations.market_data import MarketDataClient
        mdc = MarketDataClient()
        bars = await mdc.get_bars(ticker, limit=lookback_days)
        await mdc.close()
    except Exception:
        # Fallback to Alpaca
        try:
            from broker.alpaca_client import AlpacaClient
            alpaca = AlpacaClient()
            bars = await alpaca.get_bars(ticker, limit=lookback_days)
            await alpaca.close()
        except Exception:
            return []

    if not bars or len(bars) < 20:
        return []

    trades = []
    hold_period = 5  # Hold for 5 trading days

    for i in range(10, len(bars) - hold_period, hold_period):
        # Simple momentum signal: buy if 5-day return > 0
        entry_bar = bars[i]
        lookback_bar = bars[i - 5]
        exit_bar = bars[i + hold_period - 1]

        entry_close = float(entry_bar.get("c", entry_bar.get("close", 0)))
        lookback_close = float(lookback_bar.get("c", lookback_bar.get("close", 0)))
        exit_close = float(exit_bar.get("c", exit_bar.get("close", 0)))

        if entry_close <= 0 or lookback_close <= 0 or exit_close <= 0:
            continue

        momentum = (entry_close - lookback_close) / lookback_close

        # Only take trade if there's positive momentum
        if momentum > 0.005:  # 0.5% minimum momentum
            trade_date = datetime.fromisoformat(
                entry_bar.get("t", entry_bar.get("timestamp", datetime.now(timezone.utc).isoformat()))
            )
            if isinstance(trade_date, str):
                trade_date = datetime.fromisoformat(trade_date)

            trades.append({
                "date": trade_date,
                "entry_price": entry_close,
                "exit_price": exit_close,
                "profitable": exit_close > entry_close,
                "return_pct": (exit_close - entry_close) / entry_close * 100,
            })

    return trades
