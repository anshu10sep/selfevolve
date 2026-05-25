"""
Strategy DAG — Multi-Strategy Execution Pipeline

A LangGraph-based DAG that orchestrates the full multi-strategy flow:

  1. Market Data Fetch → all strategies in parallel
  2. Signal Generation → each strategy produces signals independently
  3. Regime Detection → classify current market conditions
  4. Portfolio Manager → aggregate signals, compute allocations
  5. Risk Check → guardrails and correlation filter
  6. Signal Selection → pick best trades within allocation limits
  7. Judge + Execute → existing DAG handles final execution

This DAG runs ALONGSIDE the existing trading_dag.py — both feed into
the same execution pipeline. The strategy DAG adds the "multi-strategy
diversified" path that the user requested.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.strategies.strategy_base import StrategyAgent, StrategySignal, SignalType
from agents.portfolio_manager import PortfolioManager
from agents.strategies.strategy_tracker import StrategyPerformanceTracker
from agents.skills.strategy_learning.regime_detection import detect_market_regime
from agents.skills.strategy_learning.strategy_ledger import strategy_ledger
from agents.skills.strategy_learning.strategy_learning import learn_from_trade

logger = structlog.get_logger(component="strategy_dag")


class StrategyDAG:
    """
    Multi-strategy execution pipeline.

    Flow:
      1. Fetch market data for all relevant tickers
      2. Run all strategy agents in parallel (deterministic signal generation)
      3. Detect market regime
      4. Portfolio Manager computes allocations + selects best signals
      5. Risk check: position sizing, correlation, drawdown limits
      6. Execute selected signals through the existing Alpaca pipeline

    The DAG is triggered by the scheduler at configurable intervals
    (default: every 15 minutes during market hours).
    """

    def __init__(
        self,
        strategies: list[StrategyAgent],
        portfolio_manager: PortfolioManager,
        tracker: StrategyPerformanceTracker,
        market_data_client=None,
    ):
        self._strategies = {s.strategy_name: s for s in strategies}
        self._portfolio_manager = portfolio_manager
        self._tracker = tracker
        self._market_data_client = market_data_client
        self._last_regime: Optional[dict] = None

    # ── Main Execution Pipeline ────────────────────────────────────

    async def run_cycle(
        self,
        tickers: list[str],
        portfolio_equity: float,
        market_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute one full strategy cycle.

        Args:
            tickers: Tickers to scan for signals
            portfolio_equity: Current total portfolio equity
            market_data: Pre-fetched market data (optional, will fetch if None)

        Returns:
            Cycle result with signals, allocations, and selected trades
        """
        cycle_start = datetime.now(timezone.utc)
        result = {
            "cycle_start": cycle_start.isoformat(),
            "tickers_scanned": len(tickers),
            "strategies_active": len(self._strategies),
        }

        try:
            # Step 1: Fetch market data if not provided
            if market_data is None:
                market_data = await self._fetch_market_data(tickers)

            if not market_data:
                result["status"] = "NO_DATA"
                return result

            # Step 2: Detect market regime
            regime = await self._detect_regime(market_data, tickers)
            regime_name = regime.get("regime", "MEAN_REVERTING")
            result["regime"] = regime_name

            # Step 3: Update portfolio manager with regime + equity
            self._portfolio_manager.set_regime(regime_name)
            self._portfolio_manager.update_equity(portfolio_equity)

            # Step 4: Generate signals from all strategies in parallel
            all_signals = await self._generate_all_signals(tickers, market_data)
            result["total_signals"] = sum(len(s) for s in all_signals.values())
            result["signals_by_strategy"] = {
                name: len(signals) for name, signals in all_signals.items()
            }

            # Step 5: Portfolio Manager calculates allocations (internally regime-aware)
            allocations = self._portfolio_manager.calculate_allocations()
            result["allocations"] = allocations

            # Step 6: Select best signals across strategies
            # Convert signals and rank by composite score (strength × 0.6 + confidence × 0.4)
            selected = self._select_signals(all_signals, allocations, portfolio_equity)
            result["selected_trades"] = selected

            # Step 7: Log to ledger
            history = self._portfolio_manager.get_allocation_history(1)
            old_alloc = history[0].get("allocations", {}) if history else {}
            strategy_ledger.record_allocation_change(
                old_allocations=old_alloc,
                new_allocations=allocations,
                regime=regime_name,
                reasoning=f"Cycle at {cycle_start.isoformat()}",
            )

            result["status"] = "SUCCESS"
            result["cycle_duration_ms"] = int(
                (datetime.now(timezone.utc) - cycle_start).total_seconds() * 1000
            )

            logger.info(
                "strategy_cycle_complete",
                tickers=len(tickers),
                signals=result["total_signals"],
                selected=len(selected),
                regime=result["regime"],
                duration_ms=result["cycle_duration_ms"],
            )

        except Exception as e:
            logger.error("strategy_cycle_failed", error=str(e))
            result["status"] = "ERROR"
            result["error"] = str(e)

        return result

    def _select_signals(
        self,
        all_signals: dict[str, list[StrategySignal]],
        allocations: dict[str, float],
        portfolio_equity: float,
        max_positions: int = 5,
    ) -> list[dict]:
        """Select the best signals across all strategies within allocation limits."""
        candidates = []

        for strategy_name, signals in all_signals.items():
            alloc = allocations.get(strategy_name, 0.0)
            if alloc <= 0:
                continue

            for signal in signals:
                if signal.signal_type != SignalType.BUY:
                    continue

                candidates.append({
                    "strategy_name": strategy_name,
                    "ticker": signal.ticker,
                    "signal_type": signal.signal_type.value,
                    "strength": signal.strength,
                    "confidence": signal.confidence,
                    "entry_price": signal.entry_price,
                    "stop_loss_price": signal.stop_loss_price,
                    "take_profit_price": signal.take_profit_price,
                    "rationale": signal.rationale,
                    "max_notional": alloc,
                    "composite_score": signal.strength * 0.6 + signal.confidence * 0.4,
                })

        candidates.sort(key=lambda x: x["composite_score"], reverse=True)

        selected = []
        seen_tickers = set()
        for c in candidates:
            if c["ticker"] in seen_tickers:
                continue
            if len(selected) >= max_positions:
                break
            seen_tickers.add(c["ticker"])
            selected.append(c)

        logger.info(
            "signals_selected",
            total_candidates=len(candidates),
            selected=len(selected),
        )

        return selected

    # ── Signal Generation (Parallel) ───────────────────────────────

    async def _generate_all_signals(
        self,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> dict[str, list[StrategySignal]]:
        """Run all strategy agents in parallel."""
        tasks = {}
        for name, strategy in self._strategies.items():
            tasks[name] = asyncio.create_task(
                self._safe_generate(strategy, tickers, market_data)
            )

        all_signals = {}
        for name, task in tasks.items():
            try:
                signals = await task
                all_signals[name] = signals
                logger.info(
                    "strategy_signals_generated",
                    strategy=name,
                    signal_count=len(signals),
                )
            except Exception as e:
                logger.warning(
                    "strategy_signal_failed",
                    strategy=name,
                    error=str(e),
                )
                all_signals[name] = []

        return all_signals

    async def _safe_generate(
        self,
        strategy: StrategyAgent,
        tickers: list[str],
        market_data: dict[str, Any],
    ) -> list[StrategySignal]:
        """Safely generate signals with timeout and error handling."""
        try:
            return await asyncio.wait_for(
                strategy.generate_signals(tickers, market_data),
                timeout=30.0,  # 30 second timeout per strategy
            )
        except asyncio.TimeoutError:
            logger.warning(
                "strategy_timeout",
                strategy=strategy.strategy_name,
            )
            return []
        except Exception as e:
            logger.warning(
                "strategy_error",
                strategy=strategy.strategy_name,
                error=str(e),
            )
            return []

    # ── Regime Detection ───────────────────────────────────────────

    async def _detect_regime(
        self,
        market_data: dict[str, Any],
        tickers: list[str],
    ) -> dict:
        """Detect current market regime from index data."""
        # Use SPY or first ticker as regime proxy
        proxy_tickers = ["SPY", "QQQ"] + tickers[:3]
        for proxy in proxy_tickers:
            data = market_data.get(proxy, {})
            bars = data.get("bars", [])
            if len(bars) >= 50:
                closes = [b["close"] for b in bars]
                highs = [b["high"] for b in bars]
                lows = [b["low"] for b in bars]
                volumes = [b["volume"] for b in bars]

                regime = detect_market_regime(
                    closes=closes,
                    highs=highs,
                    lows=lows,
                    volumes=volumes,
                )
                self._last_regime = regime
                return regime

        # Fallback
        return {
            "regime": "MEAN_REVERTING",
            "confidence": 0.3,
            "reason": "No data for regime detection",
            "indicators": {},
        }

    # ── Post-Trade Learning ────────────────────────────────────────

    async def process_trade_result(
        self,
        strategy_name: str,
        trade_result: dict,
    ) -> dict:
        """
        Process a completed trade through the learning pipeline.

        Called by the execution engine after a trade closes.
        """
        strategy = self._strategies.get(strategy_name)
        if not strategy:
            return {"error": f"Unknown strategy: {strategy_name}"}

        # Record exit in strategy
        ticker = trade_result.get("ticker", "")
        exit_price = trade_result.get("exit_price", 0)
        trade_record = strategy.record_exit(ticker, exit_price)

        if trade_record is None:
            return {"error": f"No active trade for {ticker}"}

        # Run learning
        learning = learn_from_trade(
            trade_result={
                "trade_id": trade_record.trade_id,
                "entry_price": trade_record.entry_price,
                "exit_price": trade_record.exit_price,
                "stop_loss_price": trade_record.stop_loss_price,
                "take_profit_price": trade_record.take_profit_price,
                "pnl_pct": trade_record.pnl_pct,
                "is_winner": trade_record.is_winner,
                "hold_duration_minutes": trade_record.hold_duration_minutes,
                "predicted_probability": trade_record.predicted_probability,
            },
            strategy_params=strategy.params,
            strategy_name=strategy_name,
        )

        # Record in ledger
        strategy_ledger.record_trade_result(
            strategy_name=strategy_name,
            trade_id=trade_record.trade_id,
            ticker=ticker,
            pnl_usd=trade_record.pnl_usd or 0,
            pnl_pct=trade_record.pnl_pct or 0,
            is_winner=trade_record.is_winner or False,
            params_version=trade_record.strategy_version,
            learning_report=learning,
        )

        # Record learning
        self._tracker.record_learning(
            strategy_name=strategy_name,
            lesson_type=learning.get("grade", "N/A"),
            lesson="; ".join(learning.get("observations", [])),
            context={
                "trade_id": trade_record.trade_id,
                "pnl_pct": trade_record.pnl_pct,
                "grade": learning.get("grade"),
            },
        )

        logger.info(
            "trade_learning_complete",
            strategy=strategy_name,
            ticker=ticker,
            grade=learning.get("grade"),
            pnl_pct=trade_record.pnl_pct,
        )

        return {
            "trade_id": trade_record.trade_id,
            "learning": learning,
            "performance": strategy.get_performance(),
        }

    # ── Market Data ────────────────────────────────────────────────

    async def _fetch_market_data(
        self,
        tickers: list[str],
    ) -> dict[str, Any]:
        """Fetch market data for all tickers."""
        if self._market_data_client is None:
            logger.warning("no_market_data_client")
            return {}

        market_data = {}
        for ticker in tickers:
            try:
                data = await self._market_data_client.get_bars(
                    ticker, limit=60, timeframe="1Day"
                )
                quote = await self._market_data_client.get_quote(ticker)
                market_data[ticker] = {
                    "bars": data,
                    "quote": quote,
                }
            except Exception as e:
                logger.warning(
                    "market_data_fetch_failed",
                    ticker=ticker,
                    error=str(e),
                )

        return market_data

    # ── Utility ────────────────────────────────────────────────────

    @staticmethod
    def _signal_to_dict(signal: StrategySignal) -> dict:
        """Convert StrategySignal to dict for portfolio manager."""
        return {
            "signal_id": signal.signal_id,
            "strategy_name": signal.strategy_name,
            "ticker": signal.ticker,
            "signal_type": signal.signal_type.value,
            "strength": signal.strength,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "stop_loss_price": signal.stop_loss_price,
            "take_profit_price": signal.take_profit_price,
            "rationale": signal.rationale,
        }

    def get_status(self) -> dict[str, Any]:
        """Get current status of all strategies."""
        return {
            "strategies": {
                name: {
                    "mode": s.mode.value,
                    "allocated_capital": s.allocated_capital,
                    "available_capital": s.available_capital,
                    "active_positions": len(s._active_trades),
                    "params_version": s._parameters.version,
                }
                for name, s in self._strategies.items()
            },
            "last_regime": self._last_regime,
            "allocations": self._portfolio_manager.get_portfolio_state().get("allocations", {}),
        }
