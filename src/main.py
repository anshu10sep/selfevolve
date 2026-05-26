"""
SelfEvolve — Main Entry Point

The 24/7 process that orchestrates the entire self-evolving trading system.
Never stops. Manages the trading schedule, agent lifecycle, evolution cycles,
and recovery from crashes.

Phases of operation:
  08:00 ET — Pre-Market Warm-up (research, briefing)
  09:30 ET — Market Open (trading DAG active)
  16:00 ET — Market Close (stop new trades)
  16:30 ET — Post-Market (evolution, reflexion, A/B testing)
  21:00 ET — Overnight (research, model improvement)
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Local imports
from config.settings import get_settings, Settings
from config.logging_config import setup_logging, get_logger
from config.constants import (
    MARKET_OPEN_ET,
    MARKET_CLOSE_ET,
    PRE_MARKET_WARMUP_ET,
    POST_MARKET_EVOLUTION_ET,
    HEARTBEAT_INTERVAL_SEC,
)
from persistence.database import initialize_database, health_check as db_health
from persistence.redis_client import get_redis_client, health_check as redis_health
from core.state_manager import StateManager
from core.event_bus import EventBus, EventChannels
from execution.circuit_breaker import CircuitBreaker, DeadManSwitch, HCFProtocol
from core.llm_utils import extract_text

logger: Optional[structlog.stdlib.BoundLogger] = None


class SelfEvolveSystem:
    """
    Main system orchestrator — the top-level process.
    
    Manages:
    - Infrastructure initialization (DB, Redis, Qdrant)
    - Agent spawning and lifecycle
    - Market schedule adherence
    - Trading DAG execution
    - Post-market evolution cycles
    - Crash recovery and self-healing
    """

    def __init__(self):
        self.settings: Settings = get_settings()
        self.state_manager: Optional[StateManager] = None
        self.event_bus: Optional[EventBus] = None
        self.circuit_breaker = CircuitBreaker()
        self.dead_man_switch: Optional[DeadManSwitch] = None
        self.hcf_protocol = HCFProtocol()
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self._running = False
        self._shutdown_event = asyncio.Event()
        # Phase 2: Event-driven components
        self.trade_publisher = None
        self.health_publisher = None
        self._market_daemon = None

    async def startup(self) -> None:
        """
        Initialize all system components.
        
        Order matters: DB → Redis → State → Agents → DAGs → Dashboard
        """
        global logger
        setup_logging(self.settings.log_level)
        logger = get_logger("main")

        await logger.ainfo(
            "selfevolve_starting",
            environment=self.settings.environment.value,
            initial_capital=self.settings.initial_capital,
            version="1.0.0",
        )

        # ── 1. Database ───────────────────────────────────────────
        try:
            await initialize_database()
            await logger.ainfo("database_initialized")
        except Exception as e:
            await logger.aerror("database_init_failed", error=str(e))
            # Continue anyway — some features work without DB

        # ── 2. Redis + State + Event Bus ─────────────────────────────
        # All wrapped together — if Redis is down, Jarvis runs in
        # dashboard-only mode until infra comes online.
        try:
            redis = await get_redis_client()
            await redis.ping()  # Verify connection immediately
            self.state_manager = StateManager(redis)
            self.event_bus = EventBus(redis)
            self.dead_man_switch = DeadManSwitch(redis)
            await logger.ainfo("redis_initialized")

            # ── 3. Initialize State ──────────────────────────────
            await self.state_manager.initialize_tranches()
            portfolio = await self.state_manager.get_portfolio_state()
            await logger.ainfo(
                "portfolio_initialized",
                equity=portfolio.total_equity,
                tranches=portfolio.available_tranches,
            )

            # ── 4. Start Event Bus + Subscribe All Handlers ────
            from core.event_handlers import (
                handle_market_event, handle_trade_event,
                handle_evolution_event, handle_health_event,
            )
            self.event_bus.subscribe(EventChannels.ALERT_EVENTS, self._handle_alert)
            self.event_bus.subscribe(EventChannels.MARKET_EVENTS, handle_market_event)
            self.event_bus.subscribe(EventChannels.TRADE_EVENTS, handle_trade_event)
            self.event_bus.subscribe(EventChannels.EVOLUTION_EVENTS, handle_evolution_event)
            self.event_bus.subscribe(EventChannels.HEALTH_EVENTS, handle_health_event)

            # ── 4b. Register Agent Event Handlers ─────────────────
            # These wire agents (Auditor, Journaling, QA, CTO, CSO)
            # to automatically react to trade/evolution/health events.
            try:
                from core.agent_event_handlers import register_agent_event_handlers
                register_agent_event_handlers(self.event_bus)
                await logger.ainfo("agent_event_handlers_registered")
            except Exception as e:
                await logger.awarning("agent_event_handlers_failed", error=str(e))

            # ── 4c. Initialize InsightPublisher ────────────────────
            # Inter-agent intelligence sharing via pub/sub.
            try:
                from core.insight_publisher import insight_publisher, handle_incoming_insight
                insight_publisher.set_event_bus(self.event_bus)
                self.event_bus.subscribe(
                    EventChannels.AGENT_INSIGHTS, handle_incoming_insight
                )
                await logger.ainfo("insight_publisher_wired")
            except Exception as e:
                await logger.awarning("insight_publisher_failed", error=str(e))

            await self.event_bus.start_listening()

            # ── 4c. Initialize VectorStore ─────────────────────────
            # Provides reflexion memory for agent self-evolution.
            try:
                from memory.vector_store import initialize_vector_store
                await initialize_vector_store()
                await logger.ainfo("vector_store_initialized")
            except Exception as e:
                await logger.awarning("vector_store_init_failed", error=str(e))

            # ── 5. Initialize Event Publishers ────────────────────
            from core.trade_event_publisher import TradeEventPublisher
            from core.health_publisher import HealthPublisher
            self.trade_publisher = TradeEventPublisher(self.event_bus)
            self.health_publisher = HealthPublisher(self.event_bus)

            # ── 6. Initialize Market Data Daemon ──────────────────
            from integrations.market_data_daemon import MarketDataDaemon
            self._market_daemon = MarketDataDaemon(self.event_bus, redis)
            await logger.ainfo("event_bus_fully_wired", channels=6)
        except Exception as e:
            await logger.awarning(
                "infra_not_available",
                error=str(e),
                message="Running in DASHBOARD-ONLY mode. "
                        "Start Redis/Postgres for full trading functionality.",
            )

        # ── 5. Start Telegram Bot ──────────────────────────────────
        try:
            from integrations.telegram_bot import start_bot
            self._telegram_app = await start_bot()
            if self._telegram_app:
                await logger.ainfo("telegram_bot_started")
        except Exception as e:
            self._telegram_app = None
            if logger:
                await logger.awarning("telegram_bot_failed", error=str(e))

        # ── 5b. Initialize Agent Instances & Registry ─────────────
        # Instantiate all agents with LLM and register them in the
        # agent_messaging registry so list_all_agents and delegation work.
        await self._initialize_agents()

        # ── 6. Start Scheduler ────────────────────────────────────
        self._setup_schedule()
        self.scheduler.start()
        await logger.ainfo("scheduler_started")

        # ── 7. Start Watchdog ─────────────────────────────────────
        # The Watchdog runs every 5 minutes to deduplicate bugs,
        # auto-resolve known issues, and monitor system health.
        try:
            from evolution.watchdog import watchdog
            self._watchdog_task = asyncio.create_task(
                watchdog.run_loop(interval_minutes=5)
            )
            await logger.ainfo("watchdog_started", interval="5min")
        except Exception as e:
            await logger.awarning("watchdog_start_failed", error=str(e))

        self._running = True
        await logger.ainfo("selfevolve_started", status="RUNNING")

    async def shutdown(self) -> None:
        """Graceful shutdown — preserve all state."""
        global logger
        if logger:
            await logger.ainfo("selfevolve_shutting_down")

        self._running = False

        # Stop Telegram bot
        if hasattr(self, '_telegram_app') and self._telegram_app:
            from integrations.telegram_bot import stop_bot
            await stop_bot()

        # Stop event bus
        if self.event_bus:
            await self.event_bus.stop_listening()

        # Stop scheduler
        if hasattr(self, "scheduler") and self.scheduler.running:
            self.scheduler.shutdown()

        # Flush state to PostgreSQL
        # (In production, this persists the full Redis state)

        if logger:
            await logger.ainfo("selfevolve_shutdown_complete")

    async def run(self) -> None:
        """
        Main execution loop — runs 24/7.
        
        The system phases through the trading day:
        1. Pre-market warm-up
        2. Market hours trading
        3. Post-market evolution
        4. Overnight research
        """
        global logger

        await self.startup()

        # Start Dashboard API in background
        api_task = asyncio.create_task(self._run_dashboard())

        # Start Overwatch Daemon (heartbeat)
        overwatch_task = asyncio.create_task(self._overwatch_loop())

        # Start Market Data Daemon (event-driven market monitoring)
        market_daemon_task = None
        if self._market_daemon:
            market_daemon_task = asyncio.create_task(self._market_daemon.run_loop())
            if logger:
                await logger.ainfo("market_data_daemon_launched")

        # Start Settlement Checker
        settlement_task = asyncio.create_task(self._settlement_check_loop())

        # Start Hot Reloader (watches for code changes)
        try:
            from evolution.hot_reloader import hot_reloader
            hot_reload_task = asyncio.create_task(hot_reloader.watch_loop())
        except Exception as e:
            hot_reload_task = None
            if logger:
                await logger.awarning("hot_reloader_init_failed", error=str(e))

        # Start Bug Worker (picks up bugs, generates code, creates PRs)
        try:
            from evolution.bug_worker import bug_worker
            bug_worker_task = asyncio.create_task(bug_worker.run_loop(interval_minutes=30))
        except Exception as e:
            bug_worker_task = None
            if logger:
                await logger.awarning("bug_worker_init_failed", error=str(e))

        # DB handles persistence — no auto-save loop needed
        auto_save_task = None

        # Start PR Review Loop (reviews unreviewed PRs periodically)
        try:
            from agents.skills.pr_reviewer.review_pipeline import review_pipeline
            pr_review_task = asyncio.create_task(review_pipeline.review_loop(interval_minutes=30))
        except Exception as e:
            pr_review_task = None
            if logger:
                await logger.awarning("pr_review_loop_init_failed", error=str(e))

        # Start Self-Evolution Loop (merge approved PRs → pull → restart)
        try:
            from evolution.self_evolution import evolution_engine
            evolution_task = asyncio.create_task(evolution_engine.evolution_loop(interval_minutes=10))
        except Exception as e:
            evolution_task = None
            if logger:
                await logger.awarning("evolution_loop_init_failed", error=str(e))

        # Start Bug Scanner (proactive log/import scanning → auto-files bugs)
        try:
            from evolution.bug_scanner import bug_scanner
            bug_scanner_task = asyncio.create_task(bug_scanner.run_loop(interval_minutes=30))
        except Exception as e:
            bug_scanner_task = None
            if logger:
                await logger.awarning("bug_scanner_init_failed", error=str(e))

        # Start Prediction Resolver (resolves unresolved predictions → feeds Brier scores)
        # This is the CRITICAL bridge between trading and evolution.
        # Without it, predictions never resolve and evolution has no signal.
        try:
            from evolution.prediction_resolver import prediction_resolver
            prediction_resolver_task = asyncio.create_task(
                prediction_resolver.run_loop(interval_minutes=5)
            )
            if logger:
                await logger.ainfo("prediction_resolver_started", interval="5min")
        except Exception as e:
            prediction_resolver_task = None
            if logger:
                await logger.awarning("prediction_resolver_init_failed", error=str(e))

        # Start TPM Tracker (watchdog: escalates stuck bugs, dispatches engineer)
        try:
            from evolution.tpm_tracker import tpm_tracker
            tpm_tracker_task = asyncio.create_task(tpm_tracker.run_loop(interval_minutes=30))
        except Exception as e:
            tpm_tracker_task = None
            if logger:
                await logger.awarning("tpm_tracker_init_failed", error=str(e))

        # Start Process Monitor (meta-watchdog: ensures pipeline is alive)
        try:
            from evolution.process_monitor import process_monitor
            process_monitor_task = asyncio.create_task(process_monitor.run_loop(interval_minutes=30))
        except Exception as e:
            process_monitor_task = None
            if logger:
                await logger.awarning("process_monitor_init_failed", error=str(e))

        try:
            while self._running:
                try:
                    # Check system health
                    self.circuit_breaker.check()
                    self.hcf_protocol.check()

                    # The schedule engine (APScheduler) handles phase transitions
                    # in the background.

                    await asyncio.sleep(60)

                except Exception as e:
                    self.circuit_breaker.record_exception(e)
                    if logger:
                        await logger.aerror(
                            "main_loop_error",
                            error=str(e),
                            exc_info=True,
                        )
                    # Self-healer: diagnose and attempt auto-fix
                    try:
                        from evolution.self_healer import healer
                        await healer.handle_exception(e, context="main_loop")
                    except Exception:
                        pass
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            pass
        finally:
            api_task.cancel()
            overwatch_task.cancel()
            settlement_task.cancel()
            if market_daemon_task:
                market_daemon_task.cancel()
            if hot_reload_task:
                hot_reload_task.cancel()
            if bug_worker_task:
                bug_worker_task.cancel()
            if auto_save_task:
                auto_save_task.cancel()
            if pr_review_task:
                pr_review_task.cancel()
            if evolution_task:
                evolution_task.cancel()
            if bug_scanner_task:
                bug_scanner_task.cancel()
            if prediction_resolver_task:
                prediction_resolver_task.cancel()
            if tpm_tracker_task:
                tpm_tracker_task.cancel()
            if process_monitor_task:
                process_monitor_task.cancel()
            await self.shutdown()

    async def _initialize_agents(self) -> None:
        """
        Initialize all agent instances and register them in the agent
        messaging registry.

        This populates _agent_registry so that:
        - list_all_agents() shows live agents
        - delegate_task_to_agent() can send work to sub-agents
        - The agent hierarchy is fully operational

        Agents are instantiated with LLMs from the centralized factory.
        """
        global logger
        self._agents = {}

        try:
            from core.llm_factory import get_premium_llm, get_efficient_llm
            from agents.skills.jarvis.agent_messaging import register_agent_instance

            premium_llm = get_premium_llm()
            efficient_llm = get_efficient_llm()

            # ── 1. Jarvis (CEO) — uses premium LLM ────────────────
            try:
                from agents.master_agent import Jarvis
                jarvis = Jarvis(llm=premium_llm)
                self._agents["jarvis"] = jarvis
                register_agent_instance("jarvis", jarvis)
                register_agent_instance("master", jarvis)
            except Exception as e:
                if logger: await logger.awarning("jarvis_init_failed", error=str(e))

            # ── 2. C-Suite (Executives) — use premium LLM ─────────
            csuite_agents = [
                ("cto", "agents.cto_agent", "CtoAgent"),
                ("cso", "agents.cso_agent", "CsoAgent"),
                ("cro", "agents.cro_agent", "CroAgent"),
            ]
            for key, module_path, class_name in csuite_agents:
                try:
                    import importlib
                    mod = importlib.import_module(module_path)
                    agent_cls = getattr(mod, class_name)
                    agent = agent_cls(llm=premium_llm)
                    self._agents[key] = agent
                    register_agent_instance(key, agent)
                    register_agent_instance(agent.name.lower(), agent)
                except Exception as e:
                    if logger: await logger.awarning(f"{key}_init_failed", error=str(e))

            # ── 3. Division Directors — use efficient LLM ──────────
            director_agents = [
                ("product", "agents.product_agent", "ProductAgent"),
                ("portfolio_manager", "agents.portfolio_manager", "PortfolioManager"),
                ("meta_review", "agents.meta_review_agent", "MetaReviewAgent"),
                ("qa", "agents.qa_agent", "QaAgent"),
            ]
            for key, module_path, class_name in director_agents:
                try:
                    import importlib
                    mod = importlib.import_module(module_path)
                    agent_cls = getattr(mod, class_name)
                    agent = agent_cls(llm=efficient_llm)
                    self._agents[key] = agent
                    register_agent_instance(key, agent)
                    register_agent_instance(agent.name.lower(), agent)
                except Exception as e:
                    if logger: await logger.awarning(f"{key}_init_failed", error=str(e))

            # ── 4. Specialists — use efficient LLM ─────────────────
            specialist_agents = [
                ("auditor", "agents.auditor_agent", "AuditorAgent"),
                ("journaling", "agents.journaling_agent", "JournalingAgent"),
                ("watchdog", "agents.watchdog_agent", "WatchdogAgent"),
                ("developer", "agents.developer_agent", "DeveloperAgent"),
                ("performance_analyst", "agents.performance_analyst_agent", "PerformanceAnalystAgent"),
                ("judge", "agents.judge_agent", "JudgeAgent"),
            ]
            for key, module_path, class_name in specialist_agents:
                try:
                    import importlib
                    mod = importlib.import_module(module_path)
                    agent_cls = getattr(mod, class_name)
                    agent = agent_cls(llm=efficient_llm)
                    self._agents[key] = agent
                    register_agent_instance(key, agent)
                    register_agent_instance(agent.name.lower(), agent)
                except Exception as e:
                    if logger: await logger.awarning(f"{key}_init_failed", error=str(e))

            # ── 5b. Strategy Agents — deterministic trading strategies ──
            # Each strategy agent has its own self-evolution loop via
            # StrategyEvolutionEngine (Brier scores, shadow testing, etc.)
            try:
                from agents.strategies.strategy_evolution import strategy_evolution_engine
                from agents.strategies.momentum_strategy import MomentumStrategy
                from agents.strategies.mean_reversion_strategy import MeanReversionStrategy
                from agents.strategies.breakout_strategy import BreakoutStrategy
                from agents.strategies.gap_fill_strategy import GapFillStrategy
                from agents.strategies.vwap_strategy import VwapStrategy
                from agents.strategies.overnight_hold_strategy import OvernightHoldStrategy
                from agents.strategies.pairs_strategy import PairsStrategy
                from agents.strategies.crypto_momentum_strategy import CryptoMomentumStrategy

                strategy_classes = [
                    MomentumStrategy,
                    MeanReversionStrategy,
                    BreakoutStrategy,
                    GapFillStrategy,
                    VwapStrategy,
                    OvernightHoldStrategy,
                    PairsStrategy,
                    CryptoMomentumStrategy,
                ]

                strategies_registered = 0
                for strategy_cls in strategy_classes:
                    try:
                        strategy = strategy_cls(llm=efficient_llm)
                        strategy_key = f"strategy_{strategy.strategy_name}"
                        self._agents[strategy_key] = strategy
                        register_agent_instance(strategy_key, strategy)
                        strategy_evolution_engine.register_strategy(strategy)
                        strategies_registered += 1
                    except Exception as strat_err:
                        if logger: await logger.awarning(
                            "strategy_init_failed",
                            strategy=strategy_cls.__name__,
                            error=str(strat_err),
                        )

                if strategies_registered > 0 and logger:
                    await logger.ainfo(
                        "strategy_agents_initialized",
                        count=strategies_registered,
                        strategies=list(strategy_evolution_engine._strategies.keys()),
                    )
            except Exception as e:
                if logger: await logger.awarning(
                    "strategy_framework_init_failed",
                    error=str(e),
                    message="Trading continues with LLM-based analyst agents only",
                )

            # ── 5c. Wire Jarvis to Event Bus (Gap #7 fix) ───────────
            if self.event_bus and "jarvis" in self._agents:
                try:
                    jarvis = self._agents["jarvis"]

                    async def _jarvis_trade_handler(event: dict):
                        """Jarvis reacts to trade events (orders filled, etc.)."""
                        event_type = event.get("event_type", "")
                        ticker = event.get("data", {}).get("ticker", "?")
                        if logger:
                            await logger.ainfo(
                                "jarvis_trade_event",
                                event_type=event_type, ticker=ticker,
                            )

                    async def _jarvis_health_handler(event: dict):
                        """Jarvis reacts to health degradation events."""
                        severity = event.get("data", {}).get("severity", "INFO")
                        if severity in ("HIGH", "CRITICAL") and "cto" in self._agents:
                            cto = self._agents["cto"]
                            try:
                                await cto.invoke(
                                    f"Health alert [{severity}]: {event.get('data', {}).get('message', 'Unknown issue')}. "
                                    "Assess system health and recommend actions."
                                )
                            except Exception:
                                pass

                    self.event_bus.subscribe(EventChannels.TRADE_EVENTS, _jarvis_trade_handler)
                    self.event_bus.subscribe(EventChannels.HEALTH_EVENTS, _jarvis_health_handler)

                    if logger:
                        await logger.ainfo("jarvis_event_bus_connected", channels=["TRADE_EVENTS", "HEALTH_EVENTS"])
                except Exception as e:
                    if logger: await logger.awarning("jarvis_event_bus_failed", error=str(e))

            total = len(self._agents)
            if logger:
                await logger.ainfo(
                    "agents_initialized",
                    total=total,
                    agents=list(self._agents.keys()),
                )

            # ── 6. Restore Evolved Prompts from DB ─────────────────
            # Without this, every restart resets agents to default prompts,
            # erasing all evolution progress.
            try:
                from persistence.db import get_active_prompt
                prompts_restored = 0
                for key, agent in self._agents.items():
                    if not hasattr(agent, "update_strategic_nuance"):
                        continue
                    role = getattr(agent, "role", None)
                    if role is None:
                        continue
                    role_str = role.value if hasattr(role, "value") else str(role)
                    active = get_active_prompt(role_str)
                    if active and active.get("prompt_text"):
                        agent.update_strategic_nuance(
                            active["prompt_text"],
                            active.get("version_number", 1),
                        )
                        prompts_restored += 1
                if prompts_restored > 0 and logger:
                    await logger.ainfo(
                        "evolved_prompts_restored",
                        count=prompts_restored,
                        message="Agents resumed with their evolved strategic nuances",
                    )
            except Exception as e:
                if logger:
                    await logger.awarning(
                        "prompt_restoration_failed",
                        error=str(e),
                        message="Agents continue with default prompts",
                    )

        except Exception as e:
            if logger:
                await logger.awarning(
                    "agent_initialization_failed",
                    error=str(e),
                    message="System continues without live agent instances",
                )

    def _setup_schedule(self) -> None:
        """Setup APScheduler with market hours logic.
        
        Trading Schedule (ET → UTC, ET = UTC-4 during EDT):
          08:00 ET (12:00 UTC) — Pre-Market: Screen stocks, build briefing
          09:30 ET (13:30 UTC) — Market Open: First trading scan
          10:30 ET (14:30 UTC) — Mid-Morning: Second scan (volatility settled)
          12:30 ET (16:30 UTC) — Midday: Midday opportunities
          14:30 ET (18:30 UTC) — Afternoon: Afternoon momentum scan
          16:00 ET (20:00 UTC) — Market Close: Journal, P&L report
          16:30 ET (20:30 UTC) — Post-Market: Evolution, reflection
        """
        self.scheduler.add_job(
            self._run_pre_market,
            CronTrigger(day_of_week='mon-fri', hour=12, minute=0),
            id='pre_market',
        )
        self.scheduler.add_job(
            self._run_market_open,
            CronTrigger(day_of_week='mon-fri', hour=13, minute=30),
            id='market_open',
        )
        # Intraday scans — 3 additional trading windows
        self.scheduler.add_job(
            self._run_intraday_scan,
            CronTrigger(day_of_week='mon-fri', hour=14, minute=30),
            id='mid_morning_scan',
        )
        self.scheduler.add_job(
            self._run_intraday_scan,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=30),
            id='midday_scan',
        )
        self.scheduler.add_job(
            self._run_intraday_scan,
            CronTrigger(day_of_week='mon-fri', hour=18, minute=30),
            id='afternoon_scan',
        )
        self.scheduler.add_job(
            self._run_market_close,
            CronTrigger(day_of_week='mon-fri', hour=20, minute=0),
            id='market_close',
        )
        self.scheduler.add_job(
            self._run_post_market_evolution,
            CronTrigger(day_of_week='mon-fri', hour=20, minute=30),
            id='post_market',
        )

        # ── CRYPTO 24/7 — scans every 30 mins for fast learning ──
        from apscheduler.triggers.interval import IntervalTrigger
        self.scheduler.add_job(
            self._run_crypto_scan,
            IntervalTrigger(minutes=30),
            id='crypto_scan_30m',
        )

        # ── CONTINUOUS EVOLUTION — every 6 hours, 7 days/week ──────
        self.scheduler.add_job(
            self._run_continuous_evolution,
            CronTrigger(hour='1,7,13,19', minute=0),
            id='continuous_evolution',
        )

        # ── B2 FIX: Position Review — every 30 min during market hours ──
        self.scheduler.add_job(
            self._run_position_review,
            CronTrigger(day_of_week='mon-fri', hour='14,15,16,17,18,19', minute='0,30'),
            id='position_review',
        )

        # ── B2 FIX: Crypto Stop Monitor — every 15 min, 24/7 ──
        self.scheduler.add_job(
            self._run_crypto_stop_monitor,
            IntervalTrigger(minutes=15),
            id='crypto_stop_monitor',
        )

    async def _run_pre_market(self) -> None:
        """Pre-market: Screen stocks, gather research, build briefing."""
        global logger
        if logger: await logger.ainfo("phase_started", phase="PRE_MARKET")

        try:
            from integrations.telegram_bot import send_alert
            from integrations.market_data import MarketDataClient
            from research.screener import StockScreener

            # Update dashboard phase
            from dashboard.api.main import system_state
            system_state["current_phase"] = "PRE_MARKET"

            await send_alert("☀️ *Pre-Market Phase Started*\nScanning for opportunities...")

            # Check if market will be open today — skip on holidays
            mdc = MarketDataClient()
            is_open = await mdc.is_market_open()
            if not is_open:
                await mdc.close()
                await send_alert("⏸ Market is closed today. Skipping pre-market scan.")
                return

            # Screen for candidates
            screener = StockScreener(mdc)
            candidates = await screener.screen_candidates(max_results=5)
            await mdc.close()

            # Store candidates for trading phase
            system_state["today_candidates"] = candidates

            if candidates:
                ticker_list = "\n".join(
                    f"  • `{c['ticker']}` — score: {c.get('momentum_score', 0):.2f} ({c.get('reason', '')})"
                    for c in candidates[:5]
                )
                await send_alert(
                    f"📋 *Pre-Market Briefing*\n\n"
                    f"Top {len(candidates)} candidates:\n{ticker_list}"
                )
            else:
                await send_alert("📋 *Pre-Market*: No strong candidates found today.")

            if logger: await logger.ainfo("pre_market_complete", candidates=len(candidates))

        except Exception as e:
            if logger: await logger.aerror("pre_market_failed", error=str(e))
            try:
                from integrations.telegram_bot import send_alert
                await send_alert(f"⚠️ Pre-market failed: `{str(e)[:100]}`")
            except Exception:
                pass

    async def _run_market_open(self) -> None:
        """Market open: Run multi-agent trading DAG on pre-screened candidates."""
        global logger
        if logger: await logger.ainfo("phase_started", phase="MARKET_OPEN")

        try:
            from integrations.telegram_bot import send_alert
            from dashboard.api.main import system_state
            system_state["current_phase"] = "MARKET_OPEN"

            # Check if market is actually open BEFORE announcing
            from integrations.market_data import MarketDataClient
            mdc = MarketDataClient()
            is_open = await mdc.is_market_open()
            await mdc.close()

            if not is_open:
                await send_alert("⏸ Market is closed today. Skipping trading.")
                return

            # Market is confirmed open — now announce
            await send_alert("🔔 *Market Open*\nTrading engine active.")

            # Get today's candidates from pre-market
            candidates = system_state.get("today_candidates", [])
            if not candidates:
                await send_alert("📭 No candidates to trade today.")
                return

            from broker.alpaca_client import AlpacaClient
            alpaca = AlpacaClient()

            # Compile the multi-agent trading DAG once for all candidates
            dag = None
            try:
                from orchestration.trading_dag import compile_trading_dag
                dag = compile_trading_dag()
                if logger: await logger.ainfo("trading_dag_compiled")
            except Exception as e:
                if logger: await logger.awarning("trading_dag_compile_failed", error=str(e))

            for candidate in candidates[:3]:  # Max 3 trades per day
                ticker = candidate["ticker"]
                try:
                    # Get fresh quote
                    from integrations.market_data import MarketDataClient as MDC2
                    mdc2 = MDC2()
                    quote = await mdc2.get_latest_quote(ticker)
                    current_price = quote.get("ask", candidate.get("price", 0))
                    await mdc2.close()

                    # ── Multi-Agent DAG Path ────────────────────────────
                    if dag is not None:
                        try:
                            initial_state = {
                                "ticker": ticker,
                                "regime": {},
                                "portfolio": system_state.get("portfolio", {}),
                                "fundamental_score": {},
                                "technical_score": {},
                                "sentiment_score": {},
                                "macro_score": {},
                                "aggregated_research": {},
                                "debate_state": {},
                                "execution_order": {},
                                "guardrail_result": "",
                                "hitl_action": "",
                                "trade_result": {},
                                "error": "",
                                "step": "",
                            }

                            result = await dag.ainvoke(initial_state)

                            execution_order = result.get("execution_order", {})
                            action = execution_order.get("action", "PASS")
                            _conf = execution_order.get("confidence_score", 0)
                            reasoning = execution_order.get("reasoning", "")
                            allocated_capital = execution_order.get("allocated_capital", 0)

                            # Build analysis summary from DAG state for logging/alerts
                            debate = result.get("debate_state", {})
                            aggregated = result.get("aggregated_research", {})
                            analysis = (
                                f"ACTION: {action}\n"
                                f"CONFIDENCE: {_conf}\n"
                                f"REASONING: {reasoning}\n"
                                f"Weighted Conviction: {aggregated.get('weighted_conviction', 0):.2f}\n"
                                f"Bull Score: {debate.get('bull_score', 'N/A')}\n"
                                f"Bear Score: {debate.get('bear_score', 'N/A')}\n"
                                f"Guardrail: {result.get('guardrail_result', 'N/A')}"
                            )

                            if logger:
                                await logger.ainfo(
                                    "dag_trade_analysis", ticker=ticker,
                                    action=action, confidence=_conf,
                                    conviction=aggregated.get("weighted_conviction", 0),
                                    tools_used=execution_order.get("tools_used", []),
                                )

                            if action == "BUY" and result.get("guardrail_result") != "REJECTED":
                                # Use allocated capital from Judge, or default $10K
                                tranche_size = allocated_capital if allocated_capital > 0 else 10000.0

                                # Parse SL/TP from reasoning or use defaults
                                sl_pct = 2.0
                                tp_pct = 5.0
                                for line in reasoning.split("\n") if reasoning else []:
                                    if "STOP_LOSS_PCT" in line.upper():
                                        try: sl_pct = float(line.split(":")[-1].strip().replace("%", ""))
                                        except: pass
                                    if "TAKE_PROFIT_PCT" in line.upper():
                                        try: tp_pct = float(line.split(":")[-1].strip().replace("%", ""))
                                        except: pass

                                from core.models.portfolio import TradeIntent, TradeSide
                                import uuid
                                intent = TradeIntent(
                                    ticker=ticker,
                                    side=TradeSide.BUY,
                                    notional=tranche_size,
                                    stop_loss_price=round(current_price * (1 - sl_pct / 100), 2),
                                    take_profit_price=round(current_price * (1 + tp_pct / 100), 2),
                                    client_order_id=str(uuid.uuid4()),
                                )

                                # ── HITL Gate ──
                                from core.hitl_gateway import hitl_gateway, should_trigger_hitl
                                _should_hitl, _hitl_reason = should_trigger_hitl(
                                    confidence=_conf,
                                    notional=tranche_size,
                                    equity=system_state.get("portfolio", {}).get("total_equity", 100),
                                    num_positions=len(system_state.get("portfolio", {}).get("positions", {})),
                                    drawdown_pct=system_state.get("portfolio", {}).get("drawdown_pct", 0),
                                )

                                if _should_hitl:
                                    hitl_req = await hitl_gateway.request_approval(
                                        ticker=ticker, side="BUY", notional=tranche_size,
                                        price=current_price,
                                        stop_loss=intent.stop_loss_price,
                                        take_profit=intent.take_profit_price,
                                        confidence=_conf,
                                        trigger_reason=_hitl_reason,
                                        analysis=analysis,
                                    )
                                    resolved = await hitl_gateway.wait_for_resolution(hitl_req.id)

                                    if resolved.status.value == "REJECTED":
                                        await send_alert(f"🚫 *HITL REJECTED:* {ticker}\n_{resolved.human_notes or 'No reason given'}_")
                                        continue
                                    elif resolved.status.value == "MODIFIED":
                                        if resolved.modified_sl:
                                            intent.stop_loss_price = resolved.modified_sl
                                            sl_pct = abs((current_price - resolved.modified_sl) / current_price * 100)
                                        if resolved.modified_tp:
                                            intent.take_profit_price = resolved.modified_tp
                                            tp_pct = abs((resolved.modified_tp - current_price) / current_price * 100)

                                order = await alpaca.submit_bracket_order(intent)
                                order_id = order.get("id", "?")
                                trade_id = intent.client_order_id

                                # ── Record per-agent predictions for Brier scoring ──
                                agent_predictions = {}
                                for role in ["fundamental", "technical", "sentiment", "macro"]:
                                    score_data = result.get(f"{role}_score", {})
                                    if score_data.get("score") is not None:
                                        # Normalize conviction (-1,1) to probability (0,1)
                                        prob = (float(score_data["score"]) + 1.0) / 2.0
                                        agent_predictions[f"{role.upper()}_ANALYST"] = prob

                                if self.trade_publisher:
                                    await self.trade_publisher.on_order_submitted(
                                        trade_id=trade_id, ticker=ticker,
                                        side="BUY", notional=tranche_size,
                                        analysis=analysis, confidence=_conf,
                                        current_price=current_price,
                                        agent_predictions=agent_predictions if agent_predictions else None,
                                    )

                                # ── Gap 4 Fix: Store trade context in VectorStore ──
                                # Enables cross-agent learning: "what did we do last
                                # time in a similar market situation?"
                                try:
                                    from memory.vector_store import get_vector_store
                                    vs = get_vector_store()
                                    debate = result.get("debate", {})
                                    await vs.store_trade_context(
                                        trade_id=trade_id,
                                        ticker=ticker,
                                        action="BUY",
                                        context_text=analysis[:1000] if analysis else "",
                                        analyst_scores={
                                            role: float(result.get(f"{role}_score", {}).get("score", 0) or 0)
                                            for role in ["fundamental", "technical", "sentiment", "macro"]
                                        },
                                        debate_summary=(
                                            f"Bull: {debate.get('bull_argument', '')[:200]} | "
                                            f"Bear: {debate.get('bear_argument', '')[:200]}"
                                        ) if debate else "",
                                        judge_reasoning=reasoning[:500] if reasoning else "",
                                        market_regime=result.get("regime", {}).get("regime", "SIDEWAYS"),
                                    )
                                except Exception as vs_err:
                                    if logger: await logger.debug(
                                        "trade_context_store_skipped", error=str(vs_err),
                                    )

                                await send_alert(
                                    f"🎯 *ORDER SUBMITTED: {ticker}*\n\n"
                                    f"💰 Amount: *${tranche_size:,.0f}*\n"
                                    f"📈 Price: *${current_price:.2f}*\n"
                                    f"🛡 Stop Loss: *${intent.stop_loss_price:.2f}* (-{sl_pct:.1f}%)\n"
                                    f"🎯 Take Profit: *${intent.take_profit_price:.2f}* (+{tp_pct:.1f}%)\n"
                                    f"🔖 Order ID: `{order_id[:8]}`\n"
                                    f"🤖 Agents: {len(agent_predictions)} analysts\n"
                                    f"⚖️ Conviction: {aggregated.get('weighted_conviction', 0):.2f}\n\n"
                                    f"```\n{reasoning[:250]}\n```"
                                )
                            else:
                                await send_alert(
                                    f"⏭ *Skip: {ticker}*\n"
                                    f"📊 Action: {action} | Confidence: {_conf}\n"
                                    f"```\n{reasoning[:200]}\n```"
                                )

                            continue  # DAG handled this candidate, skip fallback

                        except Exception as dag_err:
                            if logger: await logger.awarning(
                                "dag_execution_failed_using_fallback",
                                ticker=ticker, error=str(dag_err),
                            )
                            # Fall through to inline LLM fallback below

                    # ── Fallback: Inline LLM (when DAG unavailable) ────
                    from core.llm_factory import get_premium_llm
                    llm = get_premium_llm()

                    mdc3 = MarketDataClient()
                    bars = await mdc3.get_bars(ticker, timeframe="1Day", limit=10)
                    await mdc3.close()

                    bars_summary = ""
                    if bars:
                        recent = bars[-5:] if len(bars) >= 5 else bars
                        bars_summary = "Recent closes: " + ", ".join(f"${b['close']:.2f}" for b in recent)

                    prompt = (
                        f"You are a professional stock analyst for an autonomous trading system.\n"
                        f"Analyze {ticker} for a swing trade (hold 1-5 days).\n\n"
                        f"Data:\n"
                        f"- Current price: ${current_price:.2f}\n"
                        f"- Momentum score: {candidate.get('momentum_score', 0):.2f} (-1 to 1)\n"
                        f"- Today's change: {candidate.get('change_pct', 0):.1f}%\n"
                        f"- Volume: {candidate.get('volume', 0):,}\n"
                        f"- {bars_summary}\n\n"
                        f"Respond EXACTLY in this format:\n"
                        f"ACTION: BUY or PASS\n"
                        f"CONFIDENCE: 1-10\n"
                        f"REASONING: one sentence\n"
                        f"STOP_LOSS_PCT: number (e.g. 2.0)\n"
                        f"TAKE_PROFIT_PCT: number (e.g. 5.0)"
                    )
                    response = await llm.ainvoke(prompt)
                    analysis = extract_text(response.content)

                    if logger:
                        await logger.ainfo("fallback_trade_analysis", ticker=ticker, analysis=analysis[:200])

                    if "ACTION: BUY" in analysis.upper():
                        sl_pct, tp_pct = 2.0, 5.0
                        for line in analysis.split("\n"):
                            if "STOP_LOSS_PCT" in line.upper():
                                try: sl_pct = float(line.split(":")[-1].strip().replace("%", ""))
                                except: pass
                            if "TAKE_PROFIT_PCT" in line.upper():
                                try: tp_pct = float(line.split(":")[-1].strip().replace("%", ""))
                                except: pass

                        from core.models.portfolio import TradeIntent, TradeSide
                        import uuid
                        tranche_size = 10000.0

                        intent = TradeIntent(
                            ticker=ticker, side=TradeSide.BUY,
                            notional=tranche_size,
                            stop_loss_price=round(current_price * (1 - sl_pct / 100), 2),
                            take_profit_price=round(current_price * (1 + tp_pct / 100), 2),
                            client_order_id=str(uuid.uuid4()),
                        )

                        _conf = 5.0
                        for _line in analysis.split("\n"):
                            if "CONFIDENCE" in _line.upper():
                                try: _conf = float(_line.split(":")[-1].strip())
                                except: pass

                        from core.hitl_gateway import hitl_gateway, should_trigger_hitl
                        _should_hitl, _hitl_reason = should_trigger_hitl(
                            confidence=_conf, notional=tranche_size,
                            equity=system_state.get("portfolio", {}).get("total_equity", 100),
                            num_positions=len(system_state.get("portfolio", {}).get("positions", {})),
                            drawdown_pct=system_state.get("portfolio", {}).get("drawdown_pct", 0),
                        )
                        if _should_hitl:
                            hitl_req = await hitl_gateway.request_approval(
                                ticker=ticker, side="BUY", notional=tranche_size,
                                price=current_price, stop_loss=intent.stop_loss_price,
                                take_profit=intent.take_profit_price, confidence=_conf,
                                trigger_reason=_hitl_reason, analysis=analysis,
                            )
                            resolved = await hitl_gateway.wait_for_resolution(hitl_req.id)
                            if resolved.status.value == "REJECTED":
                                await send_alert(f"🚫 *HITL REJECTED:* {ticker}")
                                continue
                            elif resolved.status.value == "MODIFIED":
                                if resolved.modified_sl: intent.stop_loss_price = resolved.modified_sl
                                if resolved.modified_tp: intent.take_profit_price = resolved.modified_tp

                        order = await alpaca.submit_bracket_order(intent)
                        order_id = order.get("id", "?")
                        trade_id = intent.client_order_id

                        if self.trade_publisher:
                            await self.trade_publisher.on_order_submitted(
                                trade_id=trade_id, ticker=ticker,
                                side="BUY", notional=tranche_size,
                                analysis=analysis, confidence=_conf,
                                current_price=current_price,
                            )

                        await send_alert(
                            f"🎯 *ORDER (Fallback): {ticker}*\n"
                            f"💰 ${tranche_size:,.0f} @ ${current_price:.2f}\n"
                            f"🛡 SL: ${intent.stop_loss_price:.2f} | TP: ${intent.take_profit_price:.2f}\n"
                            f"```\n{analysis[:250]}\n```"
                        )
                    else:
                        await send_alert(f"⏭ *Skip: {ticker}*\n```\n{analysis[:200]}\n```")

                except Exception as e:
                    if logger: await logger.aerror("trade_analysis_failed", ticker=ticker, error=str(e))
                    await send_alert(f"⚠️ Analysis failed for `{ticker}`: `{str(e)[:80]}`")

            await alpaca.close()
            if logger: await logger.ainfo("market_open_complete")

        except Exception as e:
            if logger: await logger.aerror("market_open_failed", error=str(e))

    async def _run_intraday_scan(self) -> None:
        """Intraday scan: Re-screen for new opportunities mid-day."""
        global logger
        if logger: await logger.ainfo("phase_started", phase="INTRADAY_SCAN")

        try:
            from integrations.telegram_bot import send_alert
            from integrations.market_data import MarketDataClient
            from research.screener import StockScreener
            from dashboard.api.main import system_state

            # Check market is open
            mdc = MarketDataClient()
            if not await mdc.is_market_open():
                await mdc.close()
                return

            # Fresh screen
            screener = StockScreener(mdc)
            candidates = await screener.screen_candidates(max_results=3)
            await mdc.close()

            if not candidates:
                if logger: await logger.ainfo("intraday_scan_no_candidates")
                return

            # Check how many positions we already have
            from dashboard.api.main import sync_alpaca_portfolio
            await sync_alpaca_portfolio()
            p = system_state.get("portfolio", {})
            open_positions = len(p.get("positions", {}))

            if open_positions >= 5:
                await send_alert("📊 *Intraday Scan*: 5+ positions open, skipping new entries.")
                return

            # Analyze top candidate only (1 per scan for discipline)
            candidate = candidates[0]
            ticker = candidate["ticker"]

            # Skip if we already hold this
            if ticker in p.get("positions", {}):
                if logger: await logger.ainfo("intraday_skip_existing", ticker=ticker)
                return

            from broker.alpaca_client import AlpacaClient
            alpaca = AlpacaClient()

            mdc2 = MarketDataClient()
            quote = await mdc2.get_latest_quote(ticker)
            current_price = quote.get("ask", candidate.get("price", 0))
            await mdc2.close()

            # ── Multi-Agent DAG Path ────────────────────────────
            dag_handled = False
            try:
                from orchestration.trading_dag import compile_trading_dag
                dag = compile_trading_dag()

                initial_state = {
                    "ticker": ticker,
                    "regime": {},
                    "portfolio": p,
                    "fundamental_score": {},
                    "technical_score": {},
                    "sentiment_score": {},
                    "macro_score": {},
                    "aggregated_research": {},
                    "debate_state": {},
                    "execution_order": {},
                    "guardrail_result": "",
                    "hitl_action": "",
                    "trade_result": {},
                    "error": "",
                    "step": "",
                }

                result = await dag.ainvoke(initial_state)
                dag_handled = True

                execution_order = result.get("execution_order", {})
                action = execution_order.get("action", "PASS")
                _conf = execution_order.get("confidence_score", 0)
                reasoning = execution_order.get("reasoning", "")
                allocated_capital = execution_order.get("allocated_capital", 0)
                aggregated = result.get("aggregated_research", {})

                analysis = (
                    f"ACTION: {action}\nCONFIDENCE: {_conf}\n"
                    f"REASONING: {reasoning}\n"
                    f"Conviction: {aggregated.get('weighted_conviction', 0):.2f}"
                )

                if action == "BUY" and result.get("guardrail_result") != "REJECTED":
                    from core.models.portfolio import TradeIntent, TradeSide
                    import uuid

                    tranche_size = allocated_capital if allocated_capital > 0 else 10000.0
                    sl_pct, tp_pct = 2.0, 5.0

                    intent = TradeIntent(
                        ticker=ticker, side=TradeSide.BUY,
                        notional=tranche_size,
                        stop_loss_price=round(current_price * (1 - sl_pct / 100), 2),
                        take_profit_price=round(current_price * (1 + tp_pct / 100), 2),
                        client_order_id=str(uuid.uuid4()),
                    )

                    from core.hitl_gateway import hitl_gateway, should_trigger_hitl
                    _should_hitl, _hitl_reason = should_trigger_hitl(
                        confidence=_conf, notional=tranche_size,
                        equity=p.get("total_equity", 100),
                        num_positions=open_positions,
                        drawdown_pct=p.get("drawdown_pct", 0),
                    )

                    if _should_hitl:
                        hitl_req = await hitl_gateway.request_approval(
                            ticker=ticker, side="BUY", notional=tranche_size,
                            price=current_price,
                            stop_loss=intent.stop_loss_price,
                            take_profit=intent.take_profit_price,
                            confidence=_conf,
                            trigger_reason=_hitl_reason,
                            analysis=analysis,
                        )
                        resolved = await hitl_gateway.wait_for_resolution(hitl_req.id)
                        if resolved.status.value == "REJECTED":
                            await send_alert(f"🚫 *HITL REJECTED:* {ticker}")
                            await alpaca.close()
                            return
                        elif resolved.status.value == "MODIFIED":
                            if resolved.modified_sl: intent.stop_loss_price = resolved.modified_sl
                            if resolved.modified_tp: intent.take_profit_price = resolved.modified_tp

                    order = await alpaca.submit_bracket_order(intent)
                    trade_id = intent.client_order_id

                    # Record per-agent predictions
                    agent_predictions = {}
                    for role in ["fundamental", "technical", "sentiment", "macro"]:
                        score_data = result.get(f"{role}_score", {})
                        if score_data.get("score") is not None:
                            prob = (float(score_data["score"]) + 1.0) / 2.0
                            agent_predictions[f"{role.upper()}_ANALYST"] = prob

                    if self.trade_publisher:
                        await self.trade_publisher.on_order_submitted(
                            trade_id=trade_id, ticker=ticker,
                            side="BUY", notional=tranche_size,
                            analysis=analysis, confidence=_conf,
                            current_price=current_price,
                            agent_predictions=agent_predictions if agent_predictions else None,
                        )

                    await send_alert(
                        f"📊 *INTRADAY ORDER: {ticker}*\n\n"
                        f"💰 ${tranche_size:,.0f} @ ${current_price:.2f}\n"
                        f"🛡 SL: ${intent.stop_loss_price:.2f} | TP: ${intent.take_profit_price:.2f}\n"
                        f"🤖 {len(agent_predictions)} analysts\n"
                        f"```\n{reasoning[:200]}\n```"
                    )
                else:
                    if logger: await logger.ainfo("intraday_dag_pass", ticker=ticker, action=action)

            except Exception as dag_err:
                if logger: await logger.awarning("intraday_dag_failed", ticker=ticker, error=str(dag_err))

            # ── Fallback: Inline LLM ────
            if not dag_handled:
                from core.llm_factory import get_premium_llm
                llm = get_premium_llm()

                response = await llm.ainvoke(
                    f"Intraday opportunity scan. Analyze {ticker} at ${current_price:.2f}. "
                    f"Momentum: {candidate.get('momentum_score', 0):.2f}, "
                    f"Change: {candidate.get('change_pct', 0):.1f}%. "
                    f"Should we BUY or PASS? Format: ACTION: BUY/PASS, CONFIDENCE: 1-10, REASONING: one line, "
                    f"STOP_LOSS_PCT: number, TAKE_PROFIT_PCT: number"
                )
                analysis = extract_text(response.content)

                if "ACTION: BUY" in analysis.upper():
                    from core.models.portfolio import TradeIntent, TradeSide
                    import uuid

                    sl_pct, tp_pct = 2.0, 5.0
                    for line in analysis.split("\n"):
                        if "STOP_LOSS_PCT" in line.upper():
                            try: sl_pct = float(line.split(":")[-1].strip().replace("%", ""))
                            except: pass
                        if "TAKE_PROFIT_PCT" in line.upper():
                            try: tp_pct = float(line.split(":")[-1].strip().replace("%", ""))
                            except: pass

                    intent = TradeIntent(
                        ticker=ticker, side=TradeSide.BUY, notional=10000.0,
                        stop_loss_price=round(current_price * (1 - sl_pct / 100), 2),
                        take_profit_price=round(current_price * (1 + tp_pct / 100), 2),
                        client_order_id=str(uuid.uuid4()),
                    )

                    _conf = 5.0
                    for _line in analysis.split("\n"):
                        if "CONFIDENCE" in _line.upper():
                            try: _conf = float(_line.split(":")[-1].strip())
                            except: pass

                    from core.hitl_gateway import hitl_gateway, should_trigger_hitl
                    _should_hitl, _hitl_reason = should_trigger_hitl(
                        confidence=_conf, notional=10000.0,
                        equity=p.get("total_equity", 100),
                        num_positions=open_positions,
                        drawdown_pct=p.get("drawdown_pct", 0),
                    )
                    if _should_hitl:
                        hitl_req = await hitl_gateway.request_approval(
                            ticker=ticker, side="BUY", notional=10000.0,
                            price=current_price, stop_loss=intent.stop_loss_price,
                            take_profit=intent.take_profit_price, confidence=_conf,
                            trigger_reason=_hitl_reason, analysis=analysis,
                        )
                        resolved = await hitl_gateway.wait_for_resolution(hitl_req.id)
                        if resolved.status.value == "REJECTED":
                            await send_alert(f"🚫 *HITL REJECTED:* {ticker}")
                            await alpaca.close()
                            return
                        elif resolved.status.value == "MODIFIED":
                            if resolved.modified_sl: intent.stop_loss_price = resolved.modified_sl
                            if resolved.modified_tp: intent.take_profit_price = resolved.modified_tp

                    order = await alpaca.submit_bracket_order(intent)
                    trade_id = intent.client_order_id

                    if self.trade_publisher:
                        await self.trade_publisher.on_order_submitted(
                            trade_id=trade_id, ticker=ticker,
                            side="BUY", notional=10000.0,
                            analysis=analysis, confidence=_conf,
                            current_price=current_price,
                        )

                    await send_alert(
                        f"📊 *INTRADAY ORDER (Fallback): {ticker}*\n"
                        f"💰 $10,000 @ ${current_price:.2f}\n"
                        f"🛡 SL: ${intent.stop_loss_price:.2f} | TP: ${intent.take_profit_price:.2f}\n"
                        f"```\n{analysis[:200]}\n```"
                    )
                else:
                    if logger: await logger.ainfo("intraday_pass", ticker=ticker)

            await alpaca.close()

        except Exception as e:
            if logger: await logger.aerror("intraday_scan_failed", error=str(e))

    async def _run_crypto_scan(self) -> None:
        """Crypto scan: 24/7, runs every 4 hours, trades crypto on Alpaca."""
        global logger
        if logger: await logger.ainfo("phase_started", phase="CRYPTO_SCAN")

        try:
            from integrations.telegram_bot import send_alert
            from integrations.crypto_data import CryptoDataClient, CryptoScreener
            from dashboard.api.main import system_state
            system_state["current_phase"] = "CRYPTO_SCAN"

            # Screen crypto
            cdc = CryptoDataClient()
            screener = CryptoScreener(cdc)
            candidates = await screener.screen_candidates(max_results=3)

            if not candidates:
                await cdc.close()
                if logger: await logger.ainfo("crypto_scan_no_candidates")
                return

            # Check existing crypto positions
            from dashboard.api.main import sync_alpaca_portfolio
            await sync_alpaca_portfolio()
            p = system_state.get("portfolio", {})
            crypto_positions = sum(1 for t in p.get("positions", {}) if "/" in t)

            if crypto_positions >= 3:
                await cdc.close()
                if logger: await logger.ainfo("crypto_max_positions", count=crypto_positions)
                return

            # Analyze top candidate
            candidate = candidates[0]
            ticker = candidate["ticker"]

            # Skip if already holding
            if ticker in p.get("positions", {}) or ticker.replace("/", "") in p.get("positions", {}):
                await cdc.close()
                return

            # Get fresh quote
            quotes = await cdc.get_latest_quotes([ticker])
            current_price = quotes.get(ticker, {}).get("ask", candidate["price"])

            # Get bars for context
            bars = await cdc.get_bars(ticker, timeframe="1Day", limit=7)
            await cdc.close()

            bars_summary = ""
            if bars:
                recent = bars[-5:] if len(bars) >= 5 else bars
                bars_summary = "Recent closes: " + ", ".join(f"${b['close']:.2f}" for b in recent)

            from core.llm_factory import get_premium_llm
            llm = get_premium_llm()

            response = await llm.ainvoke(
                f"You are a crypto trading analyst. Analyze {ticker} for a swing trade.\n"
                f"Price: ${current_price:.2f}, Momentum: {candidate.get('momentum_score', 0):.2f}, "
                f"24h change: {candidate.get('change_pct', 0):.1f}%\n"
                f"{bars_summary}\n\n"
                f"Crypto is volatile — use wider stops (3-5%). "
                f"Respond: ACTION: BUY or PASS, CONFIDENCE: 1-10, REASONING: one line, "
                f"STOP_LOSS_PCT: number, TAKE_PROFIT_PCT: number"
            )
            analysis = extract_text(response.content)  # noqa: normalize list→str

            if "ACTION: BUY" in analysis.upper():
                import uuid

                sl_pct, tp_pct = 4.0, 8.0  # Wider for crypto
                for line in analysis.split("\n"):
                    if "STOP_LOSS_PCT" in line.upper():
                        try: sl_pct = float(line.split(":")[-1].strip().replace("%", ""))
                        except: pass
                    if "TAKE_PROFIT_PCT" in line.upper():
                        try: tp_pct = float(line.split(":")[-1].strip().replace("%", ""))
                        except: pass

                sl_price = round(current_price * (1 - sl_pct / 100), 2)
                tp_price = round(current_price * (1 + tp_pct / 100), 2)

                # ── HITL Gate: Check if human approval needed (Gap #1 fix) ──
                _conf = 5.0
                for _line in analysis.split("\n"):
                    if "CONFIDENCE" in _line.upper():
                        try: _conf = float(_line.split(":")[-1].strip())
                        except: pass

                from core.hitl_gateway import hitl_gateway, should_trigger_hitl
                _should_hitl, _hitl_reason = should_trigger_hitl(
                    confidence=_conf,
                    notional=5000.0,
                    equity=p.get("total_equity", 100),
                    num_positions=crypto_positions,
                    drawdown_pct=p.get("drawdown_pct", 0),
                )

                if _should_hitl:
                    hitl_req = await hitl_gateway.request_approval(
                        ticker=ticker, side="BUY", notional=5000.0,
                        price=current_price,
                        stop_loss=sl_price,
                        take_profit=tp_price,
                        confidence=_conf,
                        trigger_reason=_hitl_reason,
                        analysis=analysis,
                    )
                    resolved = await hitl_gateway.wait_for_resolution(hitl_req.id)

                    if resolved.status.value == "REJECTED":
                        await send_alert(f"🚫 *HITL REJECTED:* {ticker}\n_{resolved.human_notes or 'No reason given'}_")
                        return
                    elif resolved.status.value == "MODIFIED":
                        if resolved.modified_sl:
                            sl_price = resolved.modified_sl
                        if resolved.modified_tp:
                            tp_price = resolved.modified_tp
                    # APPROVED or TIMED_OUT → proceed

                # Crypto: simple market order (bracket not supported)
                import httpx
                from config.settings import get_settings
                settings = get_settings()
                trade_id = str(uuid.uuid4())
                order_data = {
                    "symbol": ticker,  # Alpaca accepts "BTC/USD" for crypto
                    "notional": "5000",
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "gtc",  # GTC for crypto (not "day")
                    "client_order_id": trade_id,
                }
                async with httpx.AsyncClient(
                    headers={
                        "APCA-API-KEY-ID": settings.alpaca_api_key,
                        "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
                    },
                    timeout=15,
                ) as hc:
                    r = await hc.post(f"{settings.alpaca_base_url}/v2/orders", json=order_data)
                    r.raise_for_status()
                    order = r.json()

                order_id = order.get("id", "?")

                # Track SL/TP in system state for software stop monitoring
                system_state.setdefault("crypto_stops", {})[ticker] = {
                    "entry": current_price,
                    "sl": sl_price,
                    "tp": tp_price,
                    "order_id": order_id,
                    "trade_id": trade_id,
                }

                # ── Record prediction via Event Bus (Gap #2 + Gap #3 fix) ──
                # Record a prediction for the CRYPTO_ANALYST role so crypto
                # trades contribute to Brier scoring and agent evolution.
                if self.trade_publisher:
                    crypto_prob = min(max(_conf / 10.0, 0.0), 1.0)
                    await self.trade_publisher.on_order_submitted(
                        trade_id=trade_id, ticker=ticker,
                        side="BUY", notional=5000.0,
                        analysis=analysis, confidence=_conf,
                        current_price=current_price,
                        agent_predictions={"CRYPTO_ANALYST": crypto_prob},
                    )

                await send_alert(
                    f"🪙 *CRYPTO ORDER: {ticker}*\n\n"
                    f"💰 $5,000 @ ${current_price:,.2f}\n"
                    f"🛡 SL: ${sl_price:,.2f} (-{sl_pct}%)\n"
                    f"🎯 TP: ${tp_price:,.2f} (+{tp_pct}%)\n"
                    f"🔖 ID: `{order_id[:8]}`\n"
                    f"```\n{analysis[:200]}\n```"
                )
            else:
                if logger: await logger.ainfo("crypto_pass", ticker=ticker)

        except Exception as e:
            if logger: await logger.aerror("crypto_scan_failed", error=str(e))
            try:
                from integrations.telegram_bot import send_alert
                await send_alert(f"⚠️ Crypto scan error: `{str(e)[:100]}`")
            except Exception:
                pass

    async def _run_continuous_evolution(self) -> None:
        """Continuous evolution: runs every 6 hours, 24/7.

        - Backtest current strategies on recent data
        - Update agent trust scores
        - Run system audit
        - Research new strategy improvements via Gemini
        """
        global logger
        if logger: await logger.ainfo("phase_started", phase="CONTINUOUS_EVOLUTION")

        try:
            from integrations.telegram_bot import send_alert
            from dashboard.api.main import system_state
            system_state["current_phase"] = "EVOLVING"

            # 1. Backtest current strategies
            from research.backtester import StrategyBacktester
            from integrations.market_data import MarketDataClient
            mdc = MarketDataClient()
            bt = StrategyBacktester(mdc)

            test_tickers = ["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL"]
            backtest_results = []
            for ticker in test_tickers:
                try:
                    result = await bt.compare_strategies(ticker, lookback_days=30)
                    backtest_results.append(result)
                except Exception:
                    pass
            await mdc.close()

            # 2. Update trust weights from real Brier scores
            trust_report = {}
            try:
                from evolution.trust_updater import update_all_trust_weights
                trust_report = update_all_trust_weights()
                if logger: await logger.ainfo(
                    "trust_weights_updated_in_cycle",
                    agents_updated=trust_report.get("agents_updated", 0),
                )
            except Exception as trust_err:
                if logger: await logger.awarning(
                    "trust_update_skipped", error=str(trust_err),
                    message="Evolution continues without trust updates",
                )

            # 3. Run system audit (guarded — don't let audit failure kill evolution)
            readiness = 0
            try:
                from agents.skills.jarvis.system_audit import SystemAuditor
                auditor = SystemAuditor()
                audit = auditor.run_audit()
                readiness = audit.get("readiness_score", 0) * 100
            except Exception as audit_err:
                if logger: await logger.awarning(
                    "system_audit_skipped", error=str(audit_err),
                    message="Evolution continues without audit data",
                )

            # 4. Ask Gemini to analyze and suggest improvements
            from core.llm_factory import get_efficient_llm
            llm = get_efficient_llm()

            bt_summary = "\n".join(
                f"  {r.get('ticker','?')}: {r.get('recommended','?')} "
                f"(momentum: {r.get('momentum',{}).get('total_return',0):.1f}%, "
                f"mean_rev: {r.get('mean_reversion',{}).get('total_return',0):.1f}%)"
                for r in backtest_results
            ) or "  No backtest data"

            p = system_state.get("portfolio", {})
            response = await llm.ainvoke(
                f"You are the evolution engine of an autonomous trading system.\n\n"
                f"Portfolio: ${p.get('total_equity',0):,.2f} equity, "
                f"${p.get('daily_pnl',0):,.2f} daily P&L\n"
                f"Positions: {len(p.get('positions',{}))}\n"
                f"System readiness: {readiness:.0f}%\n\n"
                f"Latest backtests (30 days):\n{bt_summary}\n\n"
                f"Write a brief evolution report (3-4 sentences):\n"
                f"1. Which strategies are working?\n"
                f"2. What should we adjust?\n"
                f"3. Any new opportunities to explore?"
            )

            report = extract_text(response.content)  # noqa: normalize list→str

            # Include trust weight summary in the report
            trust_summary = ""
            if trust_report.get("agents_updated", 0) > 0:
                trust_summary = f"\n🔄 Trust weights updated: {trust_report['agents_updated']} agents\n"

            await send_alert(
                f"🧬 *Evolution Report*\n\n"
                f"⏰ Cycle: {datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('America/Los_Angeles')).strftime('%I:%M %p PST')}\n"
                f"📊 Readiness: `{readiness:.0f}%`\n"
                f"📈 Strategies tested: {len(backtest_results)}"
                f"{trust_summary}\n"
                f"{report[:500]}"
            )

            system_state["current_phase"] = "IDLE"
            if logger: await logger.ainfo("continuous_evolution_complete")

        except Exception as e:
            if logger: await logger.aerror("continuous_evolution_failed", error=str(e))

    # ── B2 FIX: Position Review ────────────────────────────────

    async def _run_position_review(self) -> None:
        """Review open positions and apply deterministic exit rules.

        Runs every 30 minutes during market hours.
        Uses deterministic Python rules (no LLM) for exit decisions:
        - Trailing stop tightening for winners
        - Time decay exits for stale positions
        - Regime-based exits in adverse conditions
        """
        global logger
        if logger: await logger.ainfo("phase_started", phase="POSITION_REVIEW")

        try:
            from broker.alpaca_client import AlpacaClient
            from orchestration.position_review import (
                review_positions, format_telegram_report,
            )
            from integrations.telegram_bot import send_alert
            from persistence.db import get_recent_trades

            # Get current positions from Alpaca
            alpaca = AlpacaClient()
            positions = await alpaca.get_positions()

            if not positions:
                await alpaca.close()
                return

            # Get current regime
            regime = "SIDEWAYS"
            try:
                from core.insight_publisher import insight_publisher
                regime_insight = insight_publisher.get_active_regime()
                if regime_insight:
                    regime = regime_insight.data.get("regime", "SIDEWAYS")
            except Exception:
                pass

            # Get trade history for hold duration calculation
            trades_db = get_recent_trades(limit=100)

            # Run deterministic review
            recommendations = review_positions(
                positions=positions,
                regime=regime,
                trades_db=trades_db,
            )

            if not recommendations:
                await alpaca.close()
                if logger: await logger.ainfo("position_review_complete", actions=0)
                return

            # Execute recommendations
            actions_taken = 0
            for rec in recommendations:
                try:
                    if rec.action == "CLOSE":
                        result = await alpaca.close_position(rec.ticker)
                        actions_taken += 1

                        # Resolve predictions for this closed position
                        try:
                            from evolution.prediction_tracker import prediction_tracker
                            # Determine P&L from position data
                            pos_data = next(
                                (p for p in positions if p.get("symbol") == rec.ticker),
                                None,
                            )
                            if pos_data:
                                pnl = float(pos_data.get("unrealized_pl", 0))
                                # Find the trade_id for this ticker
                                for trade in trades_db:
                                    if (trade.get("ticker") == rec.ticker
                                            and trade.get("status") == "FILLED"):
                                        prediction_tracker.resolve_trade(
                                            trade["id"], profitable=(pnl > 0)
                                        )
                                        break
                        except Exception as pred_err:
                            if logger:
                                await logger.awarning(
                                    "position_close_prediction_resolution_failed",
                                    ticker=rec.ticker, error=str(pred_err),
                                )

                        if logger:
                            await logger.ainfo(
                                "position_closed_by_review",
                                ticker=rec.ticker,
                                reason=rec.reason,
                                urgency=rec.urgency,
                            )

                    elif rec.action == "TIGHTEN_STOP" and rec.new_stop_price:
                        # Find the stop order for this position and replace it
                        # For now, log the recommendation — full stop replacement
                        # requires tracking the stop order ID
                        if logger:
                            await logger.ainfo(
                                "trailing_stop_recommendation",
                                ticker=rec.ticker,
                                new_stop=rec.new_stop_price,
                                reason=rec.reason,
                            )

                except Exception as exec_err:
                    if logger:
                        await logger.awarning(
                            "position_review_action_failed",
                            ticker=rec.ticker,
                            action=rec.action,
                            error=str(exec_err),
                        )

            await alpaca.close()

            # Send Telegram report
            if actions_taken > 0:
                report = format_telegram_report(recommendations)
                await send_alert(report)

            if logger:
                await logger.ainfo(
                    "position_review_complete",
                    positions_reviewed=len(positions),
                    recommendations=len(recommendations),
                    actions_taken=actions_taken,
                )

        except Exception as e:
            if logger: await logger.aerror("position_review_failed", error=str(e))

    async def _run_crypto_stop_monitor(self) -> None:
        """Monitor crypto positions against stored stop-loss/take-profit levels.

        Runs every 15 minutes, 24/7.
        Checks prices and closes positions that hit SL or TP.
        """
        global logger

        try:
            from persistence.db import get_active_crypto_stops, update_crypto_stop_status
            from evolution.prediction_tracker import prediction_tracker

            active_stops = get_active_crypto_stops()
            if not active_stops:
                return

            from broker.alpaca_client import AlpacaClient
            alpaca = AlpacaClient()

            for stop in active_stops:
                ticker = stop.get("ticker", "")
                entry = stop.get("entry_price", 0)
                sl = stop.get("stop_loss", 0)
                tp = stop.get("take_profit", 0)
                order_id = stop.get("order_id", "")

                if not ticker or not entry:
                    continue

                # Get current price
                try:
                    quote = await alpaca.get_latest_quote(ticker)
                    current_price = float(
                        quote.get("quote", {}).get("ap", 0)
                        or quote.get("ask", 0)
                        or 0
                    )
                except Exception:
                    continue

                if current_price <= 0:
                    continue

                # Check stops
                if sl > 0 and current_price <= sl:
                    # Stop loss hit
                    try:
                        await alpaca.close_position(ticker)
                        update_crypto_stop_status(ticker, "STOPPED")
                        if order_id:
                            prediction_tracker.resolve_trade(order_id, profitable=False)

                        from integrations.telegram_bot import send_alert
                        pnl_pct = ((current_price - entry) / entry * 100)
                        await send_alert(
                            f"🔴 *Crypto Stop Loss Hit*\n\n"
                            f"Ticker: `{ticker}`\n"
                            f"Entry: ${entry:,.2f}\n"
                            f"Exit: ${current_price:,.2f}\n"
                            f"P&L: {pnl_pct:+.1f}%"
                        )
                    except Exception as e:
                        if logger:
                            await logger.awarning("crypto_sl_execution_failed",
                                                   ticker=ticker, error=str(e))

                elif tp > 0 and current_price >= tp:
                    # Take profit hit
                    try:
                        await alpaca.close_position(ticker)
                        update_crypto_stop_status(ticker, "PROFIT_TAKEN")
                        if order_id:
                            prediction_tracker.resolve_trade(order_id, profitable=True)

                        from integrations.telegram_bot import send_alert
                        pnl_pct = ((current_price - entry) / entry * 100)
                        await send_alert(
                            f"🟢 *Crypto Take Profit Hit*\n\n"
                            f"Ticker: `{ticker}`\n"
                            f"Entry: ${entry:,.2f}\n"
                            f"Exit: ${current_price:,.2f}\n"
                            f"P&L: {pnl_pct:+.1f}%"
                        )
                    except Exception as e:
                        if logger:
                            await logger.awarning("crypto_tp_execution_failed",
                                                   ticker=ticker, error=str(e))

            await alpaca.close()

        except Exception as e:
            if logger: await logger.aerror("crypto_stop_monitor_failed", error=str(e))

    async def _run_market_close(self) -> None:
        """Market close: Journal results, resolve predictions, update portfolio."""
        global logger
        if logger: await logger.ainfo("phase_started", phase="MARKET_CLOSE")

        try:
            from integrations.telegram_bot import send_alert
            from dashboard.api.main import system_state, sync_alpaca_portfolio
            system_state["current_phase"] = "MARKET_CLOSE"

            # Sync latest portfolio from Alpaca
            await sync_alpaca_portfolio()
            p = system_state.get("portfolio", {})

            equity = p.get("total_equity", 0)
            pnl = p.get("daily_pnl", 0)
            positions = p.get("positions", {})

            # ── Resolve predictions for closed orders (Gap #3 fix) ──
            # Check Alpaca for orders that filled and closed today
            resolved_count = 0
            try:
                from evolution.prediction_tracker import prediction_tracker
                from broker.alpaca_client import AlpacaClient
                alpaca = AlpacaClient()
                closed_orders = await alpaca.get_closed_orders(limit=50)
                await alpaca.close()

                for order in closed_orders:
                    client_oid = order.get("client_order_id")
                    if not client_oid:
                        continue

                    # Determine if the trade was profitable
                    filled_avg = float(order.get("filled_avg_price", 0) or 0)
                    side = order.get("side", "buy")

                    # For closed bracket orders, check if TP or SL was hit
                    # Simple heuristic: if order status is 'filled' and there's
                    # a matching position that's been closed, check current vs entry
                    order_status = order.get("status", "")
                    if order_status in ("filled", "closed") and filled_avg > 0:
                        # Check if there's a corresponding sell/close
                        ticker = order.get("symbol", "")
                        # If the position is no longer open, it was closed
                        if ticker and ticker not in positions:
                            # Try to determine profit from order legs
                            legs = order.get("legs", [])
                            profitable = None
                            for leg in legs:
                                if leg.get("status") == "filled" and leg.get("side") == "sell":
                                    sell_price = float(leg.get("filled_avg_price", 0) or 0)
                                    if sell_price > 0 and filled_avg > 0:
                                        profitable = sell_price > filled_avg

                            if profitable is not None:
                                updated = prediction_tracker.resolve_trade(
                                    trade_id=client_oid,
                                    profitable=profitable,
                                )
                                if updated > 0:
                                    resolved_count += updated

                if resolved_count > 0 and logger:
                    await logger.ainfo("predictions_resolved", count=resolved_count)

            except Exception as pred_err:
                if logger:
                    await logger.awarning("prediction_resolution_failed", error=str(pred_err))

            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            resolved_line = f"\n📊 Predictions resolved: *{resolved_count}*" if resolved_count > 0 else ""
            await send_alert(
                f"🔔 *Market Close*\n\n"
                f"💰 Equity: *${equity:,.2f}*\n"
                f"{pnl_emoji} Daily P&L: *${pnl:,.2f}*\n"
                f"📦 Open positions: *{len(positions)}*"
                f"{resolved_line}"
            )

            if logger: await logger.ainfo("market_close_complete", equity=equity, pnl=pnl,
                                           predictions_resolved=resolved_count)

        except Exception as e:
            if logger: await logger.aerror("market_close_failed", error=str(e))

    async def _run_post_market_evolution(self) -> None:
        """Post-market: Run the full self-evolution cycle.

        This is the REAL evolution — not just an LLM summary.
        1. Compute Brier scores from actual predictions
        2. Update trust weights for all agents
        3. Generate post-mortems for underperformers
        4. Propose prompt mutations (validated by domain isolation)
        5. Evaluate mature Shadow Crew A/B tests
        6. Auto-promote statistically significant improvements
        """
        global logger
        if logger: await logger.ainfo("phase_started", phase="POST_MARKET_EVOLUTION")

        try:
            from integrations.telegram_bot import send_alert
            from dashboard.api.main import system_state
            system_state["current_phase"] = "EVOLUTION"

            await send_alert("🧬 *Post-Market Evolution*\nRunning full reflexion cycle...")

            # Run the full evolution cycle
            from evolution.evolution_runner import evolution_runner
            evo_report = await evolution_runner.run_full_cycle()

            # Format and send the Telegram report
            telegram_msg = evolution_runner.format_telegram_report(evo_report)
            await send_alert(telegram_msg)

            # ── Gap 1 Fix: Run strategy agent evolution cycle ──────────
            # Evolve all 8 deterministic strategy agents using their own
            # Brier scores, shadow testing, and LLM reflection.
            try:
                from agents.strategies.strategy_evolution import strategy_evolution_engine
                if strategy_evolution_engine._strategies:
                    strat_report = await strategy_evolution_engine.run_evolution_cycle()
                    evolved_count = sum(
                        1 for r in strat_report.get("results", {}).values()
                        if r.get("evolved")
                    )
                    if evolved_count > 0:
                        await send_alert(
                            f"📈 *Strategy Evolution*\n\n"
                            f"Strategies evaluated: {len(strat_report.get('results', {}))}\n"
                            f"Strategies evolved: {evolved_count}"
                        )
                    if logger: await logger.ainfo(
                        "strategy_evolution_complete",
                        strategies=len(strat_report.get("results", {})),
                        evolved=evolved_count,
                    )
            except Exception as strat_evo_err:
                if logger: await logger.awarning(
                    "strategy_evolution_skipped", error=str(strat_evo_err),
                )

            # Also run system audit for general readiness
            readiness = 0
            try:
                from agents.skills.jarvis.system_audit import SystemAuditor
                auditor = SystemAuditor()
                audit = auditor.run_audit()
                readiness = audit.get("readiness_score", 0) * 100
            except Exception:
                pass

            # Generate end-of-day strategic summary via LLM
            from core.llm_factory import get_efficient_llm
            llm = get_efficient_llm()

            # Include evolution results in the prompt
            trust_data = evo_report.get("trust_updates", {})
            proposals = evo_report.get("prompt_proposals", [])
            shadows = evo_report.get("shadow_evaluations", [])

            p = system_state.get("portfolio", {})
            response = await llm.ainvoke(
                f"You are Jarvis, an autonomous trading system. Today's results:\n"
                f"- Equity: ${p.get('total_equity', 0):,.2f}\n"
                f"- Daily P&L: ${p.get('daily_pnl', 0):,.2f}\n"
                f"- Positions: {len(p.get('positions', {}))}\n"
                f"- System readiness: {readiness:.0f}%\n"
                f"- Trust weights updated: {trust_data.get('agents_updated', 0)}\n"
                f"- Prompt candidates created: {len(proposals)}\n"
                f"- Shadow tests evaluated: {len(shadows)}\n\n"
                f"Write a brief end-of-day report (3-4 sentences). "
                f"Include what went well, what to improve, and tomorrow's focus."
            )

            report = extract_text(response.content)  # noqa: normalize list→str
            await send_alert(
                f"📊 *End-of-Day Report*\n\n"
                f"Readiness: `{readiness:.0f}%`\n\n"
                f"{report}\n\n"
                f"_Next phase: Overnight research_"
            )

            system_state["current_phase"] = "IDLE"
            if logger: await logger.ainfo("evolution_complete")

        except Exception as e:
            if logger: await logger.aerror("evolution_failed", error=str(e))

    async def _overwatch_loop(self) -> None:
        """
        Overwatch Daemon: writes heartbeat every second.
        
        If this daemon crashes, the Dead Man's Switch triggers
        and halts all trading.
        """
        global logger
        _health_check_counter = 0
        while self._running:
            try:
                if self.dead_man_switch:
                    await self.dead_man_switch.write_heartbeat()

                # Publish health status every 60 heartbeats (~60 seconds)
                _health_check_counter += 1
                if _health_check_counter >= 60 and self.health_publisher:
                    _health_check_counter = 0
                    # Check component health
                    _redis_ok = True
                    try:
                        from persistence.redis_client import health_check as redis_health
                        _redis_ok = await redis_health()
                    except Exception:
                        _redis_ok = False

                    await self.health_publisher.check_and_publish(
                        redis_ok=_redis_ok,
                        circuit_breaker_tripped=self.circuit_breaker._tripped
                            if hasattr(self.circuit_breaker, '_tripped') else False,
                    )

                await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if logger:
                    await logger.aerror("overwatch_error", error=str(e))
                await asyncio.sleep(1)

    async def _settlement_check_loop(self) -> None:
        """Periodically check and settle matured tranches."""
        global logger
        while self._running:
            try:
                if self.state_manager:
                    settled = await self.state_manager.settle_matured_tranches()
                    if settled > 0 and logger:
                        await logger.ainfo(
                            "tranches_settled_in_loop",
                            count=settled,
                        )
                await asyncio.sleep(300)  # Check every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                if logger:
                    await logger.aerror("settlement_check_error", error=str(e))
                await asyncio.sleep(60)

    async def _run_dashboard(self) -> None:
        """Run the FastAPI dashboard in the background."""
        from dashboard.api.main import app
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.settings.dashboard_port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def _handle_alert(self, event: dict) -> None:
        """Handle incoming alert events."""
        global logger
        severity = event.get("data", {}).get("severity", "INFO")
        message = event.get("data", {}).get("message", "Unknown alert")

        if logger:
            await logger.awarning(
                "alert_received",
                severity=severity,
                message=message,
            )

        # In production: send Telegram notification for HIGH/CRITICAL alerts
        if severity in ("HIGH", "CRITICAL"):
            try:
                from integrations.telegram_bot import send_alert
                await send_alert(f"🚨 *Alert [{severity}]*\n{message}")
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════
# BOOT CRASH-LOOP DETECTION
# ════════════════════════════════════════════════════════════════════

_BOOT_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "boot_history.json")
_MAX_BOOTS_THRESHOLD = 3
_BOOT_WINDOW_SECONDS = 300  # 5 minutes


def _check_boot_safety() -> None:
    """Detect crash loops and auto-revert if needed.

    If the system has booted 3+ times in 5 minutes, it's likely
    a bad auto-merge caused a crash loop. Auto-revert to the
    previous commit and notify via Telegram.
    """
    os.makedirs(os.path.dirname(_BOOT_HISTORY_FILE), exist_ok=True)

    # Load boot history
    history: list[float] = []
    try:
        if os.path.exists(_BOOT_HISTORY_FILE):
            with open(_BOOT_HISTORY_FILE, "r") as f:
                history = json.load(f)
    except Exception:
        history = []

    now = time.time()
    recent = [t for t in history if now - t < _BOOT_WINDOW_SECONDS]

    if len(recent) >= _MAX_BOOTS_THRESHOLD:
        # ── CRASH LOOP DETECTED ──
        print(f"\n🚨 CRASH LOOP DETECTED: {len(recent)} boots in {_BOOT_WINDOW_SECONDS}s")
        print("Auto-reverting to previous commit...")

        try:
            import subprocess
            project_root = os.path.join(os.path.dirname(__file__), "..")
            result = subprocess.run(
                ["git", "revert", "HEAD", "--no-edit"],
                cwd=project_root,
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                print(f"✅ Auto-reverted: {result.stdout.strip()[:100]}")
            else:
                # If revert fails (merge conflict), hard reset
                subprocess.run(
                    ["git", "reset", "--hard", "HEAD~1"],
                    cwd=project_root,
                    capture_output=True, text=True, timeout=30,
                )
                print("✅ Hard reset to HEAD~1")
        except Exception as e:
            print(f"⚠️ Auto-revert failed: {e}")

        # Clear boot history to break the loop
        try:
            with open(_BOOT_HISTORY_FILE, "w") as f:
                json.dump([], f)
        except Exception:
            pass

        # Notify via Telegram (best effort, synchronous)
        try:
            from integrations.telegram_bot import send_alert
            asyncio.get_event_loop().run_until_complete(
                send_alert(
                    "🚨 *CRASH LOOP DETECTED*\n\n"
                    f"System booted {len(recent)}x in {_BOOT_WINDOW_SECONDS}s.\n"
                    "Auto-reverted to previous commit.\n"
                    "Manual review required."
                )
            )
        except Exception:
            pass

        return

    # Record this boot
    recent.append(now)
    try:
        with open(_BOOT_HISTORY_FILE, "w") as f:
            json.dump(recent, f)
    except Exception:
        pass


def main():
    """Entry point for the SelfEvolve system."""
    # Boot crash-loop detection — MUST be first
    _check_boot_safety()

    system = SelfEvolveSystem()

    # Handle graceful shutdown signals
    def signal_handler(sig, frame):
        print("\nReceived shutdown signal. Gracefully stopping...")
        system._running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the system
    asyncio.run(system.run())


if __name__ == "__main__":
    main()
