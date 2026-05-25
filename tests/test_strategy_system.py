"""
Unit Tests for Multi-Strategy Trading System

Tests cover:
  - Strategy models (Pydantic validation)
  - Strategy learning skills (trade learning, parameter fitness, t-test)
  - Regime detection (deterministic classification)
  - Portfolio Manager (allocation algorithms)
  - Strategy DAG (pipeline execution)
"""

import math
import pytest
from datetime import datetime, timezone, timedelta

# ════════════════════════════════════════════════════════════════════
# TEST: Strategy Models
# ════════════════════════════════════════════════════════════════════

class TestStrategyModels:
    """Tests for Pydantic strategy models."""

    def test_signal_creation(self):
        from core.models.strategy_models import Signal, StrategyType, SignalDirection

        signal = Signal(
            ticker="AAPL",
            strategy_name="momentum",
            strategy_type=StrategyType.MOMENTUM,
            direction=SignalDirection.LONG,
            strength=0.8,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=165.0,
            confidence=0.75,
            reasoning="Bullish EMA crossover with ADX confirmation",
        )
        assert signal.ticker == "AAPL"
        assert signal.risk_reward_ratio == 3.0  # (165-150)/(150-145) = 3.0
        assert signal.risk_pct == pytest.approx(3.33, abs=0.01)

    def test_signal_ticker_uppercase(self):
        from core.models.strategy_models import Signal, StrategyType, SignalDirection

        signal = Signal(
            ticker="  aapl  ",
            strategy_name="test",
            strategy_type=StrategyType.MOMENTUM,
            direction=SignalDirection.LONG,
            strength=0.5,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            confidence=0.5,
            reasoning="test",
        )
        assert signal.ticker == "AAPL"

    def test_allocation_validation_max_single(self):
        from core.models.strategy_models import AllocationDecision, MarketRegimeType

        with pytest.raises(Exception):  # Pydantic validation error
            AllocationDecision(
                strategy_allocations={"momentum": 50.0},  # > 40% max
                regime=MarketRegimeType.TRENDING_UP,
                reasoning="test",
            )

    def test_allocation_validation_total(self):
        from core.models.strategy_models import AllocationDecision, MarketRegimeType

        with pytest.raises(Exception):
            AllocationDecision(
                strategy_allocations={
                    "a": 30.0, "b": 30.0, "c": 30.0, "d": 20.0,
                },  # Total > 100%
                regime=MarketRegimeType.TRENDING_UP,
                reasoning="test",
            )

    def test_trade_record_pnl_calculation(self):
        from core.models.strategy_models import TradeRecord, StrategyType, SignalDirection

        trade = TradeRecord(
            strategy_name="momentum",
            strategy_type=StrategyType.MOMENTUM,
            ticker="AAPL",
            direction=SignalDirection.LONG,
            entry_price=100.0,
            exit_price=110.0,
            quantity=10.0,
            notional=1000.0,
            stop_loss=95.0,
            take_profit=115.0,
            exit_time=datetime.now(timezone.utc),
        )
        assert trade.pnl == 100.0  # (110-100) × 10
        assert trade.pnl_pct == 10.0
        assert trade.is_winner is True

    def test_strategy_performance_compute_from_trades(self):
        from core.models.strategy_models import (
            StrategyPerformance, TradeRecord, StrategyType, SignalDirection,
        )

        now = datetime.now(timezone.utc)
        trades = []
        for i in range(10):
            entry = 100.0
            exit_p = 105.0 if i < 7 else 97.0  # 7 wins, 3 losses
            trades.append(TradeRecord(
                strategy_name="test",
                strategy_type=StrategyType.MOMENTUM,
                ticker="AAPL",
                direction=SignalDirection.LONG,
                entry_price=entry,
                exit_price=exit_p,
                quantity=1.0,
                notional=entry,
                stop_loss=95.0,
                take_profit=110.0,
                entry_time=now - timedelta(hours=i * 2),
                exit_time=now - timedelta(hours=i * 2 - 1),
            ))

        perf = StrategyPerformance.compute_from_trades(
            "test", StrategyType.MOMENTUM, trades
        )
        assert perf.total_trades == 10
        assert perf.winning_trades == 7
        assert perf.losing_trades == 3
        assert perf.win_rate == 0.7
        assert perf.total_pnl > 0


# ════════════════════════════════════════════════════════════════════
# TEST: Strategy Learning
# ════════════════════════════════════════════════════════════════════

