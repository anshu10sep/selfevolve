"""
Judge Agent — Real Execution Layer Tools

Production-grade tools that connect the Judge to the execution layer:
- Position sizing (deterministic math, no LLM)
- Circuit breaker status checking
- Settlement compliance (T+2 / GFV prevention)

These tools ensure the Judge makes decisions based on REAL system state,
not LLM hallucination.
"""

from typing import Dict, Any, Optional
import logging
from datetime import datetime, timezone

from agents.skills.validator import skill

logger = logging.getLogger(__name__)


@skill("judge")
def calculate_position_size(
    portfolio_value: float,
    current_price: float,
    stop_loss_price: float,
    max_risk_pct: float = 0.02,
    max_position_pct: float = 0.30,
) -> Dict[str, Any]:
    """
    Calculate exact position size using fixed-risk position sizing.
    This is DETERMINISTIC math — no LLM estimation involved.

    Risk formula: shares = max_risk_dollars / (entry_price - stop_loss_price)

    Args:
        portfolio_value: Total portfolio value in dollars.
        current_price: Current stock price per share.
        stop_loss_price: Stop loss price per share (must be below current_price for buys).
        max_risk_pct: Maximum risk per trade as fraction of portfolio (default 0.02 = 2%).
        max_position_pct: Maximum position size as fraction of portfolio (default 0.30 = 30%).

    Returns:
        Dict with shares, allocated_capital, risk_dollars, and validation info.
    """
    if current_price <= 0 or portfolio_value <= 0:
        return {
            "valid": False,
            "shares": 0.0,
            "allocated_capital": 0.0,
            "error": "Invalid price or portfolio value",
        }

    if stop_loss_price >= current_price:
        return {
            "valid": False,
            "shares": 0.0,
            "allocated_capital": 0.0,
            "error": f"Stop loss (${stop_loss_price}) must be below entry (${current_price})",
        }

    # Maximum risk in dollars
    max_risk_dollars = portfolio_value * max_risk_pct

    # Risk per share
    risk_per_share = current_price - stop_loss_price

    # Position size based on risk
    shares_by_risk = max_risk_dollars / risk_per_share

    # Position size based on concentration limit
    max_position_dollars = portfolio_value * max_position_pct
    shares_by_concentration = max_position_dollars / current_price

    # Take the smaller of the two
    shares = min(shares_by_risk, shares_by_concentration)

    # For fractional shares, round to 3 decimal places
    shares = round(shares, 3)
    allocated_capital = round(shares * current_price, 2)
    actual_risk = round(shares * risk_per_share, 2)
    risk_pct = round(actual_risk / portfolio_value, 4)

    return {
        "valid": True,
        "shares": shares,
        "allocated_capital": allocated_capital,
        "risk_dollars": actual_risk,
        "risk_pct": risk_pct,
        "entry_price": current_price,
        "stop_loss_price": stop_loss_price,
        "risk_per_share": round(risk_per_share, 4),
        "limiting_factor": "risk" if shares_by_risk < shares_by_concentration else "concentration",
        "interpretation": (
            f"Buy {shares} shares at ${current_price:.2f}. "
            f"Capital: ${allocated_capital:.2f}. "
            f"Risk: ${actual_risk:.2f} ({risk_pct:.2%} of portfolio). "
            f"Stop loss: ${stop_loss_price:.2f}."
        ),
    }


