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

        # ── 2. Redis ──────────────────────────────────────────────
        try:
            redis = await get_redis_client()
            self.state_manager = StateManager(redis)
            self.event_bus = EventBus(redis)
            self.dead_man_switch = DeadManSwitch(redis)
            await logger.ainfo("redis_initialized")
        except Exception as e:
            await logger.aerror("redis_init_failed", error=str(e))

        # ── 3. Initialize State ───────────────────────────────────
        if self.state_manager:
            await self.state_manager.initialize_tranches()
            portfolio = await self.state_manager.get_portfolio_state()
            await logger.ainfo(
                "portfolio_initialized",
                equity=portfolio.total_equity,
                tranches=portfolio.available_tranches,
            )

        # ── 4. Start Event Bus ────────────────────────────────────
        if self.event_bus:
            self.event_bus.subscribe(
                EventChannels.ALERT_EVENTS,
                self._handle_alert,
            )
            await self.event_bus.start_listening()

        self._running = True
        await logger.ainfo("selfevolve_started", status="RUNNING")

    async def shutdown(self) -> None:
        """Graceful shutdown — preserve all state."""
        global logger
        if logger:
            await logger.ainfo("selfevolve_shutting_down")

        self._running = False

        # Stop event bus
        if self.event_bus:
            await self.event_bus.stop_listening()

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

                    # The main loop ticks every 60 seconds
                    # In production, this is where the schedule engine
                    # determines which phase to execute
                    await self._execute_phase()

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

    async def _execute_phase(self) -> None:
        """Determine and execute the current market phase."""
        # Placeholder: full schedule engine will use APScheduler
        # to trigger pre-market, trading, post-market, overnight phases
        pass

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