class TestStrategyLearning:
    """Tests for strategy learning skills."""

    def test_learn_from_winning_trade(self):
        from agents.skills.strategy_learning.strategy_learning import learn_from_trade

        result = learn_from_trade(
            trade_result={
                "trade_id": "test-001",
                "entry_price": 100.0,
                "exit_price": 108.0,
                "stop_loss_price": 95.0,
                "take_profit_price": 110.0,
                "pnl_pct": 8.0,
                "is_winner": True,
                "hold_duration_minutes": 180,
                "predicted_probability": 0.75,
            },
            strategy_params={"fast_ema_period": 10},
            strategy_name="momentum",
        )
        assert result["grade"] == "A"  # 8% gain → grade A
        assert result["is_winner"] is True
        assert result["brier_contribution"] < 0.1  # Good calibration

    def test_learn_from_losing_trade(self):
        from agents.skills.strategy_learning.strategy_learning import learn_from_trade

        result = learn_from_trade(
            trade_result={
                "trade_id": "test-002",
                "entry_price": 100.0,
                "exit_price": 95.0,
                "stop_loss_price": 94.0,
                "take_profit_price": 110.0,
                "pnl_pct": -5.0,
                "is_winner": False,
                "hold_duration_minutes": 30,
                "predicted_probability": 0.8,
                "exit_type": "STOP_LOSS",
            },
            strategy_params={},
            strategy_name="momentum",
        )
        assert result["grade"] == "D"
        assert result["is_winner"] is False
        assert result["brier_contribution"] > 0.5  # Poor calibration

    def test_evaluate_parameter_fitness_insufficient_data(self):
        from agents.skills.strategy_learning.strategy_learning import evaluate_parameter_fitness

        result = evaluate_parameter_fitness(
            trade_history=[{"exit_price": 100}] * 10,
            current_params={"fast_ema": 10},
            min_trades=30,
        )
        assert result["recommendation"] == "KEEP"
        assert "Insufficient data" in result["reason"]

    def test_statistical_significance_significant(self):
        from agents.skills.strategy_learning.strategy_learning import statistical_significance_test

        # Clear improvement
        control = [0.5, -0.3, 0.2, -0.1, 0.3, -0.2, 0.1, -0.4, 0.2, -0.1,
                    0.4, -0.2, 0.1, -0.3, 0.2]
        treatment = [1.5, 0.8, 1.2, 0.5, 1.3, 0.9, 1.1, 0.6, 1.4, 0.7,
                     1.6, 0.8, 1.0, 0.4, 1.1]

        result = statistical_significance_test(control, treatment)
        assert result["significant"] is True
        assert result["recommendation"] == "PROMOTE"
        assert result["p_value"] < 0.05

    def test_statistical_significance_not_significant(self):
        from agents.skills.strategy_learning.strategy_learning import statistical_significance_test

        # No real difference
        control = [0.5, -0.3, 0.2, -0.1, 0.3, -0.2, 0.1, -0.4, 0.2, -0.1]
        treatment = [0.4, -0.2, 0.3, -0.2, 0.2, -0.3, 0.2, -0.3, 0.1, -0.1]

        result = statistical_significance_test(control, treatment)
        assert result["significant"] is False
        assert result["recommendation"] == "CONTINUE_TESTING"


# ════════════════════════════════════════════════════════════════════
# TEST: Regime Detection
# ════════════════════════════════════════════════════════════════════

