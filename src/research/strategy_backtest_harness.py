"""
Multi-Strategy Backtesting Harness

Runs all 7 strategies simultaneously on historical data, simulates
the Portfolio Manager's allocation decisions, and calculates the
combined portfolio performance.

Usage:
    python -m research.strategy_backtest_harness --tickers AAPL,MSFT,GOOGL --days 180

Output:
    - Per-strategy performance metrics (Sharpe, win rate, drawdown)
    - Combined portfolio performance
    - Comparison vs SPY buy-and-hold benchmark
    - Allocation evolution over time
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

from agents.strategies.strategy_base import (
    StrategyAgent,
    StrategySignal,
    StrategyParameters,
    SignalType,
    StrategyMode,
    TradeRecord,
)

logger = structlog.get_logger(component="backtest_harness")


class BacktestResult:
    """Results from a single strategy backtest."""

    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.trades: list[dict] = []
        self.equity_curve: list[float] = []
        self.daily_returns: list[float] = []

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get("pnl_pct", 0) > 0)
        return round(wins / len(self.trades) * 100, 1)

    @property
    def total_return(self) -> float:
        if not self.trades:
            return 0.0
        return round(sum(t.get("pnl_pct", 0) for t in self.trades), 2)

    @property
    def sharpe_ratio(self) -> float:
        if len(self.daily_returns) < 2:
            return 0.0
        avg = sum(self.daily_returns) / len(self.daily_returns)
        std = math.sqrt(
            sum((r - avg) ** 2 for r in self.daily_returns) / (len(self.daily_returns) - 1)
        )
        if std == 0:
            return 0.0
        return round((avg / std) * math.sqrt(252), 2)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return round(max_dd, 2)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t["pnl_pct"] for t in self.trades if t.get("pnl_pct", 0) > 0)
        gross_loss = abs(sum(t["pnl_pct"] for t in self.trades if t.get("pnl_pct", 0) < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy_name,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "profit_factor": self.profit_factor,
        }


class StrategyBacktestHarness:
    """
    Multi-strategy backtesting harness.
    
    Simulates the full system:
    1. Daily screening and signal generation
    2. Portfolio Manager allocation
    3. Trade execution with slippage model
    4. Performance tracking and evolution
    """

    def __init__(
        self,
        initial_capital: float = 100.0,
        cash_reserve_pct: float = 0.20,
        max_position_pct: float = 0.30,
        slippage_bps: float = 5.0,
    ):
        self.initial_capital = initial_capital
        self.cash_reserve_pct = cash_reserve_pct
        self.max_position_pct = max_position_pct
        self.slippage_bps = slippage_bps

    async def run_backtest(
        self,
        strategies: list[StrategyAgent],
        historical_data: dict[str, list[dict]],
        start_day: int = 30,
    ) -> dict[str, Any]:
        """
        Run a multi-strategy backtest.
        
        Args:
            strategies: List of strategy agents to backtest
            historical_data: Dict of ticker -> list of OHLCV bars
            start_day: Day index to start trading (need lookback data)
            
        Returns:
            Comprehensive backtest results
        """
        # Determine the number of trading days
        max_bars = max(len(bars) for bars in historical_data.values())
        if max_bars < start_day + 5:
            return {"error": "Insufficient historical data"}

        # Initialize
        equity = self.initial_capital
        portfolio_equity_curve = [equity]
        portfolio_daily_returns = []
        strategy_results = {s.strategy_name: BacktestResult(s.strategy_name) for s in strategies}
        all_positions: dict[str, dict] = {}  # ticker -> position info

        # Allocate capital equally to start
        available = equity * (1 - self.cash_reserve_pct)
        per_strategy = available / len(strategies) if strategies else 0
        for s in strategies:
            s.set_allocation(per_strategy)

        logger.info(
            "backtest_started",
            strategies=len(strategies),
            capital=equity,
            days=max_bars - start_day,
        )

        # ── Day-by-Day Simulation ──────────────────────────────────
        for day in range(start_day, max_bars):
            day_pnl = 0.0

            # Build market data window for this day
            market_data = {}
            for ticker, bars in historical_data.items():
                if day < len(bars):
                    # Give strategy agents data up to (and including) current day
                    market_data[ticker] = {"bars": bars[: day + 1]}

            tickers = list(market_data.keys())

            # ── Check exits for active positions ───────────────────
            tickers_to_exit = []
            for ticker, pos in list(all_positions.items()):
                ticker_bars = historical_data.get(ticker, [])
                if day >= len(ticker_bars):
                    continue
                current_bar = ticker_bars[day]
                current_price = current_bar["close"]

                # Check stop loss
                if pos.get("stop_loss") and current_bar["low"] <= pos["stop_loss"]:
                    exit_price = pos["stop_loss"] * (1 - self.slippage_bps / 10000)
                    tickers_to_exit.append((ticker, exit_price, "stop_loss"))
                # Check take profit
                elif pos.get("take_profit") and current_bar["high"] >= pos["take_profit"]:
                    exit_price = pos["take_profit"] * (1 - self.slippage_bps / 10000)
                    tickers_to_exit.append((ticker, exit_price, "take_profit"))
                # Check max hold
                elif pos.get("max_hold_day") and day >= pos["max_hold_day"]:
                    exit_price = current_price * (1 - self.slippage_bps / 10000)
                    tickers_to_exit.append((ticker, exit_price, "max_hold"))

            for ticker, exit_price, reason in tickers_to_exit:
                pos = all_positions.pop(ticker)
                pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                pnl_pct = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
                day_pnl += pnl

                strategy_name = pos["strategy"]
                strategy_results[strategy_name].trades.append({
                    "ticker": ticker,
                    "entry_price": pos["entry_price"],
                    "exit_price": round(exit_price, 2),
                    "quantity": pos["quantity"],
                    "pnl_usd": round(pnl, 4),
                    "pnl_pct": round(pnl_pct, 4),
                    "entry_day": pos["entry_day"],
                    "exit_day": day,
                    "exit_reason": reason,
                })

                # Record in strategy agent
                for s in strategies:
                    if s.strategy_name == strategy_name:
                        s.record_exit(ticker, exit_price)

            # ── Generate new signals ───────────────────────────────
            for strategy in strategies:
                try:
                    signals = await strategy.generate_signals(tickers, market_data)
                    
                    for signal in signals:
                        if signal.signal_type != SignalType.BUY:
                            continue
                        if signal.ticker in all_positions:
                            continue

                        # Position sizing
                        alloc = strategy.available_capital
                        max_pos = equity * self.max_position_pct
                        position_size = min(alloc * 0.5, max_pos)  # Use 50% of allocation per trade
                        
                        if position_size < 1.0:
                            continue

                        entry_price = signal.entry_price or historical_data[signal.ticker][day]["close"]
                        slipped_entry = entry_price * (1 + self.slippage_bps / 10000)
                        quantity = position_size / slipped_entry

                        # Record position
                        all_positions[signal.ticker] = {
                            "strategy": strategy.strategy_name,
                            "entry_price": round(slipped_entry, 2),
                            "quantity": round(quantity, 6),
                            "stop_loss": signal.stop_loss_price,
                            "take_profit": signal.take_profit_price,
                            "entry_day": day,
                            "max_hold_day": day + strategy.get_param("hold_days", strategy.get_param("max_hold_days", 10)),
                        }

                        strategy.record_entry(signal, slipped_entry, quantity)

                except Exception as e:
                    logger.debug(
                        "backtest_strategy_error",
                        strategy=strategy.strategy_name,
                        day=day,
                        error=str(e),
                    )

            # ── Update equity ──────────────────────────────────────
            # Mark-to-market all positions
            mtm_pnl = 0.0
            for ticker, pos in all_positions.items():
                ticker_bars = historical_data.get(ticker, [])
                if day < len(ticker_bars):
                    current_price = ticker_bars[day]["close"]
                    mtm_pnl += (current_price - pos["entry_price"]) * pos["quantity"]

            equity = self.initial_capital + sum(
                t["pnl_usd"]
                for result in strategy_results.values()
                for t in result.trades
            ) + mtm_pnl

            portfolio_equity_curve.append(equity)
            daily_return = (
                (equity - portfolio_equity_curve[-2]) / portfolio_equity_curve[-2] * 100
                if len(portfolio_equity_curve) > 1 and portfolio_equity_curve[-2] > 0
                else 0
            )
            portfolio_daily_returns.append(daily_return)

            # Update strategy equity curves
            for name, result in strategy_results.items():
                result.equity_curve.append(equity)  # Simplified: track portfolio equity
                result.daily_returns.append(daily_return)

        # ── Final Summary ──────────────────────────────────────────
        # Close all remaining positions at last price
        for ticker, pos in list(all_positions.items()):
            ticker_bars = historical_data.get(ticker, [])
            if ticker_bars:
                final_price = ticker_bars[-1]["close"]
                pnl = (final_price - pos["entry_price"]) * pos["quantity"]
                pnl_pct = ((final_price - pos["entry_price"]) / pos["entry_price"]) * 100
                
                strategy_results[pos["strategy"]].trades.append({
                    "ticker": ticker,
                    "entry_price": pos["entry_price"],
                    "exit_price": final_price,
                    "pnl_usd": round(pnl, 4),
                    "pnl_pct": round(pnl_pct, 4),
                    "exit_reason": "end_of_backtest",
                })

        # Portfolio-level metrics
        total_pnl = equity - self.initial_capital
        total_return_pct = (total_pnl / self.initial_capital) * 100

        # Portfolio Sharpe
        if len(portfolio_daily_returns) > 1:
            avg_daily = sum(portfolio_daily_returns) / len(portfolio_daily_returns)
            std_daily = math.sqrt(
                sum((r - avg_daily) ** 2 for r in portfolio_daily_returns)
                / (len(portfolio_daily_returns) - 1)
            )
            portfolio_sharpe = (avg_daily / std_daily * math.sqrt(252)) if std_daily > 0 else 0
        else:
            portfolio_sharpe = 0

        # Portfolio max drawdown
        peak = portfolio_equity_curve[0]
        max_dd = 0.0
        for eq in portfolio_equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return {
            "portfolio": {
                "initial_capital": self.initial_capital,
                "final_equity": round(equity, 2),
                "total_pnl_usd": round(total_pnl, 2),
                "total_return_pct": round(total_return_pct, 2),
                "sharpe_ratio": round(portfolio_sharpe, 2),
                "max_drawdown_pct": round(max_dd, 2),
                "trading_days": max_bars - start_day,
                "total_trades": sum(r.total_trades for r in strategy_results.values()),
            },
            "strategies": {
                name: result.to_dict()
                for name, result in strategy_results.items()
            },
            "equity_curve": portfolio_equity_curve,
        }

    def format_report(self, results: dict[str, Any]) -> str:
        """Format backtest results as a human-readable report."""
        portfolio = results.get("portfolio", {})
        strategies = results.get("strategies", {})

        lines = [
            "═" * 70,
            "  MULTI-STRATEGY BACKTEST REPORT",
            "═" * 70,
            "",
            "  ── Portfolio Summary ──",
            f"  Initial Capital:  ${portfolio.get('initial_capital', 0):.2f}",
            f"  Final Equity:     ${portfolio.get('final_equity', 0):.2f}",
            f"  Total P&L:        ${portfolio.get('total_pnl_usd', 0):+.2f}",
            f"  Total Return:     {portfolio.get('total_return_pct', 0):+.2f}%",
            f"  Sharpe Ratio:     {portfolio.get('sharpe_ratio', 0):.2f}",
            f"  Max Drawdown:     {portfolio.get('max_drawdown_pct', 0):.2f}%",
            f"  Trading Days:     {portfolio.get('trading_days', 0)}",
            f"  Total Trades:     {portfolio.get('total_trades', 0)}",
            "",
            "  ── Strategy Breakdown ──",
            "",
            f"  {'Strategy':<25} {'Trades':>6} {'WR%':>6} {'Return%':>8} {'Sharpe':>7} {'MaxDD%':>7} {'PF':>6}",
            "  " + "─" * 65,
        ]

        for name, stats in sorted(strategies.items()):
            lines.append(
                f"  {name:<25} {stats.get('total_trades', 0):>6} "
                f"{stats.get('win_rate', 0):>5.1f}% "
                f"{stats.get('total_return', 0):>+7.2f}% "
                f"{stats.get('sharpe_ratio', 0):>6.2f} "
                f"{stats.get('max_drawdown', 0):>6.2f}% "
                f"{stats.get('profit_factor', 0):>5.2f}"
            )

        lines.extend(["", "═" * 70])
        return "\n".join(lines)


async def run_backtest_demo():
    """Demo: Run backtest with synthetic data."""
    from agents.strategies.momentum_strategy import MomentumStrategyAgent
    from agents.strategies.mean_reversion_strategy import MeanReversionStrategyAgent
    from agents.strategies.breakout_strategy import BreakoutStrategyAgent
    from agents.strategies.overnight_hold_strategy import OvernightHoldStrategyAgent
    from unittest.mock import MagicMock, AsyncMock

    # Mock LLM
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="OK"))
    llm.with_structured_output = MagicMock(return_value=llm)
    llm.model_name = "test"

    # Create strategies
    strategies = [
        MomentumStrategyAgent(llm, mode=StrategyMode.BACKTEST),
        MeanReversionStrategyAgent(llm, mode=StrategyMode.BACKTEST),
        BreakoutStrategyAgent(llm, mode=StrategyMode.BACKTEST),
        OvernightHoldStrategyAgent(llm, mode=StrategyMode.BACKTEST),
    ]

    # Generate synthetic data for 5 tickers
    import random
    historical_data = {}
    for ticker in ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]:
        bars = []
        price = random.uniform(80, 300)
        for day in range(180):
            random.seed(hash(ticker) + day)
            change = 0.001 + 0.02 * (random.random() - 0.5)
            price *= (1 + change)
            bars.append({
                "timestamp": (datetime(2025, 1, 1) + timedelta(days=day)).isoformat(),
                "open": round(price * (1 + 0.005 * (random.random() - 0.5)), 2),
                "high": round(price * (1 + 0.01 * random.random()), 2),
                "low": round(price * (1 - 0.01 * random.random()), 2),
                "close": round(price, 2),
                "volume": int(5_000_000 * (0.5 + random.random())),
            })
        historical_data[ticker] = bars

    # Run backtest
    harness = StrategyBacktestHarness(initial_capital=100.0)
    results = await harness.run_backtest(strategies, historical_data, start_day=30)

    # Print report
    report = harness.format_report(results)
    print(report)
    return results


if __name__ == "__main__":
    asyncio.run(run_backtest_demo())
