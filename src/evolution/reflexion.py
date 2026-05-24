"""
Reflexion Framework

Implements the self-evolution loop:
1. Brier Score calculation for agent probability calibration
2. Linguistic post-mortem generation
3. Rule consolidation (max 3 rules per agent)
4. Statistical significance testing for prompt evolution

The system evaluates DECISION QUALITY, not just OUTCOMES,
to avoid hindsight bias.
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone

import structlog
from scipy import stats

from config.constants import (
    BRIER_WINDOW_SIZE,
    EVOLUTION_P_VALUE_THRESHOLD,
    MAX_RULES_PER_AGENT,
)
from core.models.audit import EvolutionRecord

logger = structlog.get_logger(component="reflexion")


class BrierScoreEngine:
    """
    Evaluates agent prediction calibration using Brier Score.
    
    Formula: BS = (1/N) * Σ(predicted_probability - actual_outcome)²
    
    Lower is better:
    - 0.0 = perfect calibration
    - 0.25 = baseline (random guessing at 50%)
    - 1.0 = perfectly wrong
    """

    @staticmethod
    def calculate(
        predictions: list[float], outcomes: list[int]
    ) -> float:
        """
        Calculate Brier Score over a window of predictions.
        
        Args:
            predictions: List of predicted probabilities (0.0 to 1.0)
            outcomes: List of actual outcomes (0 or 1)
            
        Returns:
            Brier Score (lower = better calibrated)
        """
        if not predictions or len(predictions) != len(outcomes):
            return 0.5  # Baseline

        n = len(predictions)
        brier = sum(
            (p - o) ** 2 for p, o in zip(predictions, outcomes)
        ) / n
        return round(brier, 4)

    @staticmethod
    def rolling_brier(
        predictions: list[float],
        outcomes: list[int],
        window: int = BRIER_WINDOW_SIZE,
    ) -> list[float]:
        """Calculate rolling Brier Score over a sliding window."""
        if len(predictions) < window:
            return [BrierScoreEngine.calculate(predictions, outcomes)]

        scores = []
        for i in range(len(predictions) - window + 1):
            window_preds = predictions[i : i + window]
            window_outcomes = outcomes[i : i + window]
            scores.append(BrierScoreEngine.calculate(window_preds, window_outcomes))
        return scores


class MarketContextReplay:
    """
    Provides the exact data available at the moment of a trade
    for post-mortem evaluation.
    
    The Meta-Review evaluates whether the agent adhered to its
    mathematical constraints, IGNORING the final P&L.
    """

    @staticmethod
    def capture_context(
        ticker: str,
        trade_time: datetime,
        market_data: dict,
        agent_inputs: dict,
    ) -> dict[str, Any]:
        """Capture a deterministic state snapshot for post-mortem."""
        return {
            "ticker": ticker,
            "trade_time": trade_time.isoformat(),
            "market_data_at_decision": market_data,
            "agent_inputs_at_decision": agent_inputs,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }


class PromptEvolution:
    """
    Statistically rigorous prompt evolution.
    
    New prompts are only promoted to production if they demonstrate
    statistically significant improvement (p < 0.05) over the
    current production prompt.
    """

    @staticmethod
    def evaluate_significance(
        production_results: list[float],
        shadow_results: list[float],
    ) -> dict[str, Any]:
        """
        Test statistical significance of shadow vs production performance.
        
        Uses Welch's t-test for unequal variance samples.
        
        Args:
            production_results: P&L or score results from production prompt
            shadow_results: P&L or score results from shadow prompt
            
        Returns:
            Dict with t_statistic, p_value, significant, and recommendation
        """
        if len(production_results) < 5 or len(shadow_results) < 5:
            return {
                "t_statistic": 0.0,
                "p_value": 1.0,
                "significant": False,
                "recommendation": "INSUFFICIENT_DATA",
                "production_mean": 0.0,
                "shadow_mean": 0.0,
            }

        t_stat, p_value = stats.ttest_ind(
            shadow_results, production_results, equal_var=False
        )

        prod_mean = sum(production_results) / len(production_results)
        shadow_mean = sum(shadow_results) / len(shadow_results)

        significant = p_value < EVOLUTION_P_VALUE_THRESHOLD
        improvement = shadow_mean > prod_mean

        if significant and improvement:
            recommendation = "PROMOTE"
        elif significant and not improvement:
            recommendation = "ROLLBACK"
        else:
            recommendation = "CONTINUE_TESTING"

        return {
            "t_statistic": round(float(t_stat), 4),
            "p_value": round(float(p_value), 4),
            "significant": significant,
            "recommendation": recommendation,
            "production_mean": round(prod_mean, 4),
            "shadow_mean": round(shadow_mean, 4),
        }

    @staticmethod
    def calculate_win_rate_z_score(
        production_wins: int,
        production_total: int,
        shadow_wins: int,
        shadow_total: int,
    ) -> dict[str, Any]:
        """
        Z-score test for win rate comparison.
        
        Useful when comparing binary outcomes (profitable/not profitable).
        """
        if production_total == 0 or shadow_total == 0:
            return {
                "z_score": 0.0,
                "p_value": 1.0,
                "significant": False,
            }

        p1 = production_wins / production_total
        p2 = shadow_wins / shadow_total
        p_pool = (production_wins + shadow_wins) / (production_total + shadow_total)

        denominator = (
            p_pool * (1 - p_pool) * (1 / production_total + 1 / shadow_total)
        ) ** 0.5

        if denominator == 0:
            return {"z_score": 0.0, "p_value": 1.0, "significant": False}

        z = (p2 - p1) / denominator
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))

        return {
            "z_score": round(float(z), 4),
            "p_value": round(float(p_value), 4),
            "significant": p_value < EVOLUTION_P_VALUE_THRESHOLD,
            "production_win_rate": round(p1, 4),
            "shadow_win_rate": round(p2, 4),
        }


class TrustDecayManager:
    """
    Manages transparent trust weight decay for agents.
    
    Trust scores are stored in PostgreSQL and directly inform
    the deterministic ensemble weights — they are never hidden
    in an LLM's context window.
    """

    @staticmethod
    def decay_trust(
        current_weight: float,
        consecutive_failures: int,
        decay_rate: float = 0.95,
        min_weight: float = 0.1,
    ) -> float:
        """
        Apply exponential trust decay based on consecutive failures.
        
        Each failure multiplies the weight by decay_rate.
        Weight cannot go below min_weight.
        """
        decayed = current_weight * (decay_rate ** consecutive_failures)
        return max(min_weight, round(decayed, 3))

    @staticmethod
    def boost_trust(
        current_weight: float,
        boost_factor: float = 1.05,
        max_weight: float = 1.0,
    ) -> float:
        """Boost trust weight after successful prediction."""
        boosted = current_weight * boost_factor
        return min(max_weight, round(boosted, 3))

    @staticmethod
    def should_retire(
        trust_weight: float,
        consecutive_failures: int,
        min_weight: float = 0.1,
        max_failures: int = 10,
    ) -> bool:
        """Determine if an agent should be retired."""
        return trust_weight <= min_weight or consecutive_failures >= max_failures
