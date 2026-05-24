"""
Stock Screener

Scans the market for trading candidates using momentum,
volume, and price action signals via the Alpaca Data API.
"""

from __future__ import annotations

from typing import Optional

import structlog

from integrations.market_data import MarketDataClient

logger = structlog.get_logger(component="screener")


class StockScreener:
    """Screens stocks for trading candidates."""

    def __init__(self, market_data: Optional[MarketDataClient] = None):
        self.market_data = market_data or MarketDataClient()

    async def screen_candidates(self, max_results: int = 10) -> list[dict]:
        """
        Screen for trading candidates using momentum + volume.

        Returns a sorted list of dicts:
            {ticker, price, volume, momentum_score, change_pct, reason}
        """
        try:
            # Get most active stocks
            actives = await self.market_data.get_most_active(top=20)

            candidates = []
            for stock in actives:
                ticker = stock.get("symbol", "")
                price = stock.get("price", 0)
                volume = stock.get("volume", 0)
                change_pct = stock.get("change_pct", 0)

                if not ticker or price <= 0:
                    continue

                # Get recent bars for momentum calculation
                try:
                    bars = await self.market_data.get_bars(ticker, timeframe="1Day", limit=10)
                except Exception:
                    bars = []

                momentum_score = self._calculate_momentum(bars, change_pct)

                # Filter: only include stocks with meaningful activity
                if abs(momentum_score) < 0.1:
                    continue

                reason = self._generate_reason(change_pct, volume, momentum_score)

                candidates.append({
                    "ticker": ticker,
                    "price": price,
                    "volume": volume,
                    "change_pct": change_pct,
                    "momentum_score": momentum_score,
                    "reason": reason,
                })

            # Sort by absolute momentum score (strongest signals first)
            candidates.sort(key=lambda x: abs(x["momentum_score"]), reverse=True)

            logger.info(
                "screening_complete",
                total_scanned=len(actives),
                candidates_found=len(candidates),
            )

            return candidates[:max_results]

        except Exception as e:
            logger.error("screening_failed", error=str(e))
            return []

    def _calculate_momentum(self, bars: list[dict], today_change: float) -> float:
        """
        Calculate a composite momentum score (-1.0 to 1.0).

        Factors:
        - Today's price change
        - 5-day trend direction
        - Volume trend
        """
        score = 0.0

        # Factor 1: Today's change (weight 0.4)
        if abs(today_change) > 0:
            # Normalize: 5% change = max score
            change_score = min(1.0, abs(today_change) / 5.0)
            score += (0.4 * change_score) * (1 if today_change > 0 else -1)

        # Factor 2: Multi-day trend (weight 0.4)
        if len(bars) >= 5:
            closes = [b["close"] for b in bars[-5:]]
            if closes[0] > 0:
                five_day_return = (closes[-1] - closes[0]) / closes[0]
                trend_score = min(1.0, abs(five_day_return) / 0.10)  # 10% = max
                score += (0.4 * trend_score) * (1 if five_day_return > 0 else -1)

        # Factor 3: Volume surge (weight 0.2)
        if len(bars) >= 5:
            volumes = [b["volume"] for b in bars]
            avg_vol = sum(volumes[:-1]) / max(1, len(volumes) - 1)
            if avg_vol > 0 and volumes[-1] > avg_vol * 1.5:
                score += 0.2  # Volume surge = bullish signal

        return max(-1.0, min(1.0, score))

    def _generate_reason(self, change_pct: float, volume: int, momentum: float) -> str:
        """Generate a human-readable reason for the signal."""
        parts = []
        if abs(change_pct) > 2:
            direction = "up" if change_pct > 0 else "down"
            parts.append(f"{abs(change_pct):.1f}% {direction}")
        if abs(momentum) > 0.5:
            parts.append("strong momentum")
        elif abs(momentum) > 0.2:
            parts.append("moderate momentum")
        if volume > 10_000_000:
            parts.append("high volume")
        return ", ".join(parts) if parts else "screening signal"
