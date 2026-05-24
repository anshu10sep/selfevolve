"""
T+1 Settlement Tracker

Deterministic calculation of settled vs unsettled funds.
Uses pandas_market_calendars for accurate business day calculation
respecting market holidays and weekend offsets.

The LLM is BANNED from settlement math. This is pure Python.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from config.constants import T1_SETTLEMENT_DAYS

logger = structlog.get_logger(component="settlement_tracker")


class SettlementTracker:
    """
    Stateless T+1 settlement calculator.
    
    Rather than maintaining a shadow ledger (which drifts),
    this calculates settled funds on-the-fly from trade history.
    """

    def __init__(self):
        self._calendar = None

    def _get_calendar(self):
        """Lazy-load market calendar to avoid import overhead."""
        if self._calendar is None:
            try:
                import exchange_calendars as xcals
                self._calendar = xcals.get_calendar("XNYS")
            except ImportError:
                try:
                    import pandas_market_calendars as mcal
                    self._calendar = mcal.get_calendar("NYSE")
                except ImportError:
                    self._calendar = None
                    logger.warning("no_market_calendar_available")
        return self._calendar

    def calculate_settlement_date(
        self, execution_time: datetime
    ) -> datetime:
        """
        Calculate the T+1 settlement date for a trade.
        
        Accounts for weekends and market holidays using the NYSE calendar.
        """
        cal = self._get_calendar()

        if cal is not None:
            try:
                # Use exchange calendar for accurate business days
                exec_date = execution_time.date()
                # Get valid trading sessions after the execution date
                sessions = cal.sessions_in_range(
                    exec_date + timedelta(days=1),
                    exec_date + timedelta(days=10),
                )
                if len(sessions) >= T1_SETTLEMENT_DAYS:
                    settlement_date = sessions[T1_SETTLEMENT_DAYS - 1]
                    return datetime.combine(
                        settlement_date.date() if hasattr(settlement_date, 'date') else settlement_date,
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    )
            except Exception as e:
                logger.warning("calendar_calculation_failed", error=str(e))

        # Fallback: simple business day calculation
        return self._simple_t1_calculation(execution_time)

    def _simple_t1_calculation(self, execution_time: datetime) -> datetime:
        """Fallback T+1 calculation without market calendar."""
        settlement = execution_time + timedelta(days=1)

        # Skip weekends
        while settlement.weekday() >= 5:  # Saturday = 5, Sunday = 6
            settlement += timedelta(days=1)

        return settlement.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    def calculate_unsettled_amount(
        self,
        recent_trades: list[dict],
        current_time: Optional[datetime] = None,
    ) -> float:
        """
        Calculate total unsettled funds from recent trade history.
        
        This is the STATELESS approach: query Alpaca for recent fills,
        then mathematically determine what's still unsettled.
        
        Args:
            recent_trades: List of trade dicts with 'execution_time', 'notional'
            current_time: Current timestamp (default: now)
            
        Returns:
            Total dollar amount still in T+1 settlement
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        unsettled = 0.0
        for trade in recent_trades:
            exec_time = trade.get("execution_time")
            notional = trade.get("notional", 0.0)

            if exec_time is None or notional <= 0:
                continue

            if isinstance(exec_time, str):
                exec_time = datetime.fromisoformat(exec_time)

            settlement_date = self.calculate_settlement_date(exec_time)
            if current_time < settlement_date:
                unsettled += notional

        return unsettled

    def is_within_t1_window(
        self,
        execution_time: datetime,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """Check if a trade is still within its T+1 settlement window."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        settlement_date = self.calculate_settlement_date(execution_time)
        return current_time < settlement_date

    def get_settled_funds(
        self,
        total_equity: float,
        recent_trades: list[dict],
        current_time: Optional[datetime] = None,
    ) -> float:
        """
        Stateless calculation of currently settled funds.
        
        This is called IMMEDIATELY before order submission (JIT validation).
        """
        unsettled = self.calculate_unsettled_amount(recent_trades, current_time)
        settled = total_equity - unsettled
        return max(0.0, settled)
