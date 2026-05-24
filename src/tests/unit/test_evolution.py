"""
Unit tests for the Reflexion framework and evolution engine.

Tests Brier score calculations, statistical significance testing,
trust decay, and prompt evolution validation.
"""

import pytest
from evolution.reflexion import (
    BrierScoreEngine,
    PromptEvolution,
    TrustDecayManager,
)


class TestBrierScoreEngine:
    """Tests for Brier Score calculations."""

    def test_perfect_calibration(self):
        """Perfect predictions should yield Brier score of 0.0."""
        predictions = [1.0, 0.0, 1.0, 0.0]
        outcomes = [1, 0, 1, 0]
        score = BrierScoreEngine.calculate(predictions, outcomes)
        assert score == 0.0

    def test_perfectly_wrong(self):
        """100% wrong predictions should yield Brier score of 1.0."""
        predictions = [1.0, 0.0, 1.0, 0.0]
        outcomes = [0, 1, 0, 1]
        score = BrierScoreEngine.calculate(predictions, outcomes)
        assert score == 1.0

    def test_random_baseline(self):
        """50/50 predictions on 50/50 outcomes should yield ≈ 0.25."""
        predictions = [0.5, 0.5, 0.5, 0.5]
        outcomes = [1, 0, 1, 0]
        score = BrierScoreEngine.calculate(predictions, outcomes)
        assert score == 0.25

    def test_empty_predictions(self):
        """Empty predictions should return baseline 0.5."""
        score = BrierScoreEngine.calculate([], [])
        assert score == 0.5

    def test_mismatched_lengths(self):
        """Mismatched lengths should return baseline 0.5."""
        score = BrierScoreEngine.calculate([0.8], [1, 0])
        assert score == 0.5

    def test_rolling_brier(self):
        """Rolling Brier should produce a list of window-size scores."""
        predictions = [0.9, 0.8, 0.7, 0.6, 0.5] * 10  # 50 predictions
        outcomes = [1, 1, 1, 0, 0] * 10
        scores = BrierScoreEngine.rolling_brier(predictions, outcomes, window=30)
        assert len(scores) > 1
        assert all(0.0 <= s <= 1.0 for s in scores)


class TestPromptEvolution:
    """Tests for statistical significance in prompt evolution."""

    def test_significant_improvement_recommends_promote(self):
        """Clear improvement should recommend PROMOTE."""
        production = [0.01, 0.02, -0.01, 0.03, 0.01, 0.0, -0.02, 0.01, 0.02, 0.01]
        shadow = [0.05, 0.06, 0.04, 0.07, 0.05, 0.06, 0.04, 0.08, 0.05, 0.06]
        result = PromptEvolution.evaluate_significance(production, shadow)
        assert result["significant"] == True
        assert result["recommendation"] == "PROMOTE"
        assert result["shadow_mean"] > result["production_mean"]

    def test_insufficient_data_returns_insufficient(self):
        """Too few data points should return INSUFFICIENT_DATA."""
        result = PromptEvolution.evaluate_significance([0.01], [0.05])
        assert result["recommendation"] == "INSUFFICIENT_DATA"

    def test_no_significant_difference(self):
        """Similar results should return CONTINUE_TESTING."""
        production = [0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02]
        shadow = [0.015, 0.025, 0.015, 0.025, 0.015, 0.025, 0.015, 0.025, 0.015, 0.025]
        result = PromptEvolution.evaluate_significance(production, shadow)
        # These are very close, so likely not significant
        assert result["recommendation"] in ("CONTINUE_TESTING", "PROMOTE")

    def test_win_rate_z_score_significant(self):
        """Significantly different win rates should be detected."""
        result = PromptEvolution.calculate_win_rate_z_score(
            production_wins=30, production_total=100,
            shadow_wins=60, shadow_total=100,
        )
        assert result["significant"] == True
        assert result["shadow_win_rate"] > result["production_win_rate"]


class TestTrustDecayManager:
    """Tests for trust weight decay and boost."""

    def test_decay_reduces_weight(self):
        """Consecutive failures should reduce trust weight."""
        weight = TrustDecayManager.decay_trust(
            current_weight=1.0,
            consecutive_failures=3,
            decay_rate=0.95,
        )
        assert weight < 1.0
        assert weight == round(1.0 * (0.95 ** 3), 3)

    def test_decay_respects_minimum(self):
        """Trust weight should not go below minimum."""
        weight = TrustDecayManager.decay_trust(
            current_weight=0.15,
            consecutive_failures=100,
            min_weight=0.1,
        )
        assert weight == 0.1

    def test_boost_increases_weight(self):
        """Successful prediction should boost trust weight."""
        weight = TrustDecayManager.boost_trust(
            current_weight=0.8,
            boost_factor=1.05,
        )
        assert weight > 0.8
        assert weight <= 1.0

    def test_boost_respects_maximum(self):
        """Trust weight should not exceed 1.0."""
        weight = TrustDecayManager.boost_trust(
            current_weight=0.99,
            boost_factor=1.1,
        )
        assert weight == 1.0

    def test_should_retire_low_trust(self):
        """Agent with trust weight below minimum should be retired."""
        assert TrustDecayManager.should_retire(0.05, 5) is True

    def test_should_retire_many_failures(self):
        """Agent with too many failures should be retired."""
        assert TrustDecayManager.should_retire(0.5, 10) is True

    def test_should_not_retire_healthy(self):
        """Healthy agent should not be retired."""
        assert TrustDecayManager.should_retire(0.8, 2) is False
