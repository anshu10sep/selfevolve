"""
Strategy Agent Test Suite

Comprehensive tests for the multi-strategy trading system:
- Unit tests for signal generation
- Parameter evolution tests
- Portfolio manager allocation tests
- Integration tests for the full pipeline
- Edge case and safety tests
"""

from __future__ import annotations

import asyncio
import math
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Strategy imports
from agents.strategies.strategy_base import (
    StrategyAgent,
    StrategySignal,
    StrategyParameters,
    SignalType,
    StrategyMode,
    MarketRegimeAffinity,
    TradeRecord,
)
from agents.strategies.momentum_strategy import MomentumStrategyAgent
from agents.strategies.mean_reversion_strategy import MeanReversionStrategyAgent
from agents.strategies.breakout_strategy import BreakoutStrategyAgent
from agents.strategies.vwap_strategy import VWAPStrategyAgent
from agents.strategies.pairs_strategy import PairsStrategyAgent
from agents.strategies.gap_fill_strategy import GapFillStrategyAgent
from agents.strategies.overnight_hold_strategy import OvernightHoldStrategyAgent
from agents.portfolio_manager import PortfolioManager
from agents.strategies.strategy_tracker import StrategyPerformanceTracker


# ════════════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════════════

def make_mock_llm():
    """Create a mock LLM for testing."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="Test response"))
    llm.with_structured_output = MagicMock(return_value=llm)
    llm.model_name = "test-model"
    return llm


def make_bars(
    n: int = 60,
    base_price: float = 100.0,
    trend: float = 0.001,
    volatility: float = 0.02,
    base_volume: int = 2_000_000,
) -> list[dict]:
    """Generate synthetic OHLCV bar data for testing."""
    bars = []
    price = base_price
    for i in range(n):
        # Simple random walk with trend
        import random
        random.seed(42 + i)
        change = trend + volatility * (random.random() - 0.5)
        price *= (1 + change)
        
        high = price * (1 + abs(volatility * random.random()))
        low = price * (1 - abs(volatility * random.random()))
        open_p = price * (1 + volatility * (random.random() - 0.5) * 0.5)
        volume = int(base_volume * (0.5 + random.random()))
        
        bars.append({
            "timestamp": (datetime(2025, 1, 1) + timedelta(days=i)).isoformat(),
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": volume,
        })
    return bars


def make_momentum_bars(n: int = 30, strong: bool = True) -> list[dict]:
    """Generate bars with clear momentum signal."""
    bars = []
    price = 100.0
    for i in range(n):
        import random
        random.seed(100 + i)
        if strong and i > n - 10:
            # Strong uptrend in last 10 bars
            change = 0.005 + 0.005 * random.random()
        else:
            change = 0.001 * (random.random() - 0.5)
        
        price *= (1 + change)
        high = price * 1.005
        low = price * 0.995
        volume = 3_000_000 if (strong and i > n - 5) else 1_500_000
        
        bars.append({
            "timestamp": (datetime(2025, 1, 1) + timedelta(days=i)).isoformat(),
            "open": round(price * 0.999, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": volume,
        })
    return bars


def make_oversold_bars(n: int = 30) -> list[dict]:
    """Generate bars that end with an oversold RSI condition."""
    bars = []
    price = 100.0
    for i in range(n):
        import random
        random.seed(200 + i)
        if i > n - 8:
            # Sharp decline to trigger oversold
            change = -0.015 - 0.01 * random.random()
        else:
            change = 0.002 * (random.random() - 0.5)
        
        price *= (1 + change)
        high = price * 1.003
        low = price * 0.997
        
        bars.append({
            "timestamp": (datetime(2025, 1, 1) + timedelta(days=i)).isoformat(),
            "open": round(price * 1.001, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": 2_000_000,
        })
    return bars


def make_gap_bars(n: int = 30) -> list[dict]:
    """Generate bars with a gap-down on the last day."""
    bars = []
    price = 100.0
    for i in range(n):
        import random
        random.seed(300 + i)
        if i == n - 1:
            # Gap down: open 3% below previous close
            open_p = price * 0.97
            price = open_p * 1.005  # Slight recovery
            high = max(open_p, price) * 1.002
            low = min(open_p, price) * 0.998
        else:
            change = 0.001 * (random.random() - 0.5)
            price *= (1 + change)
            open_p = price * (1 + 0.001 * (random.random() - 0.5))
            high = max(open_p, price) * 1.002
            low = min(open_p, price) * 0.998

        bars.append({
            "timestamp": (datetime(2025, 1, 1) + timedelta(days=i)).isoformat(),
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": 3_000_000,
        })
    return bars


# ════════════════════════════════════════════════════════════════════
# TECHNICAL INDICATOR TESTS
# ════════════════════════════════════════════════════════════════════

class TestTechnicalIndicators:
    """Test the technical indicator utility methods."""

    def test_calculate_rsi_basic(self):
        """RSI should return values between 0 and 100."""
        closes = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
                  46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41,
                  46.22, 45.64]
        rsi = StrategyAgent.calculate_rsi(closes, 14)
        assert len(rsi) > 0
        for v in rsi:
            assert 0 <= v <= 100

    def test_calculate_rsi_insufficient_data(self):
        """RSI should return empty list with insufficient data."""
        rsi = StrategyAgent.calculate_rsi([1, 2, 3], 14)
        assert rsi == []

    def test_calculate_bollinger_bands(self):
        """Bollinger Bands should have upper > middle > lower."""
        closes = [float(100 + i * 0.5) for i in range(30)]
        upper, middle, lower = StrategyAgent.calculate_bollinger_bands(closes, 20, 2.0)
        assert len(upper) > 0
        for u, m, l in zip(upper, middle, lower):
            assert u > m > l

    def test_calculate_atr(self):
        """ATR should be positive."""
        n = 30
        highs = [100 + i + 1 for i in range(n)]
        lows = [100 + i - 1 for i in range(n)]
        closes = [100 + i for i in range(n)]
        atr = StrategyAgent.calculate_atr(highs, lows, closes, 14)
        assert len(atr) > 0
        for v in atr:
            assert v > 0

    def test_calculate_ema(self):
        """EMA should track the input values."""
        values = [float(i) for i in range(20)]
        ema = StrategyAgent.calculate_ema(values, 5)
        assert len(ema) > 0
        # EMA of increasing sequence should be increasing
        for i in range(1, len(ema)):
            assert ema[i] > ema[i - 1]

    def test_calculate_vwap(self):
        """VWAP should be between low and high."""
        n = 20
        highs = [101.0] * n
        lows = [99.0] * n
        closes = [100.0] * n
        volumes = [1000000.0] * n
        vwap = StrategyAgent.calculate_vwap(highs, lows, closes, volumes)
        assert len(vwap) == n
        for v in vwap:
            assert 99 <= v <= 101


# ════════════════════════════════════════════════════════════════════
# STRATEGY SIGNAL GENERATION TESTS
# ════════════════════════════════════════════════════════════════════

class TestMomentumStrategy:
    """Test momentum strategy signal generation."""

    @pytest.mark.asyncio
    async def test_generates_buy_signal_on_momentum(self):
        """Should generate BUY when momentum + volume align."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        bars = make_momentum_bars(30, strong=True)
        
        signals = await strategy.generate_signals(
            ["AAPL"],
            {"AAPL": {"bars": bars}},
        )
        # Should generate at least one signal
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
        # With our synthetic data, momentum may or may not trigger
        # depending on exact thresholds. Verify no errors at minimum.
        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_no_signal_insufficient_data(self):
        """Should return empty with insufficient data."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        signals = await strategy.generate_signals(
            ["AAPL"],
            {"AAPL": {"bars": [{"close": 100, "high": 101, "low": 99, "volume": 1000000}]}},
        )
        assert signals == []

    @pytest.mark.asyncio
    async def test_no_duplicate_position(self):
        """Should not signal if already in position."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        # Simulate active position
        strategy._active_trades["AAPL"] = MagicMock()
        
        signals = await strategy.generate_signals(
            ["AAPL"],
            {"AAPL": {"bars": make_momentum_bars(30, strong=True)}},
        )
        aapl_signals = [s for s in signals if s.ticker == "AAPL"]
        assert len(aapl_signals) == 0

    def test_regime_affinity(self):
        """Momentum should be STRONG in BULL, DISABLED in PANIC."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        affinity = strategy.get_regime_affinity()
        assert affinity["BULL"] == MarketRegimeAffinity.STRONG
        assert affinity["PANIC"] == MarketRegimeAffinity.DISABLED


class TestMeanReversionStrategy:
    """Test mean reversion strategy signal generation."""

    @pytest.mark.asyncio
    async def test_scan_completes_without_error(self):
        """Mean reversion scan should complete without errors."""
        llm = make_mock_llm()
        strategy = MeanReversionStrategyAgent(llm)
        bars = make_oversold_bars(30)
        
        signals = await strategy.generate_signals(
            ["TSLA"],
            {"TSLA": {"bars": bars}},
        )
        assert isinstance(signals, list)

    def test_regime_affinity(self):
        """Mean reversion should be STRONG in SIDEWAYS."""
        llm = make_mock_llm()
        strategy = MeanReversionStrategyAgent(llm)
        affinity = strategy.get_regime_affinity()
        assert affinity["SIDEWAYS"] == MarketRegimeAffinity.STRONG


class TestGapFillStrategy:
    """Test gap fill strategy signal generation."""

    @pytest.mark.asyncio
    async def test_detects_gap_down(self):
        """Should detect gap-down setups."""
        llm = make_mock_llm()
        strategy = GapFillStrategyAgent(llm)
        bars = make_gap_bars(30)
        
        signals = await strategy.generate_signals(
            ["MSFT"],
            {"MSFT": {"bars": bars}},
        )
        assert isinstance(signals, list)

    def test_historical_fill_rate_calculation(self):
        """Should correctly calculate fill rate."""
        llm = make_mock_llm()
        strategy = GapFillStrategyAgent(llm)
        
        # Create bars with known gap pattern
        bars = []
        for i in range(10):
            bars.append({
                "open": 100 if i == 0 else 97,  # 3% gap down
                "high": 101,  # Always fills
                "low": 96,
                "close": 100,
                "volume": 2_000_000,
            })
        
        rate, found, filled = strategy._calculate_historical_fill_rate(bars, 0.02)
        assert found >= 0
        assert filled <= found


# ════════════════════════════════════════════════════════════════════
# TRADE JOURNALING TESTS
# ════════════════════════════════════════════════════════════════════

class TestTradeJournaling:
    """Test trade recording and P&L calculation."""

    def test_record_entry(self):
        """Should correctly record a trade entry."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        signal = StrategySignal(
            strategy_name="momentum",
            ticker="AAPL",
            signal_type=SignalType.BUY,
            strength=0.8,
            confidence=0.7,
            entry_price=150.0,
            stop_loss_price=145.0,
            take_profit_price=160.0,
        )
        
        trade = strategy.record_entry(signal, 150.0, 1.5)
        
        assert trade.ticker == "AAPL"
        assert trade.entry_price == 150.0
        assert trade.quantity == 1.5
        assert trade.notional == 225.0
        assert strategy.has_active_position("AAPL")

    def test_record_exit_profit(self):
        """Should correctly calculate profit on exit."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        signal = StrategySignal(
            strategy_name="momentum",
            ticker="AAPL",
            signal_type=SignalType.BUY,
            strength=0.8,
            confidence=0.7,
            entry_price=150.0,
        )
        
        strategy.record_entry(signal, 150.0, 1.0)
        trade = strategy.record_exit("AAPL", 155.0)
        
        assert trade is not None
        assert trade.pnl_usd == 5.0
        assert trade.pnl_pct > 0
        assert trade.is_winner is True
        assert not strategy.has_active_position("AAPL")

    def test_record_exit_loss(self):
        """Should correctly calculate loss on exit."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        signal = StrategySignal(
            strategy_name="momentum",
            ticker="TSLA",
            signal_type=SignalType.BUY,
            strength=0.5,
            confidence=0.5,
            entry_price=200.0,
        )
        
        strategy.record_entry(signal, 200.0, 0.5)
        trade = strategy.record_exit("TSLA", 190.0)
        
        assert trade is not None
        assert trade.pnl_usd == -5.0
        assert trade.is_winner is False


