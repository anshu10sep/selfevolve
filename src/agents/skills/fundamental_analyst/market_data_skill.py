"""
Market Data Skills for Fundamental Analyst

Provides the fundamental analyst agent with access to live
Alpaca price data for valuation context, P/E comparisons,
and price-to-fundamentals analysis.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from agents.skills.validator import skill


def _run_async(coro):
    """Run an async coroutine from a synchronous context."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)
    except RuntimeError:
        return asyncio.run(coro)


async def _fetch_bars(ticker: str, period_days: int = 30) -> List[dict]:
    """Fetch OHLCV bars from Alpaca."""
    from integrations.market_data import MarketDataClient
    mdc = MarketDataClient()
    try:
        return await mdc.get_bars(ticker, timeframe="1Day", limit=period_days)
    finally:
        await mdc.close()


async def _fetch_quote(ticker: str) -> dict:
    """Fetch latest quote from Alpaca."""
    from integrations.market_data import MarketDataClient
    mdc = MarketDataClient()
    try:
        return await mdc.get_latest_quote(ticker)
    finally:
        await mdc.close()


@skill("fundamental_analyst")
def get_price_history(ticker: str, period_days: int = 90) -> Dict[str, Any]:
    """Fetch historical closing prices for fundamental analysis context.

    Use this to check recent price trends when evaluating
    whether a stock is trading at a discount or premium to
    its fundamental value.

    Args:
        ticker: Stock symbol (e.g., "AAPL", "NVDA")
        period_days: Number of trading days of history (default 90)

    Returns:
        Dict with prices, volumes, dates, latest_price, and
        summary statistics (52w range approximation, avg volume).
    """
    try:
        bars = _run_async(_fetch_bars(ticker, period_days))

        if not bars:
            return {"error": f"No data for {ticker}", "prices": [], "count": 0}

        prices = [b["close"] for b in bars]
        volumes = [b["volume"] for b in bars]

        return {
            "ticker": ticker,
            "prices": prices,
            "volumes": volumes,
            "dates": [b["timestamp"] for b in bars],
            "latest_price": prices[-1] if prices else 0,
            "count": len(bars),
            "period_high": max(prices),
            "period_low": min(prices),
            "avg_volume": sum(volumes) // len(volumes) if volumes else 0,
            "price_change_pct": round(
                (prices[-1] - prices[0]) / prices[0] * 100, 2
            ) if len(prices) > 1 and prices[0] > 0 else 0,
        }
    except Exception as e:
        return {"error": str(e), "prices": [], "count": 0}


@skill("fundamental_analyst")
def get_latest_quote(ticker: str) -> Dict[str, Any]:
    """Get the current bid/ask quote for fundamental valuation context.

    Use this to check the current trading price when comparing
    to fair value estimates.

    Args:
        ticker: Stock symbol (e.g., "AAPL")

    Returns:
        Dict with bid, ask, and mid_price.
    """
    try:
        quote = _run_async(_fetch_quote(ticker))
        bid = quote.get("bid", 0)
        ask = quote.get("ask", 0)
        mid = (bid + ask) / 2 if bid and ask else bid or ask

        return {
            "ticker": ticker,
            "bid": bid,
            "ask": ask,
            "mid_price": round(mid, 4),
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker}
