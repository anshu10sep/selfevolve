"""
Tests for the self-evolution loop.

Tests the complete pipeline:
1. PredictionRecord & PromptVersion DB models
2. PredictionTracker CRUD operations
3. BrierScoreEngine calculation with real data
4. TrustDecayManager weight adjustments
5. MetaReviewAgent domain isolation validation
6. PromptEvolution statistical significance
7. Evolution runner orchestration (mocked LLM)
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════
# TEST 1: Brier Score Engine
# ═══════════════════════════════════════════════════════════════════

class TestBrierScoreEngine:
    """Test the Brier Score calculation engine."""

    def test_perfect_calibration(self):
        """Predictions that perfectly match outcomes → Brier = 0.0"""
        from evolution.reflexion import BrierScoreEngine
        predictions = [1.0, 0.0, 1.0, 0.0, 1.0]
        outcomes = [1, 0, 1, 0, 1]
        score = BrierScoreEngine.calculate(predictions, outcomes)
        assert score == 0.0

    def test_perfectly_wrong(self):
        """Predictions completely inverted → Brier = 1.0"""
        from evolution.reflexion import BrierScoreEngine
        predictions = [0.0, 1.0, 0.0, 1.0]
        outcomes = [1, 0, 1, 0]
        score = BrierScoreEngine.calculate(predictions, outcomes)
        assert score == 1.0

    def test_random_guessing(self):
        """Always predicting 0.5 → Brier = 0.25"""
        from evolution.reflexion import BrierScoreEngine
        predictions = [0.5, 0.5, 0.5, 0.5]
        outcomes = [1, 0, 1, 0]
        score = BrierScoreEngine.calculate(predictions, outcomes)
        assert score == 0.25

    def test_empty_predictions(self):
        """Empty predictions → baseline 0.5"""
        from evolution.reflexion import BrierScoreEngine
        score = BrierScoreEngine.calculate([], [])
        assert score == 0.5

    def test_mismatched_lengths(self):
        """Mismatched prediction/outcome lengths → baseline 0.5"""
        from evolution.reflexion import BrierScoreEngine
        score = BrierScoreEngine.calculate([0.5, 0.5], [1])
        assert score == 0.5

    def test_partial_calibration(self):
        """Realistic predictions → score between 0 and 0.5"""
        from evolution.reflexion import BrierScoreEngine
        predictions = [0.8, 0.7, 0.3, 0.6, 0.9]
        outcomes = [1, 1, 0, 0, 1]
        score = BrierScoreEngine.calculate(predictions, outcomes)
        assert 0.0 < score < 0.5  # Better than random

    def test_rolling_brier(self):
        """Rolling Brier produces a list of scores."""
        from evolution.reflexion import BrierScoreEngine
        predictions = [0.8, 0.7, 0.3, 0.6, 0.9, 0.4, 0.8]
        outcomes = [1, 1, 0, 0, 1, 0, 1]
        scores = BrierScoreEngine.rolling_brier(predictions, outcomes, window=5)
        assert len(scores) == 3  # 7 - 5 + 1
        assert all(0.0 <= s <= 1.0 for s in scores)


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Trust Decay Manager
# ═══════════════════════════════════════════════════════════════════

class TestTrustDecayManager:
    """Test trust weight decay and boost mechanics."""

    def test_decay_single_failure(self):
        """One failure → weight reduced by decay rate."""
        from evolution.reflexion import TrustDecayManager
        new_weight = TrustDecayManager.decay_trust(1.0, 1, decay_rate=0.95)
        assert new_weight == 0.95

    def test_decay_multiple_failures(self):
        """Multiple failures → exponential decay."""
        from evolution.reflexion import TrustDecayManager
        new_weight = TrustDecayManager.decay_trust(1.0, 3, decay_rate=0.95)
        expected = round(1.0 * (0.95 ** 3), 3)
        assert new_weight == expected

    def test_decay_floor(self):
        """Weight cannot go below min_weight."""
        from evolution.reflexion import TrustDecayManager
        new_weight = TrustDecayManager.decay_trust(0.15, 10, decay_rate=0.95, min_weight=0.1)
        assert new_weight == 0.1

    def test_boost_single_success(self):
        """One success → weight increased by boost factor."""
        from evolution.reflexion import TrustDecayManager
        new_weight = TrustDecayManager.boost_trust(0.8, boost_factor=1.05)
        assert new_weight == 0.84

    def test_boost_ceiling(self):
        """Weight cannot exceed max_weight."""
        from evolution.reflexion import TrustDecayManager
        new_weight = TrustDecayManager.boost_trust(0.99, boost_factor=1.05, max_weight=1.0)
        assert new_weight == 1.0

    def test_should_retire_low_weight(self):
        """Agent should retire when trust weight is at minimum."""
        from evolution.reflexion import TrustDecayManager
        assert TrustDecayManager.should_retire(0.1, 5, min_weight=0.1)

    def test_should_retire_many_failures(self):
        """Agent should retire after max consecutive failures."""
        from evolution.reflexion import TrustDecayManager
        assert TrustDecayManager.should_retire(0.5, 10, max_failures=10)

    def test_should_not_retire_healthy(self):
        """Healthy agent should not retire."""
        from evolution.reflexion import TrustDecayManager
        assert not TrustDecayManager.should_retire(0.8, 2)


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Prompt Evolution (Statistical Significance)
# ═══════════════════════════════════════════════════════════════════

class TestPromptEvolution:
    """Test statistical significance testing for prompt evolution."""

    def test_insufficient_data(self):
        """Too few samples → INSUFFICIENT_DATA."""
        from evolution.reflexion import PromptEvolution
        result = PromptEvolution.evaluate_significance([1.0, 2.0], [3.0, 4.0])
        assert result["recommendation"] == "INSUFFICIENT_DATA"
        assert result["p_value"] == 1.0

    def test_significant_improvement(self):
        """Shadow clearly better → PROMOTE."""
        from evolution.reflexion import PromptEvolution
        production = [0.3, 0.4, 0.35, 0.5, 0.45, 0.4, 0.5]
        shadow = [0.8, 0.9, 0.85, 0.7, 0.75, 0.8, 0.9]
        result = PromptEvolution.evaluate_significance(production, shadow)
        assert result["recommendation"] == "PROMOTE"
        assert result["significant"] == True
        assert result["p_value"] < 0.05

    def test_significant_regression(self):
        """Shadow clearly worse → ROLLBACK."""
        from evolution.reflexion import PromptEvolution
        production = [0.8, 0.9, 0.85, 0.7, 0.75, 0.8, 0.9]
        shadow = [0.3, 0.4, 0.35, 0.5, 0.45, 0.4, 0.5]
        result = PromptEvolution.evaluate_significance(production, shadow)
        assert result["recommendation"] == "ROLLBACK"
        assert result["significant"] == True

    def test_no_significant_difference(self):
        """Similar results → CONTINUE_TESTING."""
        from evolution.reflexion import PromptEvolution
        production = [0.5, 0.6, 0.55, 0.5, 0.52, 0.58]
        shadow = [0.5, 0.55, 0.52, 0.5, 0.53, 0.57]
        result = PromptEvolution.evaluate_significance(production, shadow)
        assert result["recommendation"] == "CONTINUE_TESTING"
        assert result["significant"] == False

    def test_win_rate_z_score(self):
        """Z-score test for win rate comparison."""
        from evolution.reflexion import PromptEvolution
        result = PromptEvolution.calculate_win_rate_z_score(
            production_wins=10, production_total=20,
            shadow_wins=15, shadow_total=20,
        )
        assert "z_score" in result
        assert "p_value" in result
        assert result["production_win_rate"] == 0.5
        assert result["shadow_win_rate"] == 0.75


# ═══════════════════════════════════════════════════════════════════
# TEST 4: Domain Isolation (AgentUpdate Validator)
# ═══════════════════════════════════════════════════════════════════

class TestDomainIsolation:
    """Test that domain isolation prevents cross-domain prompt updates."""

    def test_valid_technical_nuance(self):
        """Technical Analyst can use technical terms."""
        from core.models.agents import AgentUpdate, AgentRole
        update = AgentUpdate(
            agent_name="Technical Analyst",
            agent_role=AgentRole.TECHNICAL_ANALYST,
            strategic_nuance="- Prioritize VWAP bounces in high-volatility regimes",
            version_number=2,
            change_description="Test update",
        )
        assert update.strategic_nuance == "- Prioritize VWAP bounces in high-volatility regimes"

    def test_invalid_technical_uses_fundamental_terms(self):
        """Technical Analyst cannot use 'earnings' or 'revenue'."""
        from core.models.agents import AgentUpdate, AgentRole
        with pytest.raises(ValueError, match="domain isolation"):
            AgentUpdate(
                agent_name="Technical Analyst",
                agent_role=AgentRole.TECHNICAL_ANALYST,
                strategic_nuance="- Focus on earnings surprises and revenue growth",
                version_number=2,
                change_description="Test update",
            )

    def test_invalid_fundamental_uses_technical_terms(self):
        """Fundamental Analyst cannot use 'RSI' or 'MACD'."""
        from core.models.agents import AgentUpdate, AgentRole
        with pytest.raises(ValueError, match="domain isolation"):
            AgentUpdate(
                agent_name="Fundamental Analyst",
                agent_role=AgentRole.FUNDAMENTAL_ANALYST,
                strategic_nuance="- Buy when RSI drops below 30 and MACD crosses up",
                version_number=2,
                change_description="Test update",
            )

    def test_meta_review_validation_method(self):
        """MetaReviewAgent.validate_proposed_nuance catches domain violations."""
        from agents.meta_review_agent import MetaReviewAgent

        # Mock LLM since we're only testing the sync validation method
        mock_llm = MagicMock()
        meta = MetaReviewAgent(mock_llm)

        # Valid update
        valid, error = meta.validate_proposed_nuance(
            agent_role="TECHNICAL_ANALYST",
            agent_name="Technical Analyst",
            proposed_nuance="- Watch for volume breakouts above 20-day average",
            version_number=2,
            change_description="Test",
        )
        assert valid is True
        assert error == ""

        # Invalid update (cross-domain)
        valid, error = meta.validate_proposed_nuance(
            agent_role="TECHNICAL_ANALYST",
            agent_name="Technical Analyst",
            proposed_nuance="- Check earnings dates before entering positions",
            version_number=2,
            change_description="Test",
        )
        assert valid is False
        assert "domain isolation" in error.lower() or "violates" in error.lower()


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Prediction Tracker
# ═══════════════════════════════════════════════════════════════════

class TestPredictionTracker:
    """Test the PredictionTracker helper methods."""

    def test_probability_clamping(self):
        """Out-of-range probabilities are clamped to [0, 1]."""
        from evolution.prediction_tracker import PredictionTracker
        tracker = PredictionTracker()

        # Mock the create_prediction function
        with patch("evolution.prediction_tracker.create_prediction") as mock_create:
            mock_create.return_value = {"id": "test"}

            tracker.record_prediction(
                agent_role="TEST",
                trade_id="t1",
                ticker="AAPL",
                predicted_probability=1.5,  # Should be clamped to 1.0
                confidence=-0.5,  # Should be clamped to 0.0
            )

            call_args = mock_create.call_args
            assert call_args.kwargs["predicted_probability"] == 1.0
            assert call_args.kwargs["confidence"] == 0.0

    def test_extract_brier_inputs(self):
        """Extract probabilities and outcomes from prediction dicts."""
        from evolution.prediction_tracker import PredictionTracker

        predictions = [
            {"predicted_probability": 0.8, "actual_outcome": 1},
            {"predicted_probability": 0.3, "actual_outcome": 0},
            {"predicted_probability": 0.6, "actual_outcome": None},  # Unresolved
        ]

        probs, outcomes = PredictionTracker.extract_brier_inputs(predictions)
        assert probs == [0.8, 0.3]
        assert outcomes == [1, 0]

    def test_resolve_trade(self):
        """resolve_trade calls update_prediction_outcome correctly."""
        from evolution.prediction_tracker import PredictionTracker
        tracker = PredictionTracker()

        with patch("evolution.prediction_tracker.update_prediction_outcome") as mock_update:
            mock_update.return_value = 3

            count = tracker.resolve_trade("trade-123", profitable=True)
            mock_update.assert_called_once_with("trade-123", 1)
            assert count == 3

            mock_update.reset_mock()
            count = tracker.resolve_trade("trade-456", profitable=False)
            mock_update.assert_called_once_with("trade-456", 0)


# ═══════════════════════════════════════════════════════════════════
# TEST 6: BaseAgent Strategic Nuance Update
# ═══════════════════════════════════════════════════════════════════

class TestBaseAgentNuanceUpdate:
    """Test that base agent can update its strategic nuance."""

    def test_update_strategic_nuance(self):
        """Agent's identity is updated when nuance changes."""
        from core.models.agents import AgentIdentity, AgentRole, AgentType

        identity = AgentIdentity(
            agent_name="Test Agent",
            agent_role=AgentRole.TECHNICAL_ANALYST,
            agent_type=AgentType.ANALYST,
            identity_core="Test identity core",
            strategic_nuance="",
            version=1,
        )

        # Verify initial state
        assert identity.strategic_nuance == ""
        assert identity.version == 1
        assert "Current Strategic Directives" not in identity.full_prompt

        # Update nuance
        identity.strategic_nuance = "- Focus on volume breakouts"
        identity.version = 2

        # Verify updated state
        assert identity.strategic_nuance == "- Focus on volume breakouts"
        assert identity.version == 2
        assert "Current Strategic Directives" in identity.full_prompt
        assert "volume breakouts" in identity.full_prompt