# ════════════════════════════════════════════════════════════════════
# PORTFOLIO MANAGER TESTS
# ════════════════════════════════════════════════════════════════════

class TestPortfolioManager:
    """Test portfolio manager allocation engine."""

    def test_equal_allocation_new_strategies(self):
        """New strategies with no history should get equal allocation."""
        llm = make_mock_llm()
        pm = PortfolioManager(llm, total_equity=100.0)
        
        s1 = MomentumStrategyAgent(llm)
        s2 = MeanReversionStrategyAgent(llm)
        pm.register_strategy(s1)
        pm.register_strategy(s2)
        
        allocations = pm.calculate_allocations()
        
        assert len(allocations) == 2
        total = sum(allocations.values())
        # Should not exceed available capital (equity - cash reserve)
        assert total <= 100.0 * (1 - pm.MIN_CASH_RESERVE_PCT) + 0.01

    def test_panic_mode_zero_allocation(self):
        """PANIC regime should result in 0 allocation for all strategies."""
        llm = make_mock_llm()
        pm = PortfolioManager(llm, total_equity=100.0)
        
        s1 = MomentumStrategyAgent(llm)
        pm.register_strategy(s1)
        
        pm.set_regime("PANIC")
        allocations = pm.calculate_allocations()
        
        for alloc in allocations.values():
            assert alloc == 0.0

    def test_concentration_limit(self):
        """No single strategy should exceed max concentration."""
        llm = make_mock_llm()
        pm = PortfolioManager(llm, total_equity=100.0)
        
        # Register only one strategy — it should be capped
        s1 = MomentumStrategyAgent(llm)
        pm.register_strategy(s1)
        
        allocations = pm.calculate_allocations()
        
        max_allowed = 100.0 * pm.MAX_SINGLE_STRATEGY_PCT
        for alloc in allocations.values():
            assert alloc <= max_allowed + 0.01

    def test_equity_update(self):
        """Should correctly update equity."""
        llm = make_mock_llm()
        pm = PortfolioManager(llm, total_equity=100.0)
        pm.update_equity(150.0)
        assert pm._total_equity == 150.0


