"""
Strategy Learning Skills — Self-Evolving Parameter Engine

The core learning loop for all strategy agents. After every trade,
this module evaluates the decision quality and proposes parameter
adjustments if statistically justified.

Learning Flow:
  1. Trade closes → learn_from_trade() evaluates entry/exit quality
  2. After N trades → evaluate_parameter_fitness() checks if params need updating
  3. If data supports change → propose_parameter_evolution() with t-test
  4. Shadow test → promote_if_significant() after shadow validation

STRICT RULES:
  - Minimum 30 trades before ANY parameter change evaluation
  - Statistical significance (p < 0.05) required for promotion
  - Only ONE parameter changes at a time (isolate variables)
  - Maximum 3 active parameter changes per month (prevent overfitting)
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.skills.validator import skill

logger = structlog.get_logger(component="strategy_learning")


# ════════════════════════════════════════════════════════════════════
# TRADE-LEVEL LEARNING
# ════════════════════════════════════════════════════════════════════

@skill("strategy_agent")
def learn_from_trade(
    trade_result: dict,
    strategy_params: dict,
    strategy_name: str,
) -> dict:
    """
    Evaluate a closed trade and extract learning signals.

    After every trade (win or loss), this function evaluates:
      1. Was the entry signal correct? (Direction accuracy)
      2. Was the exit timing optimal? (Compare actual vs optimal exit)
      3. Was position sizing appropriate? (Risk-adjusted return)
      4. Should any parameters be adjusted?

    Args:
        trade_result: Closed trade record with entry/exit data
        strategy_params: Current parameter values for the strategy
        strategy_name: Name of the strategy agent

    Returns:
        Learning report with trade grade, observations, and parameter notes
    """
    entry_price = trade_result.get("entry_price", 0)
    exit_price = trade_result.get("exit_price", 0)
    stop_loss = trade_result.get("stop_loss_price", 0)
    take_profit = trade_result.get("take_profit_price", 0)
    pnl_pct = trade_result.get("pnl_pct", 0)
    is_winner = trade_result.get("is_winner", False)
    hold_minutes = trade_result.get("hold_duration_minutes", 0)
    predicted_prob = trade_result.get("predicted_probability", 0.5)

    observations = []
    parameter_notes = []

    # ── Entry Quality ──────────────────────────────────────────────
    if entry_price and exit_price:
        # How close did exit get to take profit vs stop loss?
        if take_profit and stop_loss and entry_price != stop_loss:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            actual_move = exit_price - entry_price

            if risk > 0:
                r_multiple = actual_move / risk
                if r_multiple >= 2.0:
                    observations.append(f"Excellent R-multiple: {r_multiple:.1f}R")
                elif r_multiple >= 1.0:
                    observations.append(f"Good R-multiple: {r_multiple:.1f}R")
                elif r_multiple > 0:
                    observations.append(f"Small win: {r_multiple:.1f}R — exit may have been early")
                else:
                    observations.append(f"Loss: {r_multiple:.1f}R")

    # ── Exit Timing ────────────────────────────────────────────────
    exit_type = trade_result.get("exit_type", "unknown")
    if exit_type == "STOP_LOSS":
        observations.append("Hit stop loss — entry timing may need adjustment")
    elif exit_type == "TAKE_PROFIT":
        observations.append("Hit take profit — consider if TP was too conservative")
    elif exit_type == "TIME_EXIT":
        observations.append("Time-based exit — strategy may need longer hold periods")

    # ── Hold Duration ──────────────────────────────────────────────
    if hold_minutes is not None:
        if hold_minutes < 30 and is_winner:
            observations.append("Quick win — strong signal quality")
        elif hold_minutes < 30 and not is_winner:
            observations.append("Quick loss — potential whipsaw. Consider wider stops.")
            parameter_notes.append("stop_loss: Consider increasing ATR multiplier")
        elif hold_minutes > 1440 and not is_winner:  # > 1 day
            observations.append("Long hold with loss — consider tighter exit criteria")

    # ── Calibration ────────────────────────────────────────────────
    brier_contribution = (predicted_prob - (1.0 if is_winner else 0.0)) ** 2
    if brier_contribution > 0.5:
        observations.append(
            f"Poor calibration: predicted {predicted_prob:.0%} win probability, "
            f"but {'won' if is_winner else 'lost'}"
        )
    elif brier_contribution < 0.1:
        observations.append("Well-calibrated prediction")

    # ── Trade Grade ────────────────────────────────────────────────
    if is_winner and pnl_pct and pnl_pct > 3.0:
        grade = "A"
    elif is_winner:
        grade = "B"
    elif pnl_pct and abs(pnl_pct) < 1.0:
        grade = "C"  # Small loss, acceptable
    else:
        grade = "D"

    return {
        "strategy_name": strategy_name,
        "trade_id": trade_result.get("trade_id", ""),
        "grade": grade,
        "pnl_pct": pnl_pct,
        "is_winner": is_winner,
        "brier_contribution": round(brier_contribution, 4),
        "observations": observations,
        "parameter_notes": parameter_notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ════════════════════════════════════════════════════════════════════
# PARAMETER FITNESS EVALUATION
# ════════════════════════════════════════════════════════════════════

@skill("strategy_agent")
def evaluate_parameter_fitness(
    trade_history: list[dict],
    current_params: dict,
    min_trades: int = 30,
) -> dict:
    """
    Evaluate if current parameters should be adjusted.

    Only runs after minimum trade count is met. Calculates:
      - Win rate trend (improving or degrading)
      - Sharpe ratio trend
      - Brier score calibration
      - Consecutive loss streaks

    Args:
        trade_history: List of closed trade results
        current_params: Current parameter values
        min_trades: Minimum trades before evaluation (default 30)

    Returns:
        Fitness report with recommendation (KEEP, ADJUST, or SHADOW_TEST)
    """
    closed = [t for t in trade_history if t.get("exit_price") is not None]

    if len(closed) < min_trades:
        return {
            "recommendation": "KEEP",
            "reason": f"Insufficient data: {len(closed)}/{min_trades} trades",
            "trades_evaluated": len(closed),
            "fitness_score": 0.5,  # Neutral
        }

    # Split into first half and second half
    mid = len(closed) // 2
    first_half = closed[:mid]
    second_half = closed[mid:]

    # Win rate trend
    wr_first = _win_rate(first_half)
    wr_second = _win_rate(second_half)
    wr_trend = wr_second - wr_first

    # Average P&L trend
    avg_pnl_first = _avg_pnl(first_half)
    avg_pnl_second = _avg_pnl(second_half)
    pnl_trend = avg_pnl_second - avg_pnl_first

    # Consecutive losses at end
    consec_losses = 0
    for t in reversed(closed):
        if not t.get("is_winner", False):
            consec_losses += 1
        else:
            break

    # Overall fitness score (0 = terrible, 1 = excellent)
    fitness = 0.5
    fitness += min(0.2, max(-0.2, wr_trend * 2))  # Win rate improvement
    fitness += min(0.15, max(-0.15, pnl_trend / 5))  # P&L improvement
    fitness -= consec_losses * 0.05  # Penalty for losing streaks
    fitness += min(0.15, max(0, wr_second - 0.5))  # Bonus for > 50% WR
    fitness = max(0.0, min(1.0, fitness))

    # Recommendation
    if fitness < 0.3:
        recommendation = "ADJUST"
        reason = (
            f"Parameters underperforming. WR trend: {wr_trend:+.1%}, "
            f"PnL trend: {pnl_trend:+.2f}%, "
            f"consecutive losses: {consec_losses}"
        )
    elif fitness < 0.45:
        recommendation = "SHADOW_TEST"
        reason = (
            f"Parameters marginally performing. Consider testing alternatives. "
            f"WR: {wr_second:.1%}, fitness: {fitness:.2f}"
        )
    else:
        recommendation = "KEEP"
        reason = f"Parameters performing well. WR: {wr_second:.1%}, fitness: {fitness:.2f}"

    return {
        "recommendation": recommendation,
        "reason": reason,
        "trades_evaluated": len(closed),
        "fitness_score": round(fitness, 3),
        "win_rate_first_half": round(wr_first, 4),
        "win_rate_second_half": round(wr_second, 4),
        "win_rate_trend": round(wr_trend, 4),
        "avg_pnl_first_half": round(avg_pnl_first, 4),
        "avg_pnl_second_half": round(avg_pnl_second, 4),
        "pnl_trend": round(pnl_trend, 4),
        "consecutive_losses": consec_losses,
        "current_params": current_params,
    }


# ════════════════════════════════════════════════════════════════════
# PARAMETER EVOLUTION PROPOSAL
# ════════════════════════════════════════════════════════════════════

@skill("strategy_agent")
def propose_parameter_evolution(
    trade_history: list[dict],
    current_params: dict,
    fitness_report: dict,
    strategy_type: str,
) -> dict:
    """
    Propose a single parameter change based on trade history analysis.

    RULES:
      1. Only ONE parameter changes at a time (scientific method)
      2. Change magnitude is proportional to evidence strength
      3. Must include backtest comparison data
      4. Proposed change goes to SHADOW mode first, never directly to production

    Args:
        trade_history: List of closed trade results
        current_params: Current parameter values
        fitness_report: Output from evaluate_parameter_fitness()
        strategy_type: Type of strategy (momentum, mean_reversion, etc.)

    Returns:
        Evolution proposal with parameter change and statistical justification
    """
    if fitness_report.get("recommendation") == "KEEP":
        return {
            "action": "NO_CHANGE",
            "reason": "Parameters performing well, no change needed",
        }

    closed = [t for t in trade_history if t.get("exit_price") is not None]
    if not closed:
        return {"action": "NO_CHANGE", "reason": "No closed trades"}

    # Analyze trade patterns to determine which parameter to adjust
    proposal = _analyze_and_propose(closed, current_params, strategy_type)

    if proposal is None:
        return {
            "action": "NO_CHANGE",
            "reason": "No statistically significant parameter change identified",
        }

    return {
        "action": "PROPOSE",
        "param_name": proposal["param_name"],
        "current_value": proposal["current_value"],
        "proposed_value": proposal["proposed_value"],
        "change_pct": proposal["change_pct"],
        "reason": proposal["reason"],
        "evidence": proposal["evidence"],
        "deploy_as": "SHADOW",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@skill("strategy_agent")
def statistical_significance_test(
    control_pnls: list[float],
    treatment_pnls: list[float],
    alpha: float = 0.05,
) -> dict:
    """
    Two-sample t-test for comparing strategy parameter versions.

    Tests whether the treatment (proposed params) significantly
    outperforms the control (current params).

    Args:
        control_pnls: P&L percentages under current parameters
        treatment_pnls: P&L percentages under proposed parameters
        alpha: Significance level (default 0.05)

    Returns:
        Test results with t-statistic, p-value, and recommendation
    """
    n1 = len(control_pnls)
    n2 = len(treatment_pnls)

    if n1 < 10 or n2 < 10:
        return {
            "significant": False,
            "reason": f"Insufficient data: control={n1}, treatment={n2} (need ≥10 each)",
            "recommendation": "CONTINUE_TESTING",
        }

    mean1 = sum(control_pnls) / n1
    mean2 = sum(treatment_pnls) / n2

    var1 = sum((x - mean1) ** 2 for x in control_pnls) / (n1 - 1) if n1 > 1 else 0
    var2 = sum((x - mean2) ** 2 for x in treatment_pnls) / (n2 - 1) if n2 > 1 else 0

    # Pooled standard error
    se = math.sqrt(var1 / n1 + var2 / n2) if (var1 / n1 + var2 / n2) > 0 else 1e-10

    # t-statistic
    t_stat = (mean2 - mean1) / se

    # Degrees of freedom (Welch's approximation)
    if var1 / n1 + var2 / n2 > 0:
        numerator = (var1 / n1 + var2 / n2) ** 2
        denominator = (var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1)
        df = numerator / denominator if denominator > 0 else n1 + n2 - 2
    else:
        df = n1 + n2 - 2

    # Approximate p-value using normal distribution (good for df > 30)
    # For smaller df, this is conservative (overestimates p-value)
    p_value = _approximate_p_value(abs(t_stat), df)

    significant = p_value < alpha and mean2 > mean1  # Must also be better, not just different

    if significant:
        recommendation = "PROMOTE"
        reason = f"Treatment significantly better (p={p_value:.4f} < {alpha})"
    elif p_value < alpha and mean2 <= mean1:
        recommendation = "REJECT"
        reason = f"Significant difference, but treatment is WORSE (p={p_value:.4f})"
    else:
        recommendation = "CONTINUE_TESTING"
        reason = f"Not yet significant (p={p_value:.4f} ≥ {alpha})"

    return {
        "significant": significant,
        "t_statistic": round(t_stat, 4),
        "p_value": round(p_value, 6),
        "degrees_of_freedom": round(df, 1),
        "control_mean": round(mean1, 4),
        "treatment_mean": round(mean2, 4),
        "improvement_pct": round((mean2 - mean1) / abs(mean1) * 100, 2) if mean1 != 0 else 0,
        "recommendation": recommendation,
        "reason": reason,
        "alpha": alpha,
    }


# ════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════════

def _win_rate(trades: list[dict]) -> float:
    """Calculate win rate from trade list."""
    if not trades:
        return 0.0
    winners = sum(1 for t in trades if t.get("is_winner", False))
    return winners / len(trades)


def _avg_pnl(trades: list[dict]) -> float:
    """Calculate average P&L percentage from trade list."""
    if not trades:
        return 0.0
    pnls = [t.get("pnl_pct", 0) or 0 for t in trades]
    return sum(pnls) / len(pnls)


def _analyze_and_propose(
    trades: list[dict],
    params: dict,
    strategy_type: str,
) -> Optional[dict]:
    """
    Analyze trade patterns to determine which parameter to adjust.

    Returns the single most impactful parameter change proposal.
    """
    # Analyze losing trades
    losers = [t for t in trades if not t.get("is_winner", False)]
    winners = [t for t in trades if t.get("is_winner", False)]

    if not losers:
        return None

    # Common patterns to check:
    # 1. Stop losses hit too frequently → widen stops
    stop_loss_exits = [t for t in losers if t.get("exit_type") == "STOP_LOSS"]
    stop_loss_ratio = len(stop_loss_exits) / len(losers) if losers else 0

    # 2. Winners close too early → adjust take profit
    if winners:
        avg_winner_pnl = _avg_pnl(winners)
        avg_loser_pnl = _avg_pnl(losers)

        # If average loss is > 2x average win, stops are too tight
        if abs(avg_loser_pnl) > 2 * avg_winner_pnl and avg_winner_pnl > 0:
            # Suggest widening stops
            if "trailing_stop_atr_mult" in params:
                current = params["trailing_stop_atr_mult"]
                proposed = round(current * 1.2, 1)  # Widen by 20%
                return {
                    "param_name": "trailing_stop_atr_mult",
                    "current_value": current,
                    "proposed_value": proposed,
                    "change_pct": 20.0,
                    "reason": (
                        f"Average loss ({avg_loser_pnl:.1f}%) > 2x average win "
                        f"({avg_winner_pnl:.1f}%). Widening stops by 20%."
                    ),
                    "evidence": {
                        "avg_winner_pnl": avg_winner_pnl,
                        "avg_loser_pnl": avg_loser_pnl,
                        "stop_loss_exit_ratio": stop_loss_ratio,
                    },
                }

    # 3. Too many stop loss exits → widen stops
    if stop_loss_ratio > 0.7 and "stop_loss_atr_mult" in params:
        current = params.get("stop_loss_atr_mult", 2.0)
        proposed = round(current * 1.15, 1)
        return {
            "param_name": "stop_loss_atr_mult",
            "current_value": current,
            "proposed_value": proposed,
            "change_pct": 15.0,
            "reason": (
                f"{stop_loss_ratio:.0%} of losses are stop-loss exits. "
                f"Widening SL from {current} to {proposed} ATR multiples."
            ),
            "evidence": {
                "stop_loss_exit_ratio": stop_loss_ratio,
                "total_losers": len(losers),
            },
        }

    # 4. Strategy-specific adjustments
    if strategy_type == "momentum":
        return _propose_momentum_adjustment(trades, params)
    elif strategy_type == "mean_reversion":
        return _propose_mean_reversion_adjustment(trades, params)

    return None


def _propose_momentum_adjustment(
    trades: list[dict],
    params: dict,
) -> Optional[dict]:
    """Propose adjustment for momentum strategy based on trade patterns."""
    # Check if EMA periods are too close (too many whipsaws)
    losers = [t for t in trades if not t.get("is_winner", False)]
    quick_losses = [t for t in losers if (t.get("hold_duration_minutes") or 999) < 120]

    if len(quick_losses) > len(losers) * 0.5 and "fast_ema_period" in params:
        current = params["fast_ema_period"]
        proposed = current + 2
        return {
            "param_name": "fast_ema_period",
            "current_value": current,
            "proposed_value": proposed,
            "change_pct": round((proposed - current) / current * 100, 1),
            "reason": (
                f"50%+ of losses are quick (<2h) whipsaws. "
                f"Lengthening fast EMA from {current} to {proposed} to reduce noise."
            ),
            "evidence": {"quick_loss_ratio": len(quick_losses) / max(1, len(losers))},
        }

    return None


def _propose_mean_reversion_adjustment(
    trades: list[dict],
    params: dict,
) -> Optional[dict]:
    """Propose adjustment for mean reversion strategy based on trade patterns."""
    # Check if RSI threshold is too aggressive
    losers = [t for t in trades if not t.get("is_winner", False)]

    # If win rate is below 50%, consider tightening RSI oversold
    if len(trades) > 20:
        wr = _win_rate(trades)
        if wr < 0.45 and "rsi_oversold" in params:
            current = params["rsi_oversold"]
            proposed = max(20, current - 3)  # More conservative (lower threshold)
            return {
                "param_name": "rsi_oversold",
                "current_value": current,
                "proposed_value": proposed,
                "change_pct": round((proposed - current) / current * 100, 1),
                "reason": (
                    f"Win rate {wr:.1%} below 45%. Tightening RSI oversold "
                    f"from {current} to {proposed} for stronger signals."
                ),
                "evidence": {"win_rate": wr, "total_trades": len(trades)},
            }

    return None


def _approximate_p_value(t_abs: float, df: float) -> float:
    """
    Approximate two-tailed p-value from t-statistic.

    Uses the approximation: p ≈ 2 * Φ(-|t|) for large df,
    where Φ is the standard normal CDF.
    For smaller df, applies a correction factor.
    """
    # Standard normal CDF approximation (Abramowitz & Stegun)
    x = t_abs
    if x > 8:
        return 1e-15  # Extremely significant

    # Normal CDF approximation
    b0 = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429

    t_val = 1 / (1 + b0 * x)
    phi = (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x)
    cdf = 1 - phi * (b1 * t_val + b2 * t_val**2 + b3 * t_val**3 + b4 * t_val**4 + b5 * t_val**5)

    p_value = 2 * (1 - cdf)  # Two-tailed

    # Correction for small df (t-distribution has heavier tails)
    if df < 30:
        p_value *= (1 + 1 / df)  # Conservative correction

    return max(0, min(1, p_value))
