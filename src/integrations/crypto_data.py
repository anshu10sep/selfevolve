"""
Crypto Market Data Client

Wraps the Alpaca Crypto Data API (v1beta3) for real-time quotes,
historical bars, and screening across 73+ crypto assets.
Operates 24/7 — no market hours restriction.
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone, timedelta

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(component="crypto_data")

# Top crypto assets by liquidity on Alpaca
CRYPTO_UNIVERSE = [
    "BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "DOT/USD",
    "LINK/USD", "UNI/USD", "AAVE/USD", "ARB/USD", "DOGE/USD",
    "SHIB/USD", "LTC/USD", "BCH/USD", "MATIC/USD", "ATOM/USD",
    "NEAR/USD", "FTM/USD", "XLM/USD", "ALGO/USD", "CRV/USD",
]


class CryptoDataClient:
    """Alpaca Crypto Data API client — 24/7 operation."""

    def __init__(self):
        settings = get_settings()
        self.data_url = "https://data.alpaca.markets"
        self.base_url = settings.alpaca_base_url
        self.headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers, timeout=15.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_latest_quotes(self, symbols: list[str] | None = None) -> dict:
        """Get latest quotes for crypto assets."""
        client = await self._get_client()
        syms = symbols or CRYPTO_UNIVERSE[:10]
        r = await client.get(
            f"{self.data_url}/v1beta3/crypto/us/latest/quotes",
            params={"symbols": ",".join(syms)},
        )
        r.raise_for_status()
        quotes = {}
        for sym, q in r.json().get("quotes", {}).items():
            quotes[sym] = {
                "symbol": sym,
                "bid": float(q.get("bp", 0)),
                "ask": float(q.get("ap", 0)),
                "bid_size": float(q.get("bs", 0)),
                "ask_size": float(q.get("as", 0)),
                "timestamp": q.get("t", ""),
            }
        return quotes

    async def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 30,
        start: Optional[str] = None,
    ) -> list[dict]:
        """Get historical OHLCV bars for a crypto asset."""
        client = await self._get_client()

        if not start:
            start_date = datetime.now(timezone.utc) - timedelta(days=int(limit * 1.8))
            start = start_date.strftime("%Y-%m-%dT00:00:00Z")

        r = await client.get(
            f"{self.data_url}/v1beta3/crypto/us/bars",
            params={
                "symbols": symbol,
                "timeframe": timeframe,
                "limit": limit,
                "start": start,
            },
        )
        r.raise_for_status()
        data = r.json()
        bars_data = data.get("bars", {}).get(symbol) or []
        return [
            {
                "timestamp": b.get("t", ""),
                "open": float(b.get("o", 0)),
                "high": float(b.get("h", 0)),
                "low": float(b.get("l", 0)),
                "close": float(b.get("c", 0)),
                "volume": float(b.get("v", 0)),
                "vwap": float(b.get("vw", 0)),
            }
            for b in bars_data
        ]

    async def get_snapshots(self, symbols: list[str] | None = None) -> dict:
        """Get snapshots (quote + bar) for multiple crypto assets."""
        client = await self._get_client()
        syms = symbols or CRYPTO_UNIVERSE[:10]
        r = await client.get(
            f"{self.data_url}/v1beta3/crypto/us/snapshots",
            params={"symbols": ",".join(syms)},
        )
        r.raise_for_status()
        return r.json().get("snapshots", {})


class CryptoScreener:
    """Screens crypto assets for trading candidates — runs 24/7."""

    def __init__(self, data_client: Optional[CryptoDataClient] = None):
        self.data = data_client or CryptoDataClient()

    async def screen_candidates(self, max_results: int = 5) -> list[dict]:
        """Screen crypto universe for momentum + volume signals."""
        try:
            # Get snapshots for all watched assets
            snapshots = await self.data.get_snapshots(CRYPTO_UNIVERSE)

            candidates = []
            for symbol, snap in snapshots.items():
                daily_bar = snap.get("dailyBar", {})
                prev_bar = snap.get("prevDailyBar", {})
                quote = snap.get("latestQuote", {})

                price = float(quote.get("ap", daily_bar.get("c", 0)))
                prev_close = float(prev_bar.get("c", price))

                if price <= 0 or prev_close <= 0:
                    continue

                change_pct = (price - prev_close) / prev_close * 100
                volume = float(daily_bar.get("v", 0))

                # Get recent bars for momentum
                try:
                    bars = await self.data.get_bars(symbol, timeframe="1Day", limit=7)
                except Exception:
                    bars = []

                momentum = self._calc_momentum(bars, change_pct)

                if abs(momentum) < 0.1:
                    continue

                candidates.append({
                    "ticker": symbol,
                    "price": price,
                    "volume": volume,
                    "change_pct": change_pct,
                    "momentum_score": momentum,
                    "asset_class": "crypto",
                    "reason": self._reason(change_pct, momentum),
                })

            candidates.sort(key=lambda x: abs(x["momentum_score"]), reverse=True)

            logger.info(
                "crypto_screening_complete",
                scanned=len(snapshots),
                candidates=len(candidates),
            )
            return candidates[:max_results]

        except Exception as e:
            logger.error("crypto_screening_failed", error=str(e))
            return []

    def _calc_momentum(self, bars: list[dict], today_change: float) -> float:
        score = 0.0
        if abs(today_change) > 0:
            score += 0.4 * min(1.0, abs(today_change) / 8.0) * (1 if today_change > 0 else -1)
        if len(bars) >= 5:
            closes = [b["close"] for b in bars[-5:]]
            if closes[0] > 0:
                ret = (closes[-1] - closes[0]) / closes[0]
                score += 0.4 * min(1.0, abs(ret) / 0.15) * (1 if ret > 0 else -1)
        if len(bars) >= 3:
            vols = [b["volume"] for b in bars]
            avg_v = sum(vols[:-1]) / max(1, len(vols) - 1)
            if avg_v > 0 and vols[-1] > avg_v * 1.5:
                score += 0.2
        return max(-1.0, min(1.0, score))

    def _reason(self, change_pct: float, momentum: float) -> str:
        parts = []
        if abs(change_pct) > 3:
            parts.append(f"{abs(change_pct):.1f}% {'up' if change_pct > 0 else 'down'}")
        if abs(momentum) > 0.5:
            parts.append("strong momentum")
        elif abs(momentum) > 0.2:
            parts.append("moderate momentum")
        return ", ".join(parts) if parts else "screening signal"
