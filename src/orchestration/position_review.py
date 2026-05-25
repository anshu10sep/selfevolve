"""
Position Review Engine — Active Exit Management

Runs during market hours to actively manage open positions.
Uses DETERMINISTIC rules (no LLM) for fast, reliable decisions:

1. Trailing Stop Tightening:
   - If position up >3%: tighten stop to breakeven
   - If position up >5%: lock in 2% profit
   - If position up >8%: lock in 5% profit

2. Time Decay Exit:
   - If held >5 trading days with <1% gain: recommend close
   - If held >10 trading days: recommend close regardless

3. Regime-Based Exit:
   - If regime changes to BEAR/PANIC and position <2% profitable: close
   - If regime is HIGH_VOL and position <0%: close immediately

These are deterministic Python rules — no LLM latency in exit decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger(component="position_review")


@dataclass
class ExitRecommendation:
    """A recommended exit or stop adjustment."""
    ticker: str
    action: str           # CLOSE, TIGHTEN_STOP, HOLD
    reason: str           # Human-readable explanation
    new_stop_price: Optional[float] = None
    urgency: str = "NORMAL"  # LOW, NORMAL, HIGH, CRITICAL


def review_positions(
    positions: list[dict],
    regime: str = "SIDEWAYS",
    trades_db: Optional[list[dict]] = None,
) -> list[ExitRecommendation]:
    """Review all open positions and generate exit recommendations.

    Args:
        positions: List of position dicts from Alpaca API
            Each has: symbol, qty, avg_entry_price, current_price,
                      unrealized_pl, unrealized_plpc, market_value
        regime: Current market regime (BULL, BEAR, SIDEWAYS, HIGH_VOL, PANIC)
        trades_db: Optional list of trade records from DB (for hold duration)

    Returns:
        List of ExitRecommendation objects (only actionable ones)
    """
    recommendations = []

    for pos in positions:
        ticker = pos.get("symbol", "")
        entry_price = float(pos.get("avg_entry_price", 0))
        current_price = float(pos.get("current_price", 0))
        unrealized_plpc = float(pos.get("unrealized_plpc", 0)) * 100  # Convert to %
        market_value = float(pos.get("market_value", 0))

        if not ticker or entry_price <= 0:
            continue

        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        # Determine hold duration from trades DB
        hold_days = _get_hold_days(ticker, trades_db)

        # ── Rule 1: Trailing Stop Tightening ────────────────────
        if pnl_pct >= 8.0:
            new_stop = entry_price * 1.05  # Lock in 5% profit
            recommendations.append(ExitRecommendation(
                ticker=ticker,
                action="TIGHTEN_STOP",
                reason=f"Position up {pnl_pct:.1f}% — locking in 5% profit",
                new_stop_price=round(new_stop, 2),
            ))
        elif pnl_pct >= 5.0:
            new_stop = entry_price * 1.02  # Lock in 2% profit
            recommendations.append(ExitRecommendation(
                ticker=ticker,
                action="TIGHTEN_STOP",
                reason=f"Position up {pnl_pct:.1f}% — locking in 2% profit",
                new_stop_price=round(new_stop, 2),
            ))
        elif pnl_pct >= 3.0:
            new_stop = entry_price  # Move to breakeven
            recommendations.append(ExitRecommendation(
                ticker=ticker,
                action="TIGHTEN_STOP",
                reason=f"Position up {pnl_pct:.1f}% — moving stop to breakeven",
                new_stop_price=round(new_stop, 2),
            ))

        # ── Rule 2: Time Decay Exit ─────────────────────────────
        if hold_days is not None:
            if hold_days > 10:
                recommendations.append(ExitRecommendation(
                    ticker=ticker,
                    action="CLOSE",
                    reason=f"Held {hold_days} days — exceeds max hold (10 days)",
                    urgency="HIGH",
                ))
                continue  # Don't add more recommendations for this position

            if hold_days > 5 and pnl_pct < 1.0:
                recommendations.append(ExitRecommendation(
                    ticker=ticker,
                    action="CLOSE",
                    reason=f"Held {hold_days} days with only {pnl_pct:.1f}% gain — time decay exit",
                    urgency="NORMAL",
                ))
                continue

        # ── Rule 3: Regime-Based Exit ───────────────────────────
        if regime in ("PANIC",):
            if pnl_pct < 2.0:
                recommendations.append(ExitRecommendation(
                    ticker=ticker,
                    action="CLOSE",
                    reason=f"PANIC regime — closing position with {pnl_pct:.1f}% P&L",
                    urgency="CRITICAL",
                ))
                continue

        if regime in ("BEAR", "HIGH_VOL"):
            if pnl_pct < 0:
                recommendations.append(ExitRecommendation(
                    ticker=ticker,
                    action="CLOSE",
                    reason=f"{regime} regime — cutting loss at {pnl_pct:.1f}%",
                    urgency="HIGH",
                ))
                continue

            if regime == "BEAR" and pnl_pct < 2.0:
                recommendations.append(ExitRecommendation(
                    ticker=ticker,
                    action="CLOSE",
                    reason=f"BEAR regime — taking small {pnl_pct:.1f}% profit before it evaporates",
                    urgency="NORMAL",
                ))
                continue

    return recommendations


def _get_hold_days(
    ticker: str,
    trades_db: Optional[list[dict]],
) -> Optional[int]:
    """Get the number of trading days a position has been held.

    Looks up the original trade entry time from the trades database.
    """
    if not trades_db:
        return None

    for trade in trades_db:
        if trade.get("ticker") == ticker and trade.get("status") == "FILLED":
            filled_at = trade.get("filled_at") or trade.get("created_at")
            if filled_at:
                try:
                    if isinstance(filled_at, str):
                        filled_at = datetime.fromisoformat(
                            filled_at.replace("Z", "+00:00")
                        )
                    delta = datetime.now(timezone.utc) - filled_at.replace(
                        tzinfo=timezone.utc if filled_at.tzinfo is None else filled_at.tzinfo
                    )
                    # Approximate trading days (weekdays only)
                    calendar_days = delta.days
                    trading_days = int(calendar_days * 5 / 7)
                    return max(0, trading_days)
                except (ValueError, TypeError):
                    pass

    return None


def format_telegram_report(recommendations: list[ExitRecommendation]) -> str:
    """Format recommendations for Telegram notification."""
    if not recommendations:
        return ""

    lines = ["📊 *Position Review*\n"]
    for rec in recommendations:
        if rec.action == "CLOSE":
            emoji = "🔴"
        elif rec.action == "TIGHTEN_STOP":
            emoji = "🟡"
        else:
            emoji = "🟢"

        line = f"{emoji} `{rec.ticker}`: *{rec.action}*\n   {rec.reason}"
        if rec.new_stop_price:
            line += f"\n   New stop: ${rec.new_stop_price:,.2f}"
        lines.append(line)

    return "\n".join(lines)
