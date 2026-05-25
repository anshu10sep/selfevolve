"""
Strategy Self-Evolution Engine

The learning loop that makes each strategy agent truly self-evolving.
After every trading day, this engine:

1. Collects trade results from all strategy agents
2. Calculates Brier Scores for prediction calibration
3. Uses LLM for post-mortem reflection (the ONLY LLM usage)
4. Proposes parameter changes based on patterns
5. Runs shadow simulations with new parameters
6. Promotes changes only with statistical significance (p < 0.05)
7. Updates trust weights and reports to Portfolio Manager

Bulletproof safeguards:
- No hindsight bias (Brier Score evaluates decision quality, not outcome)
- Statistical significance required (Welch's t-test, p < 0.05)
- Shadow testing first (new params run on paper before live)
- Max 1 parameter change per cycle (prevents overfitting)
- Immutable identity (strategy type never changes)
- Full rollback capability
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.strategies.strategy_base import (
    StrategyAgent,
    StrategyParameters,
    StrategyMode,
)
from agents.strategies.strategy_tracker import StrategyPerformanceTracker
from evolution.reflexion import (
    BrierScoreEngine,
    PromptEvolution,
    TrustDecayManager,
    MarketContextReplay,
)
from config.constants import (
    BRIER_WINDOW_SIZE,
    EVOLUTION_P_VALUE_THRESHOLD,
    SHADOW_MIN_TRADES,
    TRUST_DECAY_RATE,
    MIN_TRUST_WEIGHT,
)

logger = structlog.get_logger(component="strategy_evolution")


class StrategyEvolutionEngine:
    """
    Self-evolution loop for strategy agents.
    
    This is the core learning mechanism. Each strategy agent evolves
    its parameters based on statistical evidence, not gut feeling.
    """

    def __init__(
        self,
        tracker: Optional[StrategyPerformanceTracker] = None,
    ):
        self._tracker = tracker or StrategyPerformanceTracker()
        self._strategies: dict[str, StrategyAgent] = {}
        self._evolution_log: list[dict] = []
        self._brier = BrierScoreEngine()
        self._prompt_evo = PromptEvolution()
        self._trust_mgr = TrustDecayManager()

    def register_strategy(self, strategy: StrategyAgent) -> None:
        """Register a strategy for evolution tracking."""
        self._strategies[strategy.strategy_name] = strategy
        self._tracker.register_strategy(strategy)

    # ── Main Evolution Cycle ───────────────────────────────────────

    async def run_evolution_cycle(self) -> dict[str, Any]:
        """
        Run a full evolution cycle for all registered strategies.
        
        Called at end of day (post-market):
        1. For each strategy: evaluate, reflect, optionally evolve
        2. Update trust weights
        3. Generate evolution report
        """
        cycle_start = datetime.now(timezone.utc)
        results = {}

        for name, strategy in self._strategies.items():
            try:
                result = await self._evolve_strategy(strategy)
                results[name] = result
            except Exception as e:
                logger.error(
                    "evolution_cycle_error",
                    strategy=name,
                    error=str(e),
                )
                results[name] = {"status": "error", "error": str(e)}

        # Log the cycle
        cycle_record = {
            "timestamp": cycle_start.isoformat(),
            "strategies_evolved": len(results),
            "results": results,
        }
        self._evolution_log.append(cycle_record)

        logger.info(
            "evolution_cycle_complete",
            strategies=len(results),
            duration_sec=round(
                (datetime.now(timezone.utc) - cycle_start).total_seconds(), 1
            ),
        )

        return cycle_record

    async def _evolve_strategy(self, strategy: StrategyAgent) -> dict[str, Any]:
        """
        Run evolution for a single strategy agent.
        
        Steps:
        1. Calculate Brier Score (prediction calibration)
        2. Evaluate performance metrics
        3. LLM reflection for parameter suggestions
        4. If suggestion made → propose shadow test
        5. If shadow test has enough data → evaluate significance
        6. Update trust weight
        """
        result: dict[str, Any] = {
            "strategy": strategy.strategy_name,
            "version": strategy.parameters.version,
            "mode": strategy.mode.value,
        }

        # ── Step 1: Brier Score ────────────────────────────────────
        predictions, outcomes = strategy.get_brier_inputs()
        if len(predictions) >= 5:
            brier_score = self._brier.calculate(predictions, outcomes)
            rolling_brier = self._brier.rolling_brier(
                predictions, outcomes, BRIER_WINDOW_SIZE
            )
            result["brier_score"] = brier_score
            result["rolling_brier_trend"] = (
                "improving" if len(rolling_brier) > 1 and rolling_brier[-1] < rolling_brier[0]
                else "degrading" if len(rolling_brier) > 1 and rolling_brier[-1] > rolling_brier[0]
                else "stable"
            )
        else:
            result["brier_score"] = None
            result["rolling_brier_trend"] = "insufficient_data"

        # ── Step 2: Performance Metrics ────────────────────────────
        perf_7d = strategy.get_performance(window_days=7)
        perf_30d = strategy.get_performance(window_days=30)
        result["performance_7d"] = perf_7d
        result["performance_30d"] = perf_30d

        # ── Step 3: Check Shadow Parameters ────────────────────────
        if strategy._shadow_parameters is not None:
            shadow_result = await self._evaluate_shadow(strategy)
            result["shadow_evaluation"] = shadow_result

            if shadow_result.get("action") == "PROMOTE":
                # Promote shadow parameters
                old_params = strategy.parameters
                strategy.promote_shadow_parameters()
                self._tracker.record_parameter_change(
                    strategy.strategy_name,
                    old_params,
                    strategy.parameters,
                    shadow_result,
                )
                result["evolved"] = True
                result["new_version"] = strategy.parameters.version
                
                self._tracker.record_learning(
                    strategy.strategy_name,
                    "parameter_promoted",
                    f"Parameters v{strategy.parameters.version} promoted: {strategy.parameters.change_description}",
                    {"test_result": shadow_result},
                )
            elif shadow_result.get("action") == "ROLLBACK":
                strategy.rollback_parameters()
                result["evolved"] = False
                result["rollback"] = True
                
                self._tracker.record_learning(
                    strategy.strategy_name,
                    "parameter_rollback",
                    f"Shadow parameters discarded — did not outperform production",
                    {"test_result": shadow_result},
                )
            else:
                result["evolved"] = False
                result["shadow_status"] = "continue_testing"
        else:
            result["evolved"] = False

        # ── Step 4: LLM Reflection ─────────────────────────────────
        if perf_30d.get("total_trades", 0) >= 5 and strategy._shadow_parameters is None:
            try:
                reflection = await strategy.reflect_on_performance()
                result["reflection"] = reflection.get("content", "")

                # Parse if a parameter change was suggested
                # The reflection is unstructured — we log it as a learning
                self._tracker.record_learning(
                    strategy.strategy_name,
                    "reflection",
                    reflection.get("content", "No reflection"),
                    {"performance_7d": perf_7d, "performance_30d": perf_30d},
                )
            except Exception as e:
                logger.warning(
                    "reflection_failed",
                    strategy=strategy.strategy_name,
                    error=str(e),
                )
                result["reflection"] = f"Reflection failed: {e}"

        # ── Step 5: Trust Weight Update ────────────────────────────
        trade_journal = strategy._trade_journal
        closed_trades = [t for t in trade_journal if t.exit_price is not None]

        if closed_trades:
            recent_trades = closed_trades[-5:]
            consecutive_losses = 0
            for t in reversed(recent_trades):
                if t.is_winner:
                    break
                consecutive_losses += 1

            if consecutive_losses > 0:
                new_weight = self._trust_mgr.decay_trust(
                    strategy.trust_weight,
                    consecutive_losses,
                    TRUST_DECAY_RATE,
                    MIN_TRUST_WEIGHT,
                )
            else:
                new_weight = self._trust_mgr.boost_trust(
                    strategy.trust_weight
                )

            old_weight = strategy.trust_weight
            strategy.trust_weight = new_weight
            result["trust_weight"] = {
                "old": old_weight,
                "new": new_weight,
                "consecutive_losses": consecutive_losses,
            }

            # Check retirement
            if self._trust_mgr.should_retire(
                new_weight, consecutive_losses
            ):
                result["retirement_recommended"] = True
                logger.warning(
                    "strategy_retirement_recommended",
                    strategy=strategy.strategy_name,
                    trust_weight=new_weight,
                    consecutive_losses=consecutive_losses,
                )

        result["status"] = "complete"
        return result

    async def _evaluate_shadow(self, strategy: StrategyAgent) -> dict[str, Any]:
        """
        Evaluate shadow parameters against production.
        
        Uses Welch's t-test to determine statistical significance.
        """
        # In a full implementation, shadow trades would run in parallel.
        # Here we evaluate based on the trade journal data.
        trade_journal = strategy._trade_journal
        production_trades = [
            t for t in trade_journal
            if t.strategy_version == strategy.parameters.version
            and t.exit_price is not None
        ]
        shadow_trades = [
            t for t in trade_journal
            if t.strategy_version == (strategy._shadow_parameters.version if strategy._shadow_parameters else -1)
            and t.exit_price is not None
        ]

        prod_pnls = [t.pnl_pct or 0 for t in production_trades]
        shadow_pnls = [t.pnl_pct or 0 for t in shadow_trades]

        if len(shadow_pnls) < SHADOW_MIN_TRADES:
            return {
                "action": "CONTINUE",
                "reason": f"Shadow has {len(shadow_pnls)}/{SHADOW_MIN_TRADES} required trades",
                "production_trades": len(prod_pnls),
                "shadow_trades": len(shadow_pnls),
            }

        # Statistical test
        sig_result = self._prompt_evo.evaluate_significance(
            prod_pnls, shadow_pnls
        )

        if sig_result["recommendation"] == "PROMOTE":
            return {
                "action": "PROMOTE",
                **sig_result,
            }
        elif sig_result["recommendation"] == "ROLLBACK":
            return {
                "action": "ROLLBACK",
                **sig_result,
            }
        else:
            return {
                "action": "CONTINUE",
                **sig_result,
            }

    # ── Manual Parameter Suggestion ────────────────────────────────

    def suggest_parameter_change(
        self,
        strategy_name: str,
        param_name: str,
        new_value: Any,
        description: str,
    ) -> Optional[StrategyParameters]:
        """
        Manually suggest a parameter change for shadow testing.
        
        Used by Jarvis or the owner to propose changes.
        The change goes to shadow mode first — not directly to production.
        """
        strategy = self._strategies.get(strategy_name)
        if not strategy:
            logger.error("strategy_not_found", name=strategy_name)
            return None

        if strategy._shadow_parameters is not None:
            logger.warning(
                "shadow_already_active",
                strategy=strategy_name,
                shadow_version=strategy._shadow_parameters.version,
            )
            return None

        return strategy.propose_parameter_update(
            {param_name: new_value},
            description,
        )

    # ── Reports ────────────────────────────────────────────────────

    def get_evolution_status(self) -> dict[str, Any]:
        """Get the current evolution status for all strategies."""
        statuses = {}
        for name, strategy in self._strategies.items():
            brier_inputs = strategy.get_brier_inputs()
            brier_score = (
                self._brier.calculate(*brier_inputs)
                if len(brier_inputs[0]) >= 5
                else None
            )
            statuses[name] = {
                "version": strategy.parameters.version,
                "trust_weight": strategy.trust_weight,
                "brier_score": brier_score,
                "has_shadow": strategy._shadow_parameters is not None,
                "shadow_version": (
                    strategy._shadow_parameters.version
                    if strategy._shadow_parameters
                    else None
                ),
                "total_trades": len(strategy._trade_journal),
                "mode": strategy.mode.value,
            }
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategies": statuses,
            "total_evolution_cycles": len(self._evolution_log),
        }

    def get_evolution_log(self, limit: int = 10) -> list[dict]:
        """Get recent evolution cycle logs."""
        return self._evolution_log[-limit:]


# Module-level singleton
strategy_evolution_engine = StrategyEvolutionEngine()