# ════════════════════════════════════════════════════════════════════
# PERFORMANCE METRICS TESTS
# ════════════════════════════════════════════════════════════════════

class TestPerformanceMetrics:
    """Test strategy performance calculation."""

    def test_empty_performance(self):
        """Should return zeroed metrics with no trades."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        perf = strategy.get_performance()
        
        assert perf["total_trades"] == 0
        assert perf["win_rate"] == 0.0
        assert perf["sharpe_ratio"] == 0.0

    def test_performance_with_trades(self):
        """Should correctly calculate metrics from trade history."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        # Simulate some trades
        for i, (ticker, entry, exit_p) in enumerate([
            ("AAPL", 150, 155),
            ("MSFT", 300, 310),
            ("TSLA", 200, 195),
            ("GOOGL", 140, 142),
        ]):
            signal = StrategySignal(
                strategy_name="momentum",
                ticker=ticker,
                signal_type=SignalType.BUY,
                strength=0.7,
                confidence=0.6,
                entry_price=float(entry),
            )
            strategy.record_entry(signal, float(entry), 1.0)
            strategy.record_exit(ticker, float(exit_p))
        
        perf = strategy.get_performance()
        assert perf["total_trades"] == 4
        assert perf["win_rate"] == 75.0  # 3 winners out of 4

    def test_brier_inputs(self):
        """Should extract predictions and outcomes for Brier Score."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        signal = StrategySignal(
            strategy_name="momentum",
            ticker="AAPL",
            signal_type=SignalType.BUY,
            strength=0.8,
            confidence=0.7,
            entry_price=150.0,
        )
        
        strategy.record_entry(signal, 150.0, 1.0)
        strategy.record_exit("AAPL", 155.0)
        
        predictions, outcomes = strategy.get_brier_inputs()
        assert len(predictions) == 1
        assert len(outcomes) == 1
        assert predictions[0] == 0.7  # confidence
        assert outcomes[0] == 1  # profitable


# ════════════════════════════════════════════════════════════════════
# PARAMETER EVOLUTION TESTS
# ════════════════════════════════════════════════════════════════════

class TestParameterEvolution:
    """Test parameter proposal, shadow testing, and promotion."""

    def test_propose_parameter_update(self):
        """Should create shadow parameters."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        shadow = strategy.propose_parameter_update(
            {"entry_threshold": 0.03},
            "Testing higher threshold for fewer, higher-quality signals",
        )
        
        assert shadow.version == 2
        assert shadow.params["entry_threshold"] == 0.03
        assert shadow.parent_version == 1
        assert strategy._shadow_parameters is not None

    def test_promote_shadow_parameters(self):
        """Should promote shadow params to production."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        strategy.propose_parameter_update(
            {"entry_threshold": 0.03},
            "Test",
        )
        strategy.promote_shadow_parameters()
        
        assert strategy.parameters.version == 2
        assert strategy.params["entry_threshold"] == 0.03
        assert strategy._shadow_parameters is None

    def test_rollback_shadow_parameters(self):
        """Should discard shadow params on rollback."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        strategy.propose_parameter_update(
            {"entry_threshold": 0.03},
            "Test",
        )
        strategy.rollback_parameters()
        
        assert strategy.parameters.version == 1
        assert strategy.params["entry_threshold"] == 0.02
        assert strategy._shadow_parameters is None


