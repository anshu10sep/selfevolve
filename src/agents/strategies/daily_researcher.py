"""
Daily Research Scheduler

Runs every morning pre-market. Orchestrates the full daily cycle:

1. Screen universe for today's candidates (via StockScreener + CryptoScreener)
2. Fetch market data for all candidates (equities via MarketDataClient, crypto via CryptoDataClient)
3. Fan out to all strategy agents for signal generation
4. Collect and aggregate signals
5. Submit aggregated signals to Portfolio Manager for allocation
6. Execute approved trades through the existing guardrail pipeline

Crypto strategies run on a separate 24/7 intraday loop with shorter
timeframes (5-min, 15-min, 1-hour bars).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.strategies.strategy_base import (
    StrategyAgent,
    StrategySignal,
    SignalType,
    StrategyMode,
)
from agents.portfolio_manager import PortfolioManager
from agents.strategies.strategy_tracker import StrategyPerformanceTracker
from agents.strategies.strategy_evolution import StrategyEvolutionEngine
from research.screener import StockScreener
from integrations.crypto_data import CryptoDataClient, CryptoScreener

logger = structlog.get_logger(component="daily_researcher")

# Crypto pairs use '/' separator (e.g., BTC/USD)
_CRYPTO_PAIR_PATTERN = "/"


class DailyResearcher:
    """
    Autonomous daily research scheduler.
    
    Orchestrates the complete morning research cycle:
    Screen → Data → Signals → Allocate → Execute
    
    Also runs the evening evolution cycle:
    Collect → Evaluate → Reflect → Evolve
    """

    def __init__(
        self,
        portfolio_manager: PortfolioManager,
        evolution_engine: StrategyEvolutionEngine,
        tracker: StrategyPerformanceTracker,
        screener: Optional[StockScreener] = None,
        market_data_client=None,
        crypto_data_client: Optional[CryptoDataClient] = None,
        crypto_screener: Optional[CryptoScreener] = None,
    ):
        self._pm = portfolio_manager
        self._evolution = evolution_engine
        self._tracker = tracker
        self._screener = screener or StockScreener()
        self._market_data = market_data_client
        self._crypto_data = crypto_data_client
        self._crypto_screener = crypto_screener
        self._strategies: dict[str, StrategyAgent] = {}
        self._crypto_strategies: dict[str, StrategyAgent] = {}
        self._last_morning_run: Optional[datetime] = None
        self._last_evening_run: Optional[datetime] = None
        self._last_crypto_run: Optional[datetime] = None
        self._daily_signals: list[StrategySignal] = []
        self._crypto_signals: list[StrategySignal] = []

    def register_strategy(self, strategy: StrategyAgent) -> None:
        """Register a strategy for daily research."""
        self._strategies[strategy.strategy_name] = strategy
        self._pm.register_strategy(strategy)
        self._evolution.register_strategy(strategy)

    def register_crypto_strategy(self, strategy: StrategyAgent) -> None:
        """Register a crypto-specific strategy for 24/7 intraday research."""
        self._crypto_strategies[strategy.strategy_name] = strategy
        self._pm.register_strategy(strategy)
        self._evolution.register_strategy(strategy)
        logger.info("crypto_strategy_registered", strategy=strategy.strategy_name)

    # ── Morning Cycle ──────────────────────────────────────────────

    async def run_morning_cycle(
        self,
        additional_tickers: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Run the full morning research cycle.
        
        Called pre-market (~8:30 AM ET).
        
        Returns:
            {
                "candidates": [...],
                "signals_by_strategy": {...},
                "total_signals": int,
                "allocations": {...},
                "approved_trades": [...],
            }
        """
        cycle_start = datetime.now(timezone.utc)
        logger.info("morning_cycle_started")
        result: dict[str, Any] = {"timestamp": cycle_start.isoformat()}

        # ── Step 1: Screen for candidates ──────────────────────────
        try:
            candidates = await self._screener.screen_candidates(max_results=20)
            candidate_tickers = [c["ticker"] for c in candidates]
        except Exception as e:
            logger.error("screening_failed", error=str(e))
            candidate_tickers = []
            candidates = []

        # Add any additional tickers (from watchlist, user request, etc.)
        if additional_tickers:
            for t in additional_tickers:
                if t.upper() not in candidate_tickers:
                    candidate_tickers.append(t.upper())

        # Add tickers from pairs strategy
        for strategy in self._strategies.values():
            if strategy.strategy_name == "pairs":
                pairs = strategy.get_param("pairs", [])
                for pair in pairs:
                    for t in pair:
                        if t not in candidate_tickers:
                            candidate_tickers.append(t)

        result["candidates"] = candidates
        result["tickers"] = candidate_tickers
        logger.info(
            "candidates_screened",
            count=len(candidate_tickers),
        )

        # ── Step 2: Fetch market data ──────────────────────────────
        market_data = await self._fetch_market_data(candidate_tickers)
        result["data_fetched"] = len(market_data)

        # ── Step 3: Fan out to all strategy agents ─────────────────
        signals_by_strategy: dict[str, list[dict]] = {}
        all_signals: list[StrategySignal] = []

        # Run all strategies in parallel
        tasks = []
        for name, strategy in self._strategies.items():
            tasks.append(
                self._run_strategy_scan(name, strategy, candidate_tickers, market_data)
            )

        strategy_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (name, _) in enumerate(self._strategies.items()):
            res = strategy_results[i]
            if isinstance(res, Exception):
                logger.error(
                    "strategy_scan_failed",
                    strategy=name,
                    error=str(res),
                )
                signals_by_strategy[name] = []
            else:
                signals_by_strategy[name] = [
                    {
                        "ticker": s.ticker,
                        "signal": s.signal_type.value,
                        "strength": s.strength,
                        "confidence": s.confidence,
                        "rationale": s.rationale,
                    }
                    for s in res
                ]
                all_signals.extend(res)

        result["signals_by_strategy"] = signals_by_strategy
        result["total_signals"] = len(all_signals)
        self._daily_signals = all_signals

        logger.info(
            "signals_collected",
            total=len(all_signals),
            by_strategy={k: len(v) for k, v in signals_by_strategy.items()},
        )

        # ── Step 4: Portfolio Manager allocation ───────────────────
        allocations = self._pm.calculate_allocations()
        result["allocations"] = allocations

        # ── Step 5: Determine approved trades ──────────────────────
        approved = self._prioritize_signals(all_signals)
        result["approved_trades"] = [
            {
                "strategy": s.strategy_name,
                "ticker": s.ticker,
                "signal": s.signal_type.value,
                "strength": s.strength,
                "confidence": s.confidence,
                "entry_price": s.entry_price,
                "stop_loss": s.stop_loss_price,
                "take_profit": s.take_profit_price,
            }
            for s in approved
        ]

        self._last_morning_run = cycle_start
        duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        result["duration_sec"] = round(duration, 1)

        logger.info(
            "morning_cycle_complete",
            candidates=len(candidate_tickers),
            total_signals=len(all_signals),
            approved_trades=len(approved),
            duration_sec=result["duration_sec"],
        )

        return result

    async def _run_strategy_scan(
        self,
        name: str,
        strategy: StrategyAgent,
        tickers: list[str],
        market_data: dict,
    ) -> list[StrategySignal]:
        """Run a single strategy's signal generation."""
        try:
            signals = await strategy.generate_signals(tickers, market_data)
            return signals
        except Exception as e:
            logger.error(
                "strategy_scan_error",
                strategy=name,
                error=str(e),
            )
            return []

    async def _fetch_market_data(
        self,
        tickers: list[str],
        timeframe: str = "1Day",
    ) -> dict[str, Any]:
        """
        Fetch market data for all candidate tickers.
        Routes crypto pairs through CryptoDataClient, equities through MarketDataClient.
        
        Returns dict keyed by ticker, each containing 'bars' list.
        """
        market_data = {}

        equity_tickers = [t for t in tickers if _CRYPTO_PAIR_PATTERN not in t]
        crypto_tickers = [t for t in tickers if _CRYPTO_PAIR_PATTERN in t]

        # Fetch equity data
        if equity_tickers and self._market_data:
            for ticker in equity_tickers:
                try:
                    bars = await self._market_data.get_bars(
                        ticker, timeframe=timeframe, limit=60
                    )
                    market_data[ticker] = {"bars": bars}
                except Exception as e:
                    logger.warning("equity_data_fetch_failed", ticker=ticker, error=str(e))
                    market_data[ticker] = {"bars": []}
        elif equity_tickers:
            for ticker in equity_tickers:
                market_data[ticker] = {"bars": []}

        # Fetch crypto data
        if crypto_tickers and self._crypto_data:
            for ticker in crypto_tickers:
                try:
                    bars = await self._crypto_data.get_bars(
                        ticker, timeframe=timeframe, limit=60
                    )
                    market_data[ticker] = {"bars": bars}
                except Exception as e:
                    logger.warning("crypto_data_fetch_failed", ticker=ticker, error=str(e))
                    market_data[ticker] = {"bars": []}
        elif crypto_tickers:
            for ticker in crypto_tickers:
                market_data[ticker] = {"bars": []}

        return market_data

    def _prioritize_signals(
        self,
        signals: list[StrategySignal],
    ) -> list[StrategySignal]:
        """
        Prioritize and filter signals for execution.
        
        Rules:
        1. Only one signal per ticker (highest composite score wins)
        2. BUY signals only (SELL signals handled separately)
        3. Minimum strength + confidence threshold
        4. Respect allocated capital per strategy
        """
        MIN_STRENGTH = 0.3
        MIN_CONFIDENCE = 0.3

        # Filter
        eligible = [
            s for s in signals
            if s.signal_type == SignalType.BUY
            and s.strength >= MIN_STRENGTH
            and s.confidence >= MIN_CONFIDENCE
        ]

        # Deduplicate by ticker (keep strongest signal)
        by_ticker: dict[str, StrategySignal] = {}
        for signal in eligible:
            composite = signal.strength * signal.confidence
            existing = by_ticker.get(signal.ticker)
            if existing is None:
                by_ticker[signal.ticker] = signal
            else:
                existing_composite = existing.strength * existing.confidence
                if composite > existing_composite:
                    by_ticker[signal.ticker] = signal

        # Sort by composite score descending
        approved = sorted(
            by_ticker.values(),
            key=lambda s: s.strength * s.confidence,
            reverse=True,
        )

        return approved

    # ── Evening Cycle ──────────────────────────────────────────────

    async def run_evening_cycle(self) -> dict[str, Any]:
        """
        Run the evening evolution cycle.
        
        Called post-market (~4:30 PM ET):
        1. Persist all trade journals
        2. Run evolution cycle for all strategies
        3. Generate daily performance report
        4. Update Portfolio Manager allocations
        """
        cycle_start = datetime.now(timezone.utc)
        logger.info("evening_cycle_started")

        result: dict[str, Any] = {"timestamp": cycle_start.isoformat()}

        # 1. Persist trades
        persist_results = self._tracker.persist_all()
        result["trades_persisted"] = persist_results

        # 2. Evolution cycle
        evolution_result = await self._evolution.run_evolution_cycle()
        result["evolution"] = evolution_result

        # 3. Daily report
        daily_report = self._tracker.generate_daily_report()
        result["daily_report"] = daily_report

        # 4. Recalculate allocations for tomorrow
        new_allocations = self._pm.calculate_allocations()
        result["tomorrow_allocations"] = new_allocations

        self._last_evening_run = cycle_start
        duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        result["duration_sec"] = round(duration, 1)

        logger.info(
            "evening_cycle_complete",
            duration_sec=result["duration_sec"],
        )

        return result

    # ── Crypto Intraday Cycle (24/7) ─────────────────────────────────

    async def run_crypto_intraday_cycle(
        self,
        timeframe: str = "5Min",
    ) -> dict[str, Any]:
        """
        Run a crypto intraday signal scan.
        
        This runs 24/7 independently of equity market hours.
        Called on a schedule (e.g., every 5 minutes) by the scheduler.
        
        Args:
            timeframe: Bar timeframe for crypto strategies (5Min, 15Min, 1Hour)
        """
        cycle_start = datetime.now(timezone.utc)
        logger.info("crypto_intraday_cycle_started", timeframe=timeframe)

        result: dict[str, Any] = {
            "timestamp": cycle_start.isoformat(),
            "timeframe": timeframe,
            "asset_class": "crypto",
        }

        if not self._crypto_strategies:
            result["status"] = "no_crypto_strategies_registered"
            return result

        # 1. Screen crypto universe
        crypto_tickers = []
        if self._crypto_screener:
            try:
                candidates = await self._crypto_screener.screen_candidates(max_results=10)
                crypto_tickers = [c["ticker"] for c in candidates]
                result["candidates"] = candidates
            except Exception as e:
                logger.error("crypto_screening_failed", error=str(e))

        # Add preferred pairs from crypto strategies
        for strategy in self._crypto_strategies.values():
            preferred = strategy.get_param("preferred_pairs", [])
            for pair in preferred:
                if pair not in crypto_tickers:
                    crypto_tickers.append(pair)

        result["tickers"] = crypto_tickers

        # 2. Fetch intraday crypto data
        market_data = await self._fetch_market_data(crypto_tickers, timeframe=timeframe)
        result["data_fetched"] = len(market_data)

        # 3. Run all crypto strategies
        signals_by_strategy: dict[str, list[dict]] = {}
        all_signals: list[StrategySignal] = []

        tasks = [
            self._run_strategy_scan(name, strategy, crypto_tickers, market_data)
            for name, strategy in self._crypto_strategies.items()
        ]
        strategy_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (name, _) in enumerate(self._crypto_strategies.items()):
            res = strategy_results[i]
            if isinstance(res, Exception):
                logger.error("crypto_strategy_scan_failed", strategy=name, error=str(res))
                signals_by_strategy[name] = []
            else:
                signals_by_strategy[name] = [
                    {"ticker": s.ticker, "signal": s.signal_type.value,
                     "strength": s.strength, "confidence": s.confidence}
                    for s in res
                ]
                all_signals.extend(res)

        result["signals_by_strategy"] = signals_by_strategy
        result["total_signals"] = len(all_signals)
        self._crypto_signals = all_signals

        # 4. Prioritize and approve
        approved = self._prioritize_signals(all_signals)
        result["approved_trades"] = [
            {"strategy": s.strategy_name, "ticker": s.ticker,
             "signal": s.signal_type.value, "strength": s.strength,
             "entry_price": s.entry_price, "stop_loss": s.stop_loss_price,
             "take_profit": s.take_profit_price}
            for s in approved
        ]

        self._last_crypto_run = cycle_start
        duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
        result["duration_sec"] = round(duration, 1)

        logger.info(
            "crypto_intraday_cycle_complete",
            tickers=len(crypto_tickers),
            signals=len(all_signals),
            approved=len(approved),
            duration=result["duration_sec"],
        )
        return result

    # ── Status ─────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the daily researcher."""
        return {
            "equity_strategies": list(self._strategies.keys()),
            "crypto_strategies": list(self._crypto_strategies.keys()),
            "total_strategies": len(self._strategies) + len(self._crypto_strategies),
            "last_morning_run": (
                self._last_morning_run.isoformat()
                if self._last_morning_run
                else None
            ),
            "last_evening_run": (
                self._last_evening_run.isoformat()
                if self._last_evening_run
                else None
            ),
            "last_crypto_run": (
                self._last_crypto_run.isoformat()
                if self._last_crypto_run
                else None
            ),
            "today_equity_signals": len(self._daily_signals),
            "today_crypto_signals": len(self._crypto_signals),
            "portfolio_state": self._pm.get_portfolio_state(),
            "evolution_status": self._evolution.get_evolution_status(),
        }
