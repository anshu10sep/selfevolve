"""
Market Data Skills — Live Price & Quote Data for Agent Tool-Calling

Provides agent skills that bridge the Alpaca Market Data API into
the tool-calling loop, allowing agents to pull real-time data
during their analysis.

These skills solve the critical gap where analyst agents have
indicator tools (RSI, MACD, etc.) but no way to fetch the
actual price data those tools need.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from agents.skills.validator import skill


def _run_async(coro):
    """Run an async coroutine from a synchronous context.
    
    Handles the case where we may or may not already be in an event loop.
    """
    try:
        loop = asyncio.get_running_loop()
        # We're inside an event loop — create a task in a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=30)
    except RuntimeError:
        # No event loop running — safe to use asyncio.run()
        return asyncio.run(coro)


async def _fetch_bars(ticker: str, period_days: int = 30, timeframe: str = "1Day") -> List[dict]:
    """Fetch OHLCV bars from Alpaca."""
    from integrations.market_data import MarketDataClient
    mdc = MarketDataClient()
    try:
        bars = await mdc.get_bars(ticker, timeframe=timeframe, limit=period_days)
        return bars
    finally:
        await mdc.close()


async def _fetch_quote(ticker: str) -> dict:
    """Fetch latest quote from Alpaca."""
    from integrations.market_data import MarketDataClient
    mdc = MarketDataClient()
    try:
        quote = await mdc.get_latest_quote(ticker)
        return quote
    finally:
        await mdc.close()


@skill("technical_analyst")
def get_price_history(ticker: str, period_days: int = 30) -> Dict[str, Any]:
    """Fetch historical closing prices for a stock from Alpaca.

    Use this tool to get real price data before computing technical
    indicators like RSI, MACD, Bollinger Bands, or SMA.

    Args:
        ticker: Stock symbol (e.g., "AAPL", "NVDA", "MSFT")
        period_days: Number of trading days of history (default 30)

    Returns:
        Dict with keys:
        - prices: List of closing prices (oldest to newest)
        - volumes: List of daily volumes
        - highs: List of daily highs
        - lows: List of daily lows
        - opens: List of daily opens
        - dates: List of date strings
        - latest_price: Most recent closing price
        - count: Number of data points
    """
    try:
        bars = _run_async(_fetch_bars(ticker, period_days))

        if not bars:
            return {
                "error": f"No price data found for {ticker}",
                "prices": [],
                "count": 0,
            }

        return {
            "ticker": ticker,
            "prices": [b["close"] for b in bars],
            "volumes": [b["volume"] for b in bars],
            "highs": [b["high"] for b in bars],
            "lows": [b["low"] for b in bars],
            "opens": [b["open"] for b in bars],
            "dates": [b["timestamp"] for b in bars],
            "latest_price": bars[-1]["close"] if bars else 0,
            "count": len(bars),
        }
    except Exception as e:
        return {"error": str(e), "prices": [], "count": 0}


@skill("technical_analyst")
def get_latest_quote(ticker: str) -> Dict[str, Any]:
    """Get the current bid/ask quote for a stock from Alpaca.

    Use this tool to check the real-time price before making a
    trading decision.

    Args:
        ticker: Stock symbol (e.g., "AAPL", "NVDA")

    Returns:
        Dict with bid, ask, bid_size, ask_size, and mid_price.
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
            "bid_size": quote.get("bid_size", 0),
            "ask_size": quote.get("ask_size", 0),
            "mid_price": round(mid, 4),
            "timestamp": quote.get("timestamp", ""),
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


@skill("technical_analyst")
def get_intraday_bars(ticker: str, minutes: int = 60) -> Dict[str, Any]:
    """Fetch intraday price bars (1-minute intervals) for a stock.

    Use this for intraday analysis patterns like VWAP, microstructure,
    or short-term momentum.

    Args:
        ticker: Stock symbol (e.g., "AAPL")
        minutes: Number of 1-minute bars to fetch (default 60)

    Returns:
        Dict with prices, volumes, vwaps, timestamps, and count.
    """
    try:
        bars = _run_async(_fetch_bars(ticker, period_days=minutes, timeframe="1Min"))

        if not bars:
            return {"error": f"No intraday data for {ticker}", "prices": [], "count": 0}

        return {
            "ticker": ticker,
            "prices": [b["close"] for b in bars],
            "volumes": [b["volume"] for b in bars],
            "vwaps": [b.get("vwap", 0) for b in bars],
            "timestamps": [b["timestamp"] for b in bars],
            "latest_price": bars[-1]["close"] if bars else 0,
            "count": len(bars),
        }
    except Exception as e:
        return {"error": str(e), "prices": [], "count": 0}