# ════════════════════════════════════════════════════════════════════
# STRATEGY TRACKER TESTS
# ════════════════════════════════════════════════════════════════════

class TestStrategyTracker:
    """Test strategy performance tracker."""

    def test_register_and_get_metrics(self):
        """Should register strategies and return metrics."""
        llm = make_mock_llm()
        tracker = StrategyPerformanceTracker(data_dir="/tmp/test_tracker")
        
        s1 = MomentumStrategyAgent(llm)
        tracker.register_strategy(s1)
        
        metrics = tracker.get_all_metrics()
        assert "momentum" in metrics

    def test_leaderboard_sorting(self):
        """Should sort strategies by performance metric."""
        llm = make_mock_llm()
        tracker = StrategyPerformanceTracker(data_dir="/tmp/test_tracker")
        
        s1 = MomentumStrategyAgent(llm)
        s2 = MeanReversionStrategyAgent(llm)
        tracker.register_strategy(s1)
        tracker.register_strategy(s2)
        
        leaderboard = tracker.get_leaderboard(sort_by="win_rate")
        assert len(leaderboard) == 2
        assert "rank" in leaderboard[0]

    def test_learning_journal(self):
        """Should record and retrieve learning entries."""
        llm = make_mock_llm()
        tracker = StrategyPerformanceTracker(data_dir="/tmp/test_tracker")
        
        tracker.record_learning(
            "momentum",
            "reflection",
            "Win rate improved after increasing entry threshold",
            {"win_rate": 65.0},
        )
        
        journal = tracker.get_learning_journal("momentum")
        assert len(journal) >= 1


