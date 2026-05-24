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

        # Start Hot Reloader (watches for code changes)
        try:
            from evolution.hot_reloader import hot_reloader
            hot_reload_task = asyncio.create_task(hot_reloader.watch_loop())
        except Exception as e:
            hot_reload_task = None
            if logger:
                await logger.awarning("hot_reloader_init_failed", error=str(e))

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
            if hot_reload_task:
                hot_reload_task.cancel()
            await self.shutdown()

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

        # ── CRYPTO 24/7 — scans every 4 hours, 7 days/week ────────
        for hour in [0, 4, 8, 12, 16, 20]:
            self.scheduler.add_job(
                self._run_crypto_scan,
                CronTrigger(hour=hour, minute=15),
                id=f'crypto_scan_{hour:02d}',
            )

        # ── CONTINUOUS EVOLUTION — every 6 hours, 7 days/week ──────
        self.scheduler.add_job(
            self._run_continuous_evolution,
            CronTrigger(hour='1,7,13,19', minute=0),
            id='continuous_evolution',
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
            from broker.alpaca_client import AlpacaClient
            llm = get_premium_llm()
            alpaca = AlpacaClient()

            for candidate in candidates[:3]:  # Max 3 trades per day
                ticker = candidate["ticker"]
                try:
                    # Get fresh quote
                    from integrations.market_data import MarketDataClient as MDC2
                    mdc2 = MDC2()
                    quote = await mdc2.get_latest_quote(ticker)
                    current_price = quote.get("ask", candidate.get("price", 0))
                    bars = await mdc2.get_bars(ticker, timeframe="1Day", limit=10)
                    await mdc2.close()

                    # Build context for LLM
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
                    analysis = response.content

                    if logger:
                        await logger.ainfo("trade_analysis", ticker=ticker, analysis=analysis[:200])

                    # Parse and execute
                    if "ACTION: BUY" in analysis.upper():
                        # Parse stop loss and take profit
                        sl_pct = 2.0
                        tp_pct = 5.0
                        for line in analysis.split("\n"):
                            if "STOP_LOSS_PCT" in line.upper():
                                try: sl_pct = float(line.split(":")[-1].strip().replace("%", ""))
                                except: pass
                            if "TAKE_PROFIT_PCT" in line.upper():
                                try: tp_pct = float(line.split(":")[-1].strip().replace("%", ""))
                                except: pass

                        # Submit real order — $10K tranche (paper account)
                        from core.models.portfolio import TradeIntent, TradeSide
                        import uuid
                        tranche_size = 10000.0  # $10K per tranche

                        intent = TradeIntent(
                            ticker=ticker,
                            side=TradeSide.BUY,
                            notional=tranche_size,
                            stop_loss_price=round(current_price * (1 - sl_pct / 100), 2),
                            take_profit_price=round(current_price * (1 + tp_pct / 100), 2),
                            client_order_id=str(uuid.uuid4()),
                        )

                        order = await alpaca.submit_bracket_order(intent)
                        order_id = order.get("id", "?")

                        await send_alert(
                            f"🎯 *ORDER SUBMITTED: {ticker}*\n\n"
                            f"💰 Amount: *$10,000*\n"
                            f"📈 Price: *${current_price:.2f}*\n"
                            f"🛡 Stop Loss: *${intent.stop_loss_price:.2f}* (-{sl_pct}%)\n"
                            f"🎯 Take Profit: *${intent.take_profit_price:.2f}* (+{tp_pct}%)\n"
                            f"🔖 Order ID: `{order_id[:8]}`\n\n"
                            f"```\n{analysis[:250]}\n```"
                        )
                    else:
                        await send_alert(
                            f"⏭ *Skip: {ticker}*\n"
                            f"```\n{analysis[:200]}\n```"
                        )

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

            from core.llm_factory import get_premium_llm
            from broker.alpaca_client import AlpacaClient
            llm = get_premium_llm()
            alpaca = AlpacaClient()

            mdc2 = MarketDataClient()
            quote = await mdc2.get_latest_quote(ticker)
            current_price = quote.get("ask", candidate.get("price", 0))
            await mdc2.close()

            response = await llm.ainvoke(
                f"Intraday opportunity scan. Analyze {ticker} at ${current_price:.2f}. "
                f"Momentum: {candidate.get('momentum_score', 0):.2f}, "
                f"Change: {candidate.get('change_pct', 0):.1f}%. "
                f"Should we BUY or PASS? Format: ACTION: BUY/PASS, CONFIDENCE: 1-10, REASONING: one line, "
                f"STOP_LOSS_PCT: number, TAKE_PROFIT_PCT: number"
            )
            analysis = response.content

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
                    ticker=ticker,
                    side=TradeSide.BUY,
                    notional=10000.0,
                    stop_loss_price=round(current_price * (1 - sl_pct / 100), 2),
                    take_profit_price=round(current_price * (1 + tp_pct / 100), 2),
                    client_order_id=str(uuid.uuid4()),
                )
                order = await alpaca.submit_bracket_order(intent)

                await send_alert(
                    f"📊 *INTRADAY ORDER: {ticker}*\n\n"
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
            analysis = response.content

            if "ACTION: BUY" in analysis.upper():
                from broker.alpaca_client import AlpacaClient
                from core.models.portfolio import TradeIntent, TradeSide
                import uuid

                sl_pct, tp_pct = 4.0, 8.0  # Wider for crypto
                for line in analysis.split("\n"):
                    if "STOP_LOSS_PCT" in line.upper():
                        try: sl_pct = float(line.split(":")[-1].strip().replace("%", ""))
                        except: pass
                    if "TAKE_PROFIT_PCT" in line.upper():
                        try: tp_pct = float(line.split(":")[-1].strip().replace("%", ""))
                        except: pass

                alpaca = AlpacaClient()
                intent = TradeIntent(
                    ticker=ticker.replace("/", ""),  # Alpaca uses BTCUSD not BTC/USD for orders
                    side=TradeSide.BUY,
                    notional=5000.0,  # $5K tranches for crypto (higher vol)
                    stop_loss_price=round(current_price * (1 - sl_pct / 100), 2),
                    take_profit_price=round(current_price * (1 + tp_pct / 100), 2),
                    client_order_id=str(uuid.uuid4()),
                )
                order = await alpaca.submit_bracket_order(intent)
                await alpaca.close()

                await send_alert(
                    f"🪙 *CRYPTO ORDER: {ticker}*\n\n"
                    f"💰 $5,000 @ ${current_price:,.2f}\n"
                    f"🛡 SL: -${sl_pct}% | TP: +{tp_pct}%\n"
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

            # 2. Run system audit
            from agents.skills.jarvis.system_audit import SystemAuditor
            auditor = SystemAuditor()
            audit = auditor.run_audit()
            readiness = audit.get("readiness_score", 0) * 100

            # 3. Ask Gemini to analyze and suggest improvements
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

            report = response.content

            await send_alert(
                f"🧬 *Evolution Report*\n\n"
                f"⏰ Cycle: {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"
                f"📊 Readiness: `{readiness:.0f}%`\n"
                f"📈 Strategies tested: {len(backtest_results)}\n\n"
                f"{report[:500]}"
            )

            system_state["current_phase"] = "IDLE"
            if logger: await logger.ainfo("continuous_evolution_complete")

        except Exception as e:
            if logger: await logger.aerror("continuous_evolution_failed", error=str(e))

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
