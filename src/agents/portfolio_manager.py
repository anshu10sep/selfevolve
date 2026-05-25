"""
Portfolio Manager Agent

The "conductor" that allocates capital across strategy agents based on
real-time performance, market regime, and risk constraints. Uses a
deterministic allocation engine — no LLM for capital decisions.

Responsibilities:
1. Daily allocation: Re-allocate capital across strategies every morning
2. Real-time monitoring: Track each strategy's P&L, drawdown, risk
3. Regime detection: Match market regime to strategy strengths
4. Kill switch: Shut down underperforming strategies
5. Capital rebalancing: Shift capital from losers to winners
6. Reporting: Generate performance reports for Jarvis
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.base_agent import BaseAgent
from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.strategies.strategy_base import (
    StrategyAgent,
    StrategyMode,
    MarketRegimeAffinity,
)
from agents.strategies.strategy_tracker import StrategyPerformanceTracker

logger = structlog.get_logger(component="portfolio_manager")


PORTFOLIO_MANAGER_CORE = """You are the Portfolio Manager of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the capital allocator. You decide how much capital each strategy agent
receives based on their risk-adjusted performance, the current market regime,
and portfolio-level risk constraints. You do NOT trade directly — you manage
the strategy agents that trade.

## Your Responsibilities:
1. Allocate capital across strategy agents based on performance
2. Detect market regime and adjust allocations accordingly
3. Enforce portfolio-level risk limits (max drawdown, concentration)
4. Shut down strategies that breach risk limits
5. Report portfolio performance to Jarvis

## Core Directives:
- Capital allocation is DETERMINISTIC — math-based, not LLM-based
- You never allocate more than total portfolio equity
- You always maintain a cash reserve (minimum 20% of portfolio)
- You rebalance at most once per day (pre-market)
- In PANIC regime, you move 100% to cash