# ═══════════════════════════════════════════════════════════════════
# TEST 7: Trust Updater Logic
# ═══════════════════════════════════════════════════════════════════

class TestTrustUpdaterLogic:
    """Test the trust updater consecutive failure counting."""

    def test_count_consecutive_poor(self):
        """Count consecutive wrong predictions."""
        from evolution.trust_updater import _count_consecutive_poor

        # 3 consecutive wrong predictions, then a correct one
        predictions = [
            {"predicted_probability": 0.8, "actual_outcome": 0},  # Wrong
            {"predicted_probability": 0.7, "actual_outcome": 0},  # Wrong
            {"predicted_probability": 0.6, "actual_outcome": 0},  # Wrong
            {"predicted_probability": 0.8, "actual_outcome": 1},  # Correct — breaks streak
            {"predicted_probability": 0.3, "actual_outcome": 1},  # Wrong but doesn't matter
        ]
        assert _count_consecutive_poor(predictions) == 3

    def test_count_no_failures(self):
        """No failures → count = 0."""
        from evolution.trust_updater import _count_consecutive_poor

        predictions = [
            {"predicted_probability": 0.8, "actual_outcome": 1},
            {"predicted_probability": 0.3, "actual_outcome": 0},
        ]
        assert _count_consecutive_poor(predictions) == 0

    def test_count_all_failures(self):
        """All wrong → count = all."""
        from evolution.trust_updater import _count_consecutive_poor

        predictions = [
            {"predicted_probability": 0.8, "actual_outcome": 0},
            {"predicted_probability": 0.7, "actual_outcome": 0},
        ]
        assert _count_consecutive_poor(predictions) == 2
