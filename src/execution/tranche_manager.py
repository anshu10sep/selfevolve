"""
Tranche Manager

Manages the lifecycle of capital tranches ($10 each x 10 = $100).
Implements the checkout/release mechanism to prevent double-spending.
Each tranche has an independent state machine:
    AVAILABLE → LOCKED_IN_TRADE → SETTLING → AVAILABLE
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from core.models.portfolio import TrancheState, TrancheStatus
from config.constants import DEFAULT_TRANCHE_SIZES

logger = structlog.get_logger(component="tranche_manager")


class TrancheManager:
    """
    Fractional tranche lifecycle management.
    
    The Execution Agent must explicitly 'checkout' an AVAILABLE tranche
    before routing any order. This prevents the LLM from accidentally
    double-spending or over-allocating the $100 portfolio.
    """

    def __init__(self, tranches: list[TrancheState] | None = None):
        if tranches is None:
            self.tranches = [
                TrancheState(tranche_index=i, amount=amt)
                for i, amt in enumerate(DEFAULT_TRANCHE_SIZES)
            ]
        else:
            self.tranches = sorted(tranches, key=lambda t: t.tranche_index)

    @property
    def available_count(self) -> int:
        """Number of available tranches."""
        return sum(1 for t in self.tranches if t.status == TrancheStatus.AVAILABLE)

    @property
    def locked_count(self) -> int:
        """Number of locked tranches."""
        return sum(1 for t in self.tranches if t.status == TrancheStatus.LOCKED)

    @property
    def settling_count(self) -> int:
        """Number of settling tranches."""
        return sum(1 for t in self.tranches if t.status == TrancheStatus.SETTLING)

    @property
    def total_available(self) -> float:
        """Total available capital across all unlocked tranches."""
        return sum(t.amount for t in self.tranches if t.status == TrancheStatus.AVAILABLE)

    @property
    def total_locked(self) -> float:
        """Total capital locked in active trades."""
        return sum(t.amount for t in self.tranches if t.status == TrancheStatus.LOCKED)

    @property
    def total_settling(self) -> float:
        """Total capital in settlement."""
        return sum(t.amount for t in self.tranches if t.status == TrancheStatus.SETTLING)

    def checkout(self, trade_id: str) -> Optional[TrancheState]:
        """
        Checkout the first available tranche for a trade.
        
        Returns the locked tranche or None if none available.
        Thread-safety is handled at the StateManager level via Redis transactions.
        """
        for tranche in self.tranches:
            if tranche.status == TrancheStatus.AVAILABLE:
                tranche.status = TrancheStatus.LOCKED
                tranche.locked_trade_id = trade_id
                tranche.locked_at = datetime.now(timezone.utc)

                logger.info(
                    "tranche_checkout",
                    tranche_index=tranche.tranche_index,
                    amount=tranche.amount,
                    trade_id=trade_id,
                )
                return tranche

        logger.warning("no_available_tranches", trade_id=trade_id)
        return None

    def release(
        self,
        tranche_index: int,
        settling_until: Optional[datetime] = None,
        new_amount: Optional[float] = None,
    ) -> Optional[TrancheState]:
        """
        Release a tranche back to available or settling state.
        
        Args:
            tranche_index: Index of the tranche to release
            settling_until: If set, tranche enters SETTLING state until this time
            new_amount: Updated tranche amount (if trade was profitable/lossy)
        """
        tranche = self._get_tranche(tranche_index)
        if not tranche:
            return None

        if new_amount is not None:
            tranche.amount = new_amount

        if settling_until:
            tranche.status = TrancheStatus.SETTLING
            tranche.settling_until = settling_until
        else:
            tranche.status = TrancheStatus.AVAILABLE
            tranche.locked_trade_id = None
            tranche.locked_at = None
            tranche.settling_until = None

        logger.info(
            "tranche_released",
            tranche_index=tranche_index,
            new_status=tranche.status.value,
            amount=tranche.amount,
        )
        return tranche

    def settle_matured(self, current_time: Optional[datetime] = None) -> int:
        """
        Settle all tranches whose T+1 window has passed.
        
        Returns the number of tranches that were settled.
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        settled = 0
        for tranche in self.tranches:
            if (
                tranche.status == TrancheStatus.SETTLING
                and tranche.settling_until
                and current_time >= tranche.settling_until
            ):
                tranche.status = TrancheStatus.AVAILABLE
                tranche.locked_trade_id = None
                tranche.locked_at = None
                tranche.settling_until = None
                settled += 1

        if settled:
            logger.info("tranches_matured", count=settled)
        return settled

    def get_summary(self) -> dict:
        """Get a summary of all tranche states."""
        return {
            "total_tranches": len(self.tranches),
            "available": self.available_count,
            "locked": self.locked_count,
            "settling": self.settling_count,
            "total_available_usd": self.total_available,
            "total_locked_usd": self.total_locked,
            "total_settling_usd": self.total_settling,
        }

    def _get_tranche(self, index: int) -> Optional[TrancheState]:
        """Get a tranche by index."""
        for tranche in self.tranches:
            if tranche.tranche_index == index:
                return tranche
        return None
