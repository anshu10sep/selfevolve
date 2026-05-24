"""
Market Data Client

Wraps the Alpaca Data API for real-time quotes, historical bars,
market status, and stock screening data.
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(component="market_data")


class MarketDataClient:
    """Alpaca Market Data API client."""

    def __init__(self):
        settings = get_settings()
        self.data_url = settings.alpaca_data_url
        self.base_url = settings.alpaca_base_url
        self.headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=15.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Quotes ─────────────────────────────────────────────────

    async def get_latest_quote(self, ticker: str) -> dict[str, Any]:
        """Get latest bid/ask/last for a ticker."""
        client = await self._get_client()
        r = await client.get(f"{self.data_url}/v2/stocks/{ticker}/quotes/latest", params={"feed": "iex"})
        r.raise_for_status()
        data = r.json()
        quote = data.get("quote", {})
        return {
            "ticker": ticker,
            "bid": float(quote.get("bp", 0)),
            "ask": float(quote.get("ap", 0)),
            "bid_size": int(quote.get("bs", 0)),
            "ask_size": int(quote.get("as", 0)),
            "timestamp": quote.get("t", ""),
        }

    # ── Bars (OHLCV) ──────────────────────────────────────────

    async def get_bars(
        self,
        ticker: str,
        timeframe: str = "1Day",
        limit: int = 30,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> list[dict]:
        """Get historical OHLCV bars."""
        client = await self._get_client()

        # Always set a start date — Alpaca needs it for after-hours queries
        if not start:
            from datetime import timedelta
            start_date = datetime.now(timezone.utc) - timedelta(days=int(limit * 1.8))
            start = start_date.strftime("%Y-%m-%d")

        params: dict[str, Any] = {"timeframe": timeframe, "limit": limit, "feed": "iex", "start": start}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        r = await client.get(
            f"{self.data_url}/v2/stocks/{ticker}/bars",
            params=params,
        )
        r.raise_for_status()
        data = r.json()
        bars = data.get("bars") or []
        return [
            {
                "timestamp": b.get("t", ""),
                "open": float(b.get("o", 0)),
                "high": float(b.get("h", 0)),
                "low": float(b.get("l", 0)),
                "close": float(b.get("c", 0)),
                "volume": int(b.get("v", 0)),
                "vwap": float(b.get("vw", 0)),
            }
            for b in bars
        ]

    # ── Snapshot ───────────────────────────────────────────────

    async def get_snapshot(self, ticker: str) -> dict[str, Any]:
        """Get full snapshot (quote + latest trade + daily bar)."""
        client = await self._get_client()
        r = await client.get(f"{self.data_url}/v2/stocks/{ticker}/snapshot", params={"feed": "iex"})
        r.raise_for_status()
        return r.json()

    async def get_snapshots(self, tickers: list[str]) -> dict[str, Any]:
        """Get snapshots for multiple tickers at once."""
        client = await self._get_client()
        r = await client.get(
            f"{self.data_url}/v2/stocks/snapshots",
            params={"symbols": ",".join(tickers), "feed": "iex"},
        )
        r.raise_for_status()
        return r.json()

    # ── Market Status ─────────────────────────────────────────

    async def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        client = await self._get_client()
        r = await client.get(f"{self.base_url}/v2/clock")
        r.raise_for_status()
        return r.json().get("is_open", False)

    async def get_calendar(self, days: int = 5) -> list[dict]:
        """Get upcoming market calendar (open/close times)."""
        client = await self._get_client()
        r = await client.get(
            f"{self.base_url}/v2/calendar",
            params={"start": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
        )
        r.raise_for_status()
        return r.json()[:days]

    # ── Most Active / Movers ──────────────────────────────────

    async def get_most_active(self, top: int = 20) -> list[dict]:
        """
        Get most active stocks by volume.
        Falls back to a curated list if the screener endpoint isn't available.
        """
        # Try the screener endpoint first
        try:
            client = await self._get_client()
            r = await client.get(
                f"{self.data_url}/v1beta1/screener/stocks/most-actives",
                params={"top": top},
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("most_actives", [])
        except Exception:
            pass

        # Fallback: get snapshots of well-known liquid stocks
        fallback_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",
            "JPM", "V", "UNH", "JNJ", "WMT", "PG", "MA", "HD",
            "DIS", "NFLX", "PYPL", "AMD", "INTC",
        ]

        snapshots = await self.get_snapshots(fallback_tickers[:top])
        results = []
        for ticker, snap in snapshots.items():
            bar = snap.get("dailyBar", {})
            prev = snap.get("prevDailyBar", {})
            trade = snap.get("latestTrade", {})

            price = float(trade.get("p", bar.get("c", 0)))
            prev_close = float(prev.get("c", price))
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

            results.append({
                "symbol": ticker,
                "price": price,
                "volume": int(bar.get("v", 0)),
                "change_pct": change_pct,
                "prev_close": prev_close,
            })

        results.sort(key=lambda x: x["volume"], reverse=True)
        return results
