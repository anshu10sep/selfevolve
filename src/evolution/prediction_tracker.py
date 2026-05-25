"""
Prediction Tracker

Records agent predictions during trading and resolves outcomes
when trades close. This data feeds the Brier Score engine for
trust weight calculation.

Usage:
    # During trading — record each analyst's prediction
    tracker.record_prediction(
        agent_role="FUNDAMENTAL_ANALYST",
        trade_id="abc-123",
        ticker="AAPL",
        predicted_probability=0.75,  # 75% chance of profit
        confidence=0.8,
    )
    
    # When a trade closes — set the outcome for all predictions
    tracker.resolve_trade(trade_id="abc-123", profitable=True)
    
    # For Brier scoring — get resolved predictions
    preds = tracker.get_resolved_predictions("FUNDAMENTAL_ANALYST", window=30)
"""

from __future__ import annotations

import uuid
from typing import Optional

import structlog

from persistence.db import (
    create_prediction,
    update_prediction_outcome,
    get_predictions_for_agent,
    get_predictions_for_prompt_version,
)

logger = structlog.get_logger(component="prediction_tracker")


class PredictionTracker:
    """Tracks agent predictions and trade outcomes for Brier scoring."""

    def record_prediction(
        self,
        agent_role: str,
        trade_id: str,
        ticker: str,
        predicted_probability: float,
        confidence: float,
        prompt_version: int = 1,
        is_shadow: bool = False,
    ) -> dict:
        """Record a prediction made by an agent.
        
        Args:
            agent_role: The agent's role (e.g. FUNDAMENTAL_ANALYST)
            trade_id: ID of the trade this prediction is for
            ticker: Stock/crypto ticker
            predicted_probability: Agent's probability estimate (0.0-1.0)
            confidence: Agent's confidence in its prediction (0.0-1.0)
            prompt_version: Version of the prompt that generated this prediction
            is_shadow: True if from a shadow crew candidate prompt
        """
        # Clamp probability to [0, 1]
        predicted_probability = max(0.0, min(1.0, predicted_probability))
        confidence = max(0.0, min(1.0, confidence))
        
        prediction_id = str(uuid.uuid4())
        return create_prediction(
            id=prediction_id,
            agent_role=agent_role,
            trade_id=trade_id,
            ticker=ticker,
            predicted_probability=predicted_probability,
            confidence=confidence,
            prompt_version=prompt_version,
            is_shadow=is_shadow,
        )

    def resolve_trade(self, trade_id: str, profitable: bool) -> int:
        """Set the outcome for all predictions associated with a trade.
        
        Args:
            trade_id: The trade that closed
            profitable: True if the trade was profitable
            
        Returns:
            Number of predictions updated
        """
        outcome = 1 if profitable else 0
        return update_prediction_outcome(trade_id, outcome)

    def get_resolved_predictions(
        self,
        agent_role: str,
        window: int = 30,
        is_shadow: bool = False,
    ) -> list[dict]:
        """Get resolved predictions for Brier scoring.
        
        Args:
            agent_role: Agent role to query
            window: Maximum number of predictions to return
            is_shadow: If True, return shadow crew predictions
            
        Returns:
            List of prediction dicts with actual_outcome filled in
        """
        return get_predictions_for_agent(
            agent_role=agent_role,
            resolved_only=True,
            is_shadow=is_shadow,
            limit=window,
        )

    def get_version_predictions(
        self,
        agent_role: str,
        prompt_version: int,
    ) -> list[dict]:
        """Get predictions for a specific prompt version (for A/B testing)."""
        return get_predictions_for_prompt_version(
            agent_role=agent_role,
            prompt_version=prompt_version,
            resolved_only=True,
        )

    @staticmethod
    def extract_brier_inputs(
        predictions: list[dict],
    ) -> tuple[list[float], list[int]]:
        """Extract predicted probabilities and outcomes for Brier calculation.
        
        Returns:
            Tuple of (predicted_probabilities, actual_outcomes)
        """
        probs = []
        outcomes = []
        for p in predictions:
            if p.get("actual_outcome") is not None:
                probs.append(p["predicted_probability"])
                outcomes.append(p["actual_outcome"])
        return probs, outcomes


# Singleton instance
prediction_tracker = PredictionTracker()