@skill("judge")
def check_circuit_breaker(
    daily_pnl: float,
    open_positions: int,
    consecutive_losses: int,
    portfolio_value: float,
    max_daily_loss_pct: float = 0.05,
    max_open_positions: int = 5,
    max_consecutive_losses: int = 5,
) -> Dict[str, Any]:
    """
    Check if any circuit breakers are tripped.
    If ANY breaker is tripped, the Judge should NOT approve new trades.

    Args:
        daily_pnl: Today's realized + unrealized P&L in dollars.
        open_positions: Number of currently open positions.
        consecutive_losses: Number of consecutive losing trades.
        portfolio_value: Total portfolio value.
        max_daily_loss_pct: Maximum daily loss before halt (default 5%).
        max_open_positions: Maximum simultaneous positions (default 5).
        max_consecutive_losses: Max losing streak before halt (default 5).

    Returns:
        Dict with trading_allowed, tripped_breakers, and reasoning.
    """
    tripped = []
    warnings = []

    # Check daily loss limit
    daily_loss_pct = abs(daily_pnl) / portfolio_value if portfolio_value > 0 else 0
    if daily_pnl < 0 and daily_loss_pct >= max_daily_loss_pct:
        tripped.append({
            "breaker": "daily_loss_limit",
            "threshold": f"{max_daily_loss_pct:.1%}",
            "current": f"{daily_loss_pct:.1%}",
            "message": f"Daily loss (${abs(daily_pnl):.2f}) exceeds {max_daily_loss_pct:.0%} limit.",
        })
    elif daily_pnl < 0 and daily_loss_pct >= max_daily_loss_pct * 0.7:
        warnings.append(f"Approaching daily loss limit ({daily_loss_pct:.1%} of {max_daily_loss_pct:.0%})")

    # Check position limit
    if open_positions >= max_open_positions:
        tripped.append({
            "breaker": "position_limit",
            "threshold": max_open_positions,
            "current": open_positions,
            "message": f"Max positions reached ({open_positions}/{max_open_positions}).",
        })
    elif open_positions >= max_open_positions - 1:
        warnings.append(f"Near position limit ({open_positions}/{max_open_positions})")

    # Check consecutive losses
    if consecutive_losses >= max_consecutive_losses:
        tripped.append({
            "breaker": "consecutive_losses",
            "threshold": max_consecutive_losses,
            "current": consecutive_losses,
            "message": f"Losing streak ({consecutive_losses}) exceeds limit ({max_consecutive_losses}).",
        })
    elif consecutive_losses >= max_consecutive_losses - 1:
        warnings.append(f"Near loss streak limit ({consecutive_losses}/{max_consecutive_losses})")

    trading_allowed = len(tripped) == 0

    return {
        "trading_allowed": trading_allowed,
        "tripped_breakers": tripped,
        "warnings": warnings,
        "stats": {
            "daily_pnl": daily_pnl,
            "daily_loss_pct": round(daily_loss_pct, 4),
            "open_positions": open_positions,
            "consecutive_losses": consecutive_losses,
        },
        "interpretation": (
            "Trading ALLOWED. All circuit breakers clear." if trading_allowed
            else f"Trading HALTED. {len(tripped)} circuit breaker(s) tripped: "
                 f"{', '.join(b['breaker'] for b in tripped)}."
        ),
    }


@skill("judge")
def check_settlement_compliance(
    pending_settlements: int,
    unsettled_sell_proceeds: float,
    available_cash: float,
    requested_buy_amount: float,
    account_type: str = "cash",
) -> Dict[str, Any]:
    """
    Check T+2 settlement compliance to prevent Good Faith Violations (GFV).
    On a cash account, you cannot buy with unsettled funds from a recent sell.

    Args:
        pending_settlements: Number of trades pending settlement.
        unsettled_sell_proceeds: Dollar amount from sells not yet settled.
        available_cash: Currently settled (spendable) cash.
        requested_buy_amount: Dollar amount of proposed buy.
        account_type: "cash" or "margin" (margin accounts skip settlement checks).

    Returns:
        Dict with compliant, available_for_trading, gfv_risk, and interpretation.
    """
    if account_type.lower() == "margin":
        return {
            "compliant": True,
            "available_for_trading": available_cash + unsettled_sell_proceeds,
            "gfv_risk": False,
            "interpretation": "Margin account — settlement restrictions do not apply.",
        }

    # For cash accounts, only settled cash can be used
    settled_cash = available_cash
    gfv_risk = False

    if requested_buy_amount > settled_cash:
        if requested_buy_amount <= settled_cash + unsettled_sell_proceeds:
            # Would use unsettled funds — GFV risk!
            gfv_risk = True
            compliant = False
            interpretation = (
                f"GFV RISK: Buy ${requested_buy_amount:.2f} would use unsettled funds. "
                f"Settled cash: ${settled_cash:.2f}. "
                f"Unsettled: ${unsettled_sell_proceeds:.2f}. Wait for T+2 settlement."
            )
        else:
            # Simply not enough money
            compliant = False
            interpretation = (
                f"INSUFFICIENT FUNDS: Need ${requested_buy_amount:.2f}, "
                f"have ${settled_cash:.2f} settled + ${unsettled_sell_proceeds:.2f} unsettled."
            )
    else:
        compliant = True
        interpretation = (
            f"COMPLIANT: Buy ${requested_buy_amount:.2f} from "
            f"${settled_cash:.2f} settled cash. "
            f"{pending_settlements} pending settlements."
        )

    return {
        "compliant": compliant,
        "available_for_trading": settled_cash,
        "requested_amount": requested_buy_amount,
        "unsettled_funds": unsettled_sell_proceeds,
        "pending_settlements": pending_settlements,
        "gfv_risk": gfv_risk,
        "interpretation": interpretation,
    }
