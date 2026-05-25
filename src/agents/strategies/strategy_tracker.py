"""
Strategy Performance Tracker

Persistent storage and real-time metrics for each strategy agent.
Tracks trade journals, rolling metrics (7/30/90-day windows),
parameter change history, and learning decisions.

This module provides the data foundation for the self-evolution loop.
"""

from __future__ import annotations

import json
import os
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

from agents.strategies.strategy_base import (
    StrategyAgent,
    TradeRecord,
    StrategyParameters,
    StrategyMode,
)

logger = structlog.get_logger(component="strategy_tracker")

# Persistence directory
TRACKER_DATA_DIR = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
    "data", "strategy_tracker",
)


class StrategyPerformanceTracker:
    """
    Tracks and persists performance metrics for all strategy agents.
    
    Features:
    - Rolling metrics over 7, 30, and 90-day windows
    - Trade journal persistence to JSON (upgradeable to PostgreSQL)
    - Parameter change history with statistical test results
    - Learning journal for self-evolution decisions
    - Comparative leaderboard across all strategies
    """

    def __init__(self, data_dir: str = TRACKER_DATA_DIR):
        self._data_dir = data_dir
        os.makedirs(self._data_dir, exist_ok=True)
        self._strategies: dict[str, StrategyAgent] = {}
        self._learning_log: list[dict] = []

    def register_strategy(self, strategy: StrategyAgent) -> None:
        """Register a strategy agent for tracking."""
        self._strategies[strategy.strategy_name] = strategy
        # Ensure strategy data directory exists
        strategy_dir = os.path.join(self._data_dir, strategy.strategy_name)
        os.makedirs(strategy_dir, exist_ok=True)
        logger.info(
            "strategy_registered",
            strategy=strategy.strategy_name,
            mode=strategy.mode.value,
        )

    def unregister_strategy(self, strategy_name: str) -> None:
        """Remove a strategy from tracking."""
        self._strategies.pop(strategy_name, None)

    # ── Metrics Collection ─────────────────────────────────────────

    def get_all_metrics(self) -> dict[str, dict]:
        """Get performance metrics for all registered strategies."""
        return {
            name: strategy.get_performance()
            for name, strategy in self._strategies.items()
        }

    def get_rolling_metrics(
        self, strategy_name: str
    ) -> dict[str, dict[str, Any]]:
        """
        Get rolling performance metrics over multiple windows.
        
        Returns:
            {
                "7d": {...performance metrics...},
                "30d": {...performance metrics...},
                "90d": {...performance metrics...},
                "all_time": {...performance metrics...},
            }
        """
        strategy = self._strategies.get(strategy_name)
        if not strategy:
            return {}

        return {
            "7d": strategy.get_performance(window_days=7),
            "30d": strategy.get_performance(window_days=30),
            "90d": strategy.get_performance(window_days=90),
            "all_time": strategy.get_performance(),
        }

    def get_leaderboard(
        self,
        sort_by: str = "sharpe_ratio",
        window_days: Optional[int] = 30,
    ) -> list[dict[str, Any]]:
        """
        Rank all strategies by a performance metric.
        
        Args:
            sort_by: Metric to sort by ('sharpe_ratio', 'win_rate', 'total_pnl_usd', etc.)
            window_days: Time window for the metrics
            
        Returns:
            Sorted list of strategy performance dicts
        """
        metrics = []
        for name, strategy in self._strategies.items():
            perf = strategy.get_performance(window_days=window_days)
            perf["rank_metric"] = perf.get(sort_by, 0.0)
            metrics.append(perf)

        metrics.sort(key=lambda x: x["rank_metric"], reverse=True)

        for i, m in enumerate(metrics, 1):
            m["rank"] = i

        return metrics

    # ── Trade Journal Persistence ──────────────────────────────────

    def persist_trades(self, strategy_name: str) -> str:
        """
        Persist a strategy's trade journal to disk.
        
        Returns:
            Path to the saved file
        """
        strategy = self._strategies.get(strategy_name)
        if not strategy:
            raise ValueError(f"Strategy '{strategy_name}' not registered")

        journal = strategy._trade_journal
        strategy_dir = os.path.join(self._data_dir, strategy_name)
        os.makedirs(strategy_dir, exist_ok=True)
        
        filepath = os.path.join(strategy_dir, "trade_journal.jsonl")
        
        with open(filepath, "w") as f:
            for trade in journal:
                record = {
                    "trade_id": trade.trade_id,
                    "signal_id": trade.signal_id,
                    "strategy_name": trade.strategy_name,
                    "strategy_version": trade.strategy_version,
                    "ticker": trade.ticker,
                    "action": trade.action.value,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "quantity": trade.quantity,
                    "notional": trade.notional,
                    "stop_loss_price": trade.stop_loss_price,
                    "take_profit_price": trade.take_profit_price,
                    "pnl_usd": trade.pnl_usd,
                    "pnl_pct": trade.pnl_pct,
                    "is_winner": trade.is_winner,
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                    "hold_duration_minutes": trade.hold_duration_minutes,
                    "predicted_probability": trade.predicted_probability,
                    "mode": trade.mode.value,
                }
                f.write(json.dumps(record) + "\n")

        logger.info(
            "trades_persisted",
            strategy=strategy_name,
            trade_count=len(journal),
            filepath=filepath,
        )
        return filepath

    def persist_all(self) -> dict[str, str]:
        """Persist trade journals for all registered strategies."""
        results = {}
        for name in self._strategies:
            try:
                results[name] = self.persist_trades(name)
            except Exception as e:
                logger.error("persist_failed", strategy=name, error=str(e))
                results[name] = f"ERROR: {e}"
        return results

    def load_trades(self, strategy_name: str) -> list[dict]:
        """Load persisted trade journal for a strategy."""
        filepath = os.path.join(
            self._data_dir, strategy_name, "trade_journal.jsonl"
        )
        if not os.path.exists(filepath):
            return []

        trades = []
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
        return trades

    # ── Parameter History ──────────────────────────────────────────

    def record_parameter_change(
        self,
        strategy_name: str,
        old_params: StrategyParameters,
        new_params: StrategyParameters,
        test_result: dict[str, Any],
    ) -> None:
        """
        Record a parameter change with the statistical test that triggered it.
        """
        strategy_dir = os.path.join(self._data_dir, strategy_name)
        os.makedirs(strategy_dir, exist_ok=True)
        
        filepath = os.path.join(strategy_dir, "parameter_history.jsonl")
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "old_version": old_params.version,
            "new_version": new_params.version,
            "old_params": old_params.params,
            "new_params": new_params.params,
            "change_description": new_params.change_description,
            "test_result": test_result,
        }
        
        with open(filepath, "a") as f:
            f.write(json.dumps(record) + "\n")

        logger.info(
            "parameter_change_recorded",
            strategy=strategy_name,
            old_version=old_params.version,
            new_version=new_params.version,
            p_value=test_result.get("p_value"),
        )

    def get_parameter_history(self, strategy_name: str) -> list[dict]:
        """Load parameter change history for a strategy."""
        filepath = os.path.join(
            self._data_dir, strategy_name, "parameter_history.jsonl"
        )
        if not os.path.exists(filepath):
            return []

        history = []
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    history.append(json.loads(line))
        return history

    # ── Learning Journal ───────────────────────────────────────────

    def record_learning(
        self,
        strategy_name: str,
        lesson_type: str,
        lesson: str,
        context: dict[str, Any],
    ) -> None:
        """
        Record a self-evolution learning decision.
        
        Args:
            strategy_name: Which strategy learned
            lesson_type: Type of lesson (e.g., "parameter_change", "no_change", "regime_observation")
            lesson: What was learned
            context: Supporting data (performance metrics, trade data)
        """
        strategy_dir = os.path.join(self._data_dir, strategy_name)
        os.makedirs(strategy_dir, exist_ok=True)
        
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": strategy_name,
            "lesson_type": lesson_type,
            "lesson": lesson,
            "context": context,
        }
        
        filepath = os.path.join(strategy_dir, "learning_journal.jsonl")
        with open(filepath, "a") as f:
            f.write(json.dumps(record) + "\n")

        self._learning_log.append(record)
        
        logger.info(
            "learning_recorded",
            strategy=strategy_name,
            lesson_type=lesson_type,
            lesson_preview=lesson[:80],
        )

    def get_learning_journal(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get learning journal entries, optionally filtered by strategy."""
        if strategy_name:
            filepath = os.path.join(
                self._data_dir, strategy_name, "learning_journal.jsonl"
            )
            if not os.path.exists(filepath):
                return []
            
            entries = []
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            return entries[-limit:]
        else:
            return self._learning_log[-limit:]

    # ── Portfolio Summary ──────────────────────────────────────────

    def get_portfolio_summary(self) -> dict[str, Any]:
        """
        Generate a comprehensive portfolio summary across all strategies.
        
        This is what the Portfolio Manager and Jarvis use for decision-making.
        """
        all_metrics = self.get_all_metrics()
        
        total_pnl = sum(m.get("total_pnl_usd", 0) for m in all_metrics.values())
        total_trades = sum(m.get("total_trades", 0) for m in all_metrics.values())
        active_trades = sum(m.get("active_trades", 0) for m in all_metrics.values())
        total_allocated = sum(m.get("allocated_capital", 0) for m in all_metrics.values())
        
        # Weighted average win rate
        weighted_wr_sum = 0.0
        total_trade_weight = 0
        for m in all_metrics.values():
            trades = m.get("total_trades", 0)
            wr = m.get("win_rate", 0)
            weighted_wr_sum += wr * trades
            total_trade_weight += trades
        
        avg_win_rate = (
            weighted_wr_sum / total_trade_weight
            if total_trade_weight > 0
            else 0.0
        )

        # Strategy count by mode
        mode_counts = {}
        for name, strategy in self._strategies.items():
            mode = strategy.mode.value
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_strategies": len(self._strategies),
            "mode_distribution": mode_counts,
            "total_allocated_capital": round(total_allocated, 2),
            "total_pnl_usd": round(total_pnl, 2),
            "total_trades": total_trades,
            "active_trades": active_trades,
            "portfolio_win_rate": round(avg_win_rate, 1),
            "strategy_metrics": all_metrics,
            "leaderboard": self.get_leaderboard(window_days=30),
        }

    # ── Daily Report ───────────────────────────────────────────────

    def generate_daily_report(self) -> str:
        """
        Generate a human-readable daily performance report.
        
        This is sent to Jarvis for the owner briefing.
        """
        summary = self.get_portfolio_summary()
        leaderboard = summary.get("leaderboard", [])
        
        lines = [
            "═" * 60,
            "  STRATEGY PORTFOLIO — DAILY REPORT",
            f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "═" * 60,
            "",
            f"  Total Strategies: {summary['total_strategies']}",
            f"  Total Allocated:  ${summary['total_allocated_capital']:.2f}",
            f"  Total P&L:        ${summary['total_pnl_usd']:+.2f}",
            f"  Total Trades:     {summary['total_trades']}",
            f"  Active Trades:    {summary['active_trades']}",
            f"  Portfolio WR:     {summary['portfolio_win_rate']:.1f}%",
            "",
            "  ── Strategy Leaderboard (30d) ──",
            "",
        ]

        for entry in leaderboard:
            emoji = "🟢" if entry.get("total_pnl_usd", 0) >= 0 else "🔴"
            lines.append(
                f"  {entry['rank']}. {emoji} {entry['strategy']:<20} "
                f"SR={entry.get('sharpe_ratio', 0):.2f}  "
                f"WR={entry.get('win_rate', 0):.1f}%  "
                f"P&L=${entry.get('total_pnl_usd', 0):+.2f}"
            )

        lines.extend([
            "",
            "═" * 60,
        ])

        return "\n".join(lines)


# Module-level singleton
performance_tracker = StrategyPerformanceTracker()