## LLM Usage:
- Generating strategic allocation commentary for Jarvis reports
- Reflecting on allocation decisions during evolution cycles
"""


class PortfolioManager(BaseAgent):
    """
    Deterministic capital allocator across strategy agents.
    
    Allocation formula:
        Weight(i) = (sharpe_w × risk_adj_return(i)) 
                   + (recency_w × recent_perf(i))
                   + (regime_w × regime_fit(i))
                   - (dd_penalty × current_drawdown(i))
    """

    # ── Allocation Weights ─────────────────────────────────────────
    SHARPE_WEIGHT = 0.35
    RECENCY_WEIGHT = 0.25
    REGIME_WEIGHT = 0.25
    DRAWDOWN_PENALTY = 0.15

    # ── Risk Limits ────────────────────────────────────────────────
    MIN_CASH_RESERVE_PCT = 0.20
    MAX_SINGLE_STRATEGY_PCT = 0.30
    MAX_DRAWDOWN_KILL_PCT = 10.0
    MAX_CONSECUTIVE_LOSSES = 8

    # ── Regime → Strategy Affinity Scores ──────────────────────────
    AFFINITY_SCORES = {
        MarketRegimeAffinity.STRONG: 1.0,
        MarketRegimeAffinity.NEUTRAL: 0.5,
        MarketRegimeAffinity.WEAK: 0.1,
        MarketRegimeAffinity.DISABLED: 0.0,
    }

    def __init__(
        self,
        llm,
        total_equity: float = 100.0,
        trust_weight: float = 1.0,
    ):
        identity = AgentIdentity(
            agent_name="Portfolio Manager",
            agent_role=AgentRole.PORTFOLIO_MANAGER,
            agent_type=AgentType.DIRECTOR,
            identity_core=PORTFOLIO_MANAGER_CORE,
        )
        super().__init__(identity, llm, trust_weight)

        self._total_equity = total_equity
        self._strategies: dict[str, StrategyAgent] = {}
        self._current_regime: str = "SIDEWAYS"
        self._allocations: dict[str, float] = {}
        self._allocation_history: list[dict] = []
        self._kill_list: set[str] = set()
        self._tracker = StrategyPerformanceTracker()

    # ── Strategy Registration ──────────────────────────────────────

    def register_strategy(self, strategy: StrategyAgent) -> None:
        """Register a strategy agent for portfolio management."""
        self._strategies[strategy.strategy_name] = strategy
        self._tracker.register_strategy(strategy)
        logger.info(
            "strategy_registered_with_pm",
            strategy=strategy.strategy_name,
            mode=strategy.mode.value,
        )

    def remove_strategy(self, strategy_name: str) -> None:
        """Remove a strategy from the portfolio."""
        strategy = self._strategies.pop(strategy_name, None)
        if strategy:
            strategy.set_allocation(0.0)
        self._allocations.pop(strategy_name, None)

    # ── Regime Management ──────────────────────────────────────────

    def set_regime(self, regime: str) -> None:
        """Update the current market regime."""
        old = self._current_regime
        self._current_regime = regime.upper()
        if old != self._current_regime:
            logger.info(
                "regime_changed",
                old_regime=old,
                new_regime=self._current_regime,
            )

    # ── Core Allocation Engine ─────────────────────────────────────

    def calculate_allocations(self) -> dict[str, float]:
        """
        Calculate capital allocation for each strategy.
        
        This is the core deterministic allocation engine.
        No LLM is used — pure math.
        """
        if not self._strategies:
            return {}

        # PANIC mode: 100% cash
        if self._current_regime == "PANIC":
            allocations = {name: 0.0 for name in self._strategies}
            self._apply_allocations(allocations)
            return allocations

        # Available capital (after cash reserve)
        available = self._total_equity * (1.0 - self.MIN_CASH_RESERVE_PCT)

        # Calculate raw scores for each strategy
        raw_scores: dict[str, float] = {}

        for name, strategy in self._strategies.items():
            # Skip killed strategies
            if name in self._kill_list:
                raw_scores[name] = 0.0
                continue

            score = self._calculate_strategy_score(strategy)
            raw_scores[name] = max(0.0, score)

        # Normalize to sum = 1.0
        total_score = sum(raw_scores.values())
        if total_score <= 0:
            # Equal allocation if all scores are zero/negative
            active_count = sum(
                1 for s in raw_scores.values() if s >= 0
            )
            if active_count > 0:
                equal_share = available / active_count
                allocations = {
                    name: equal_share if score >= 0 else 0.0
                    for name, score in raw_scores.items()
                }
            else:
                allocations = {name: 0.0 for name in raw_scores}
        else:
            allocations = {
                name: (score / total_score) * available
                for name, score in raw_scores.items()
            }

        # Enforce single-strategy concentration limit
        max_single = self._total_equity * self.MAX_SINGLE_STRATEGY_PCT
        for name in allocations:
            if allocations[name] > max_single:
                excess = allocations[name] - max_single
                allocations[name] = max_single
                # Redistribute excess
                other_active = [
                    n for n in allocations
                    if n != name and allocations[n] > 0
                ]
                if other_active:
                    per_other = excess / len(other_active)
                    for n in other_active:
                        allocations[n] = min(
                            max_single,
                            allocations[n] + per_other,
                        )

        # Round allocations
        allocations = {
            name: round(alloc, 2) for name, alloc in allocations.items()
        }

        self._apply_allocations(allocations)
        return allocations

    def _calculate_strategy_score(self, strategy: StrategyAgent) -> float:
        """
        Calculate the composite allocation score for a strategy.
        
        Score = sharpe_component + recency_component 
              + regime_component - drawdown_component
        """
        perf_30d = strategy.get_performance(window_days=30)
        perf_7d = strategy.get_performance(window_days=7)

        # 1. Risk-adjusted return (Sharpe ratio, 30-day)
        sharpe = perf_30d.get("sharpe_ratio", 0.0)
        sharpe_score = max(0, min(1.0, sharpe / 2.0))  # Normalize: Sharpe 2 = max

        # 2. Recent performance (7-day P&L direction)
        recent_pnl = perf_7d.get("total_pnl_usd", 0.0)
        recent_score = 0.5  # Base
        if recent_pnl > 0:
            recent_score = min(1.0, 0.5 + recent_pnl / 10)
        elif recent_pnl < 0:
            recent_score = max(0.0, 0.5 + recent_pnl / 10)

        # 3. Regime fit
        affinity_map = strategy.get_regime_affinity()
        regime_affinity = affinity_map.get(
            self._current_regime, MarketRegimeAffinity.NEUTRAL
        )
        regime_score = self.AFFINITY_SCORES.get(regime_affinity, 0.5)

        # If regime affinity is DISABLED, zero out the strategy
        if regime_affinity == MarketRegimeAffinity.DISABLED:
            return 0.0

        # 4. Drawdown penalty
        max_dd = perf_30d.get("max_drawdown_pct", 0.0)
        dd_penalty = min(1.0, max_dd / self.MAX_DRAWDOWN_KILL_PCT)

        # Check kill conditions
        if max_dd >= self.MAX_DRAWDOWN_KILL_PCT:
            self._kill_strategy(strategy.strategy_name, f"Max drawdown {max_dd:.1f}% exceeded")
            return 0.0

        consec_losses = perf_30d.get("max_consecutive_losses", 0)
        if consec_losses >= self.MAX_CONSECUTIVE_LOSSES:
            self._kill_strategy(strategy.strategy_name, f"{consec_losses} consecutive losses")
            return 0.0

        # Composite score
        score = (
            self.SHARPE_WEIGHT * sharpe_score
            + self.RECENCY_WEIGHT * recent_score
            + self.REGIME_WEIGHT * regime_score
            - self.DRAWDOWN_PENALTY * dd_penalty
        )

        return score

    def _apply_allocations(self, allocations: dict[str, float]) -> None:
        """Apply the calculated allocations to strategy agents."""
        self._allocations = allocations
        for name, capital in allocations.items():
            strategy = self._strategies.get(name)
            if strategy:
                strategy.set_allocation(capital)

        # Record in history
        self._allocation_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "regime": self._current_regime,
            "total_equity": self._total_equity,
            "allocations": allocations,
        })

        logger.info(
            "allocations_applied",
            regime=self._current_regime,
            total_equity=self._total_equity,
            allocations=allocations,
        )

    def _kill_strategy(self, strategy_name: str, reason: str) -> None:
        """Kill a strategy due to risk breach."""
        self._kill_list.add(strategy_name)
        strategy = self._strategies.get(strategy_name)
        if strategy:
            strategy.set_allocation(0.0)

        logger.warning(
            "strategy_killed",
            strategy=strategy_name,
            reason=reason,
        )

    def revive_strategy(self, strategy_name: str) -> None:
        """Remove a strategy from the kill list."""
        self._kill_list.discard(strategy_name)
        logger.info("strategy_revived", strategy=strategy_name)

    # ── Equity Update ──────────────────────────────────────────────

    def update_equity(self, new_equity: float) -> None:
        """Update total portfolio equity (called after P&L changes)."""
        old = self._total_equity
        self._total_equity = new_equity
        logger.info(
            "equity_updated",
            old_equity=old,
            new_equity=new_equity,
            change_pct=round(((new_equity - old) / old) * 100, 2) if old > 0 else 0,
        )

    # ── Reporting ──────────────────────────────────────────────────

    def get_portfolio_state(self) -> dict[str, Any]:
        """Get full portfolio state for reporting."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_equity": self._total_equity,
            "cash_reserve": round(self._total_equity * self.MIN_CASH_RESERVE_PCT, 2),
            "deployed_capital": sum(self._allocations.values()),
            "regime": self._current_regime,
            "strategy_count": len(self._strategies),
            "killed_strategies": list(self._kill_list),
            "allocations": self._allocations,
            "strategy_performance": {
                name: strategy.get_performance()
                for name, strategy in self._strategies.items()
            },
        }

    def get_allocation_history(self, limit: int = 30) -> list[dict]:
        """Get recent allocation history."""
        return self._allocation_history[-limit:]

    async def generate_allocation_commentary(self) -> dict[str, Any]:
        """
        Use LLM to generate strategic commentary on current allocations.
        This is for Jarvis reports — NOT for allocation decisions.
        """
        state = self.get_portfolio_state()
        leaderboard = self._tracker.get_leaderboard()

        message = f"""Generate a brief strategic commentary on the current portfolio allocation.

PORTFOLIO STATE:
{state}

STRATEGY LEADERBOARD (30d):
{leaderboard[:5]}

REGIME: {self._current_regime}

Provide:
1. One-sentence portfolio health summary
2. Which strategies are performing best and why
3. Which strategies need attention
4. Regime outlook and any allocation adjustments to consider
Maximum 150 words.
"""
        return await self.invoke(message)

    # ── BaseAgent Required ─────────────────────────────────────────

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "content": f"Portfolio Manager error: {error}. "
                       "Allocations remain unchanged.",
            "status": "error",
            "allocations": self._allocations,
        }
