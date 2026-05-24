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
import signal
import sys
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

            # ── 4. Start Event Bus ───────────────────────────────
            self.event_bus.subscribe(
                EventChannels.ALERT_EVENTS,
                self._handle_alert,
            )
            await self.event_bus.start_listening()
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

        # ── 6. Start Scheduler ────────────────────────────────────
        self._setup_schedule()
        self.scheduler.start()
        await logger.ainfo("scheduler_started")

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

        # Start Settlement Checker
        settlement_task = asyncio.create_task(self._settlement_check_loop())

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
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            pass
        finally:
            api_task.cancel()
            overwatch_task.cancel()
            settlement_task.cancel()
            await self.shutdown()

    def _setup_schedule(self) -> None:
        """Setup APScheduler with market hours logic."""
        # Note: ET times converted to UTC for scheduler (assuming ET = UTC-5 standard, simplified)
        self.scheduler.add_job(
            self._run_pre_market,
            CronTrigger(day_of_week='mon-fri', hour=13, minute=0),
            id='pre_market',
        )
        self.scheduler.add_job(
            self._run_market_open,
            CronTrigger(day_of_week='mon-fri', hour=14, minute=30),
            id='market_open',
        )
        self.scheduler.add_job(
            self._run_market_close,
            CronTrigger(day_of_week='mon-fri', hour=21, minute=0),
            id='market_close',
        )
        self.scheduler.add_job(
            self._run_post_market_evolution,
            CronTrigger(day_of_week='mon-fri', hour=21, minute=30),
            id='post_market',
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

            # Screen for candidates
            mdc = MarketDataClient()
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
        """Market open: Run trading DAG on pre-screened candidates."""
        global logger
        if logger: await logger.ainfo("phase_started", phase="MARKET_OPEN")

        try:
            from integrations.telegram_bot import send_alert
            from dashboard.api.main import system_state
            system_state["current_phase"] = "MARKET_OPEN"

            await send_alert("🔔 *Market Open*\nTrading engine active.")

            # Check if market is actually open
            from integrations.market_data import MarketDataClient
            mdc = MarketDataClient()
            is_open = await mdc.is_market_open()
            await mdc.close()

            if not is_open:
                await send_alert("⏸ Market is closed today. Skipping trading.")
                return

            # Get today's candidates from pre-market
            candidates = system_state.get("today_candidates", [])
            if not candidates:
                await send_alert("📭 No candidates to trade today.")
                return

            # Run trading analysis via Gemini for each candidate
            from core.llm_factory import get_premium_llm
            llm = get_premium_llm()

            for candidate in candidates[:3]:  # Max 3 trades per day
                ticker = candidate["ticker"]
                try:
                    # Get LLM analysis
                    prompt = (
                        f"You are a professional stock analyst. Analyze {ticker} for a day trade.\n"
                        f"Current data: price=${candidate.get('price', 0):.2f}, "
                        f"momentum_score={candidate.get('momentum_score', 0):.2f}, "
                        f"volume={candidate.get('volume', 0):,}\n\n"
                        f"Should we BUY, HOLD, or PASS? Respond with:\n"
                        f"ACTION: BUY/HOLD/PASS\n"
                        f"CONFIDENCE: 1-10\n"
                        f"REASONING: one sentence\n"
                        f"STOP_LOSS_PCT: suggested stop loss percentage (e.g. 2.0)\n"
                        f"TAKE_PROFIT_PCT: suggested take profit percentage (e.g. 5.0)"
                    )
                    response = await llm.ainvoke(prompt)
                    analysis = response.content

                    # Log the analysis
                    if logger:
                        await logger.ainfo(
                            "trade_analysis",
                            ticker=ticker,
                            analysis=analysis[:200],
                        )

                    # Parse action (DRY RUN — log but don't execute)
                    if "ACTION: BUY" in analysis.upper():
                        await send_alert(
                            f"🎯 *Trade Signal: {ticker}*\n"
                            f"Action: BUY (DRY RUN)\n"
                            f"```\n{analysis[:300]}\n```\n\n"
                            f"_Dry run mode — no order submitted_"
                        )
                    else:
                        await send_alert(
                            f"⏭ *Skip: {ticker}*\n"
                            f"```\n{analysis[:200]}\n```"
                        )

                except Exception as e:
                    if logger: await logger.aerror("trade_analysis_failed", ticker=ticker, error=str(e))

            if logger: await logger.ainfo("market_open_complete")

        except Exception as e:
            if logger: await logger.aerror("market_open_failed", error=str(e))

    async def _run_market_close(self) -> None:
        """Market close: Journal results, update portfolio."""
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

            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            await send_alert(
                f"🔔 *Market Close*\n\n"
                f"💰 Equity: *${equity:,.2f}*\n"
                f"{pnl_emoji} Daily P&L: *${pnl:,.2f}*\n"
                f"📦 Open positions: *{len(positions)}*"
            )

            if logger: await logger.ainfo("market_close_complete", equity=equity, pnl=pnl)

        except Exception as e:
            if logger: await logger.aerror("market_close_failed", error=str(e))

    async def _run_post_market_evolution(self) -> None:
        """Post-market: Run reflexion, update agent trust, generate reports."""
        global logger
        if logger: await logger.ainfo("phase_started", phase="POST_MARKET_EVOLUTION")

        try:
            from integrations.telegram_bot import send_alert
            from dashboard.api.main import system_state
            system_state["current_phase"] = "EVOLUTION"

            await send_alert("🧬 *Post-Market Evolution*\nRunning reflexion and analysis...")

            # Run system audit
            from agents.skills.jarvis.system_audit import SystemAuditor
            auditor = SystemAuditor()
            audit = auditor.run_audit()
            readiness = audit.get("readiness_score", 0) * 100

            # Run evolution analysis via Gemini
            from core.llm_factory import get_efficient_llm
            llm = get_efficient_llm()

            p = system_state.get("portfolio", {})
            response = await llm.ainvoke(
                f"You are Jarvis, an autonomous trading system. Today's results:\n"
                f"- Equity: ${p.get('total_equity', 0):,.2f}\n"
                f"- Daily P&L: ${p.get('daily_pnl', 0):,.2f}\n"
                f"- Positions: {len(p.get('positions', {}))}\n"
                f"- System readiness: {readiness:.0f}%\n\n"
                f"Write a brief end-of-day report (3-4 sentences). "
                f"Include what went well, what to improve, and tomorrow's focus."
            )

            report = response.content
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
        while self._running:
            try:
                if self.dead_man_switch:
                    await self.dead_man_switch.write_heartbeat()
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


def main():
    """Entry point for the SelfEvolve system."""
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