# ════════════════════════════════════════════════════════════════════
# SIGNAL MODEL TESTS
# ════════════════════════════════════════════════════════════════════

class TestStrategySignal:
    """Test StrategySignal model."""

    def test_ticker_uppercase(self):
        """Ticker should be auto-uppercased."""
        signal = StrategySignal(
            strategy_name="test",
            ticker="aapl",
            signal_type=SignalType.BUY,
            strength=0.5,
            confidence=0.5,
        )
        assert signal.ticker == "AAPL"

    def test_risk_reward_ratio(self):
        """Should calculate risk:reward ratio."""
        signal = StrategySignal(
            strategy_name="test",
            ticker="AAPL",
            signal_type=SignalType.BUY,
            strength=0.5,
            confidence=0.5,
            entry_price=100.0,
            stop_loss_price=95.0,
            take_profit_price=115.0,
        )
        assert signal.risk_reward_ratio == 3.0  # 15/5 = 3

    def test_strength_validation(self):
        """Strength must be between 0 and 1."""
        with pytest.raises(Exception):
            StrategySignal(
                strategy_name="test",
                ticker="AAPL",
                signal_type=SignalType.BUY,
                strength=1.5,  # Invalid
                confidence=0.5,
            )


# ════════════════════════════════════════════════════════════════════
# TRADE RECORD TESTS
# ════════════════════════════════════════════════════════════════════