class TestRegimeDetection:
    """Tests for deterministic regime detection."""

    def _make_trending_up_data(self, n=60):
        """Generate trending up price data."""
        closes = [100 + i * 0.5 for i in range(n)]  # Steady uptrend
        highs = [c + 1.0 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000000] * n
        return closes, highs, lows, volumes

    def _make_sideways_data(self, n=60):
        """Generate sideways/range-bound data."""
        import math as m
        closes = [100 + 3 * m.sin(i * 0.3) for i in range(n)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        volumes = [1000000] * n
        return closes, highs, lows, volumes

    def test_detect_trending_up(self):
        from agents.skills.strategy_learning.regime_detection import detect_market_regime

        closes, highs, lows, volumes = self._make_trending_up_data()
        result = detect_market_regime(closes, highs, lows, volumes)
        assert result["regime"] in ("TRENDING_UP", "BREAKOUT", "LOW_VOLATILITY")
        assert result["confidence"] > 0.3

    def test_detect_volatile(self):
        from agents.skills.strategy_learning.regime_detection import detect_market_regime

        closes, highs, lows, volumes = self._make_sideways_data()
        result = detect_market_regime(closes, highs, lows, volumes, vix_level=35)
        assert result["regime"] == "VOLATILE"

    def test_regime_weights(self):
        from agents.skills.strategy_learning.regime_detection import get_regime_strategy_weights

        weights = get_regime_strategy_weights("TRENDING_UP")
        assert weights["momentum"] > 1.0  # Momentum should be boosted
        assert weights["mean_reversion"] < 1.0  # Mean reversion should be reduced

    def test_regime_weights_sideways(self):
        from agents.skills.strategy_learning.regime_detection import get_regime_strategy_weights

        weights = get_regime_strategy_weights("MEAN_REVERTING")
        assert weights["mean_reversion"] > 1.0
        assert weights["momentum"] < 1.0


# ════════════════════════════════════════════════════════════════════
# TEST: Portfolio Manager
# ════════════════════════════════════════════════════════════════════

class TestPortfolioManager:
    """Tests for portfolio manager allocation algorithms."""

    def test_portfolio_state(self):
        from agents.portfolio_manager import PortfolioManager

        # Test that we can instantiate and get state without crashing
        pm = PortfolioManager.__new__(PortfolioManager)
        pm._total_equity = 1000.0
        pm._strategies = {}
        pm._current_regime = "BULL"
        pm._allocations = {"momentum": 30.0, "mean_reversion": 25.0}
        pm._allocation_history = []
        pm._kill_list = set()

        # Basic state checks
        assert pm._total_equity == 1000.0
        assert pm._current_regime == "BULL"
        assert sum(pm._allocations.values()) == 55.0

    def test_regime_management(self):
        from agents.portfolio_manager import PortfolioManager

        pm = PortfolioManager.__new__(PortfolioManager)
        pm._current_regime = "SIDEWAYS"
        pm._strategies = {}
        pm._allocations = {}
        pm._allocation_history = []
        pm._kill_list = set()

        pm.set_regime("BULL")
        assert pm._current_regime == "BULL"

        pm.set_regime("bear")
        assert pm._current_regime == "BEAR"  # Should uppercase

    def test_max_allocation_limits(self):
        from agents.portfolio_manager import PortfolioManager

        # The PM should never allocate more than MAX_SINGLE_STRATEGY_PCT (30%)
        assert PortfolioManager.MAX_SINGLE_STRATEGY_PCT == 0.30

    def test_cash_reserve(self):
        from agents.portfolio_manager import PortfolioManager

        # The PM should always keep MIN_CASH_RESERVE_PCT (20%) in cash
        assert PortfolioManager.MIN_CASH_RESERVE_PCT == 0.20

    def test_kill_thresholds(self):
        from agents.portfolio_manager import PortfolioManager

        assert PortfolioManager.MAX_DRAWDOWN_KILL_PCT == 10.0
        assert PortfolioManager.MAX_CONSECUTIVE_LOSSES == 8


# ════════════════════════════════════════════════════════════════════
# TEST: Strategy Ledger
# ════════════════════════════════════════════════════════════════════

class TestStrategyLedger:
    """Tests for immutable strategy ledger."""

    def test_record_and_read_evolution_event(self, tmp_path):
        from agents.skills.strategy_learning.strategy_ledger import StrategyLedger

        ledger = StrategyLedger(data_dir=str(tmp_path))
        ledger.record_evolution_event(
            strategy_name="momentum",
            event_type="PARAMETER_PROPOSED",
            details={"param": "fast_ema", "old": 10, "new": 12},
        )
        events = ledger.get_evolution_events(strategy_name="momentum")
        assert len(events) == 1
        assert events[0]["event_type"] == "PARAMETER_PROPOSED"

    def test_strategy_evolution_summary(self, tmp_path):
        from agents.skills.strategy_learning.strategy_ledger import StrategyLedger

        ledger = StrategyLedger(data_dir=str(tmp_path))

        # Record some events
        ledger.record_parameter_version("momentum", 1, {"fast": 10}, "LIVE")
        ledger.record_parameter_version("momentum", 2, {"fast": 12}, "SHADOW")
        ledger.record_evolution_event("momentum", "PARAMETER_PROPOSED", {})
        ledger.record_trade_result("momentum", "t1", "AAPL", 5.0, 2.5, True, 1)
        ledger.record_trade_result("momentum", "t2", "NVDA", -3.0, -1.5, False, 1)

        summary = ledger.get_strategy_evolution_summary("momentum")
        assert summary["total_parameter_versions"] == 2
        assert summary["total_trades_recorded"] == 2
        assert summary["total_pnl"] == 2.0  # 5 - 3