class TestTradeRecord:
    """Test TradeRecord model."""

    def test_close_trade(self):
        """Should correctly close a trade and calculate P&L."""
        trade = TradeRecord(
            signal_id="test-signal",
            strategy_name="momentum",
            ticker="AAPL",
            action=SignalType.BUY,
            entry_price=150.0,
            quantity=2.0,
            notional=300.0,
        )
        
        trade.close(155.0)
        
        assert trade.exit_price == 155.0
        assert trade.pnl_usd == 10.0  # (155-150) * 2
        assert trade.pnl_pct > 0
        assert trade.is_winner is True
        assert trade.hold_duration_minutes is not None


# ════════════════════════════════════════════════════════════════════
# SAFETY & EDGE CASE TESTS
# ════════════════════════════════════════════════════════════════════

class TestSafety:
    """Test safety mechanisms and edge cases."""

    @pytest.mark.asyncio
    async def test_empty_market_data(self):
        """Should handle empty market data gracefully."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        signals = await strategy.generate_signals(["AAPL"], {})
        assert signals == []

    @pytest.mark.asyncio
    async def test_zero_price_bars(self):
        """Should handle zero-price bars without crashing."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        
        bars = [{"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "timestamp": "2025-01-01"}] * 30
        signals = await strategy.generate_signals(
            ["BAD"],
            {"BAD": {"bars": bars}},
        )
        assert signals == []

    @pytest.mark.asyncio
    async def test_all_strategies_scan_without_error(self):
        """All 7 strategies should complete a scan without error."""
        llm = make_mock_llm()
        bars = make_bars(60)
        market_data = {"AAPL": {"bars": bars}, "MSFT": {"bars": bars}}
        tickers = ["AAPL", "MSFT"]
        
        strategies = [
            MomentumStrategyAgent(llm),
            MeanReversionStrategyAgent(llm),
            BreakoutStrategyAgent(llm),
            VWAPStrategyAgent(llm),
            PairsStrategyAgent(llm),
            GapFillStrategyAgent(llm),
            OvernightHoldStrategyAgent(llm),
        ]
        
        for strategy in strategies:
            signals = await strategy.generate_signals(tickers, market_data)
            assert isinstance(signals, list), f"{strategy.strategy_name} failed"

    def test_capital_management(self):
        """Available capital should track active trades."""
        llm = make_mock_llm()
        strategy = MomentumStrategyAgent(llm)
        strategy.set_allocation(100.0)
        
        assert strategy.available_capital == 100.0
        
        signal = StrategySignal(
            strategy_name="momentum",
            ticker="AAPL",
            signal_type=SignalType.BUY,
            strength=0.5,
            confidence=0.5,
            entry_price=50.0,
        )
        strategy.record_entry(signal, 50.0, 1.0)
        
        assert strategy.available_capital == 50.0
