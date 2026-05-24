"""
Jarvis Telegram Bot

Enables the system owner to interact with Jarvis via Telegram.
Supports status queries, portfolio checks, trading controls, and
receives real-time alerts on trades, errors, and evolution events.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import structlog
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

from config.settings import get_settings

logger = structlog.get_logger(component="telegram_bot")

# ── Module-level state ────────────────────────────────────────────
_app: Optional[Application] = None
_dashboard_url = "http://localhost:8000"


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _owner_only(func):
    """Decorator to restrict commands to the owner's chat_id."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = get_settings()
        if str(update.effective_chat.id) != str(settings.telegram_chat_id):
            await update.message.reply_text("⛔ Unauthorized.")
            return
        return await func(update, context)
    return wrapper


async def _api(path: str, method: str = "GET") -> Optional[dict]:
    """Call the Jarvis dashboard API."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if method == "POST":
                r = await c.post(f"{_dashboard_url}{path}")
            else:
                r = await c.get(f"{_dashboard_url}{path}")
            return r.json()
    except Exception as e:
        logger.error("telegram_api_call_failed", path=path, error=str(e))
        return None


def _fmt_currency(n: float) -> str:
    if abs(n) >= 1000:
        return f"${n:,.2f}"
    return f"${n:.2f}"


# ══════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════

@_owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Jarvis Command Center*\n\n"
        "I'm the autonomous trading system managing your portfolio\\.\n\n"
        "*Commands:*\n"
        "/status — System status & health\n"
        "/portfolio — Live portfolio from Alpaca\n"
        "/agents — All 17 agents with trust scores\n"
        "/roadmap — Evolution roadmap\n"
        "/bugs — Open bugs & issues\n"
        "/audit — Run system audit\n"
        "/pause — Pause trading\n"
        "/resume — Resume trading\n"
        "/help — Show this message",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@_owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await _api("/api/status")
    if not data:
        await update.message.reply_text("❌ Dashboard unreachable")
        return

    p = data.get("portfolio", {})
    equity = p.get("total_equity", 0)
    pnl = p.get("daily_pnl", 0)
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    phase = data.get("current_phase", "IDLE")
    status = data.get("status", "UNKNOWN")
    uptime = data.get("uptime_hours", 0)
    agents = data.get("agents", [])
    active = sum(1 for a in agents if a.get("status") == "ACTIVE")
    bugs = data.get("bugs", [])
    open_bugs = sum(1 for b in bugs if b.get("status") == "OPEN")

    msg = (
        f"📊 *Jarvis Status*\n\n"
        f"🔵 Status: *{status}*\n"
        f"⏱ Phase: `{phase}`\n"
        f"⏳ Uptime: `{uptime:.1f}h`\n\n"
        f"💰 Equity: *{_fmt_currency(equity)}*\n"
        f"{pnl_emoji} Daily P&L: *{_fmt_currency(pnl)}*\n\n"
        f"🤖 Agents: *{active}/{len(agents)}* active\n"
        f"🐛 Bugs: *{open_bugs}* open\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await _api("/api/portfolio")
    if not data:
        await update.message.reply_text("❌ Dashboard unreachable")
        return

    equity = data.get("total_equity", 0)
    cash = data.get("settled_cash", 0)
    bp = data.get("buying_power", 0)
    pnl = data.get("daily_pnl", 0)
    dd = data.get("drawdown_pct", 0)
    positions = data.get("positions", {})
    synced = data.get("last_synced", "?")

    msg = (
        f"💼 *Portfolio — Alpaca Paper*\n\n"
        f"💰 Equity: *{_fmt_currency(equity)}*\n"
        f"💵 Cash: *{_fmt_currency(cash)}*\n"
        f"🏦 Buying Power: *{_fmt_currency(bp)}*\n"
        f"📈 Daily P&L: *{_fmt_currency(pnl)}*\n"
        f"📉 Drawdown: `{dd:.1f}%`\n\n"
    )

    if positions:
        msg += f"📦 *Positions ({len(positions)}):*\n"
        for ticker, pos in positions.items():
            pnl_pos = pos.get("unrealized_pnl", 0)
            emoji = "🟢" if pnl_pos >= 0 else "🔴"
            msg += f"  {emoji} `{ticker}`: {pos.get('quantity', 0)} shares @ ${pos.get('avg_entry_price', 0):.2f} ({_fmt_currency(pnl_pos)})\n"
    else:
        msg += "📦 No open positions\n"

    msg += f"\n🔄 Last synced: `{synced[:19]}`"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await _api("/api/agents")
    if not data:
        await update.message.reply_text("❌ Dashboard unreachable")
        return

    agents = data.get("agents", [])
    type_emojis = {"EXECUTIVE": "👑", "MANAGER": "📋", "ANALYST": "🔬", "SPECIALIST": "⚡"}

    msg = f"🤖 *Agent Ecosystem ({len(agents)} agents)*\n\n"
    for a in agents:
        emoji = type_emojis.get(a.get("type", ""), "🔹")
        trust = a.get("trust_weight", 1.0)
        trust_bar = "🟢" if trust >= 0.8 else "🟡" if trust >= 0.5 else "🔴"
        brier = a.get("brier_score")
        brier_str = f"{brier:.2f}" if brier is not None else "—"
        msg += f"{emoji} *{a['name']}* {trust_bar} {trust*100:.0f}% | Brier: `{brier_str}`\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_roadmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await _api("/api/roadmap")
    if not data:
        await update.message.reply_text("❌ Dashboard unreachable")
        return

    tasks = data.get("tasks", [])[:8]
    total_h = data.get("total_estimated_hours", 0)
    p_emojis = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵", 5: "⚪"}

    msg = f"🗺 *Evolution Roadmap*\n`{len(data.get('tasks',[]))} tasks • {total_h:.0f}h estimated`\n\n"
    for t in tasks:
        p = t.get("priority", 5)
        msg += f"{p_emojis.get(p, '⚪')} *{t['title']}* ({t.get('category', '?')}) `{t.get('estimated_hours', 0)}h`\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_bugs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = await _api("/api/bugs/summary")
    if not data:
        await update.message.reply_text("❌ Dashboard unreachable")
        return

    msg = (
        f"🐛 *Bug Tracker*\n\n"
        f"📊 Total: *{data.get('total', 0)}*\n"
        f"🔴 Open: *{data.get('open', 0)}*\n"
        f"🟠 In Progress: *{data.get('in_progress', 0)}*\n"
        f"🟢 Resolved: *{data.get('resolved', 0)}*\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Running system audit...")
    data = await _api("/api/audit")
    if not data:
        await update.message.reply_text("❌ Audit failed")
        return

    readiness = data.get("readiness_score", 0) * 100
    files = data.get("total_files", 0)
    lines = data.get("total_lines", 0)
    findings = data.get("findings", [])
    critical = sum(1 for f in findings if f.get("severity") == "CRITICAL")
    high = sum(1 for f in findings if f.get("severity") == "HIGH")

    msg = (
        f"🔍 *System Audit*\n\n"
        f"✅ Readiness: *{readiness:.0f}%*\n"
        f"📁 Files: `{files}` | Lines: `{lines:,}`\n"
        f"🔴 Critical: *{critical}* | 🟠 High: *{high}*\n"
        f"📋 Total findings: *{len(findings)}*\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _api("/api/control/pause", method="POST")
    await update.message.reply_text("⏸ Trading *PAUSED*.", parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _api("/api/control/resume", method="POST")
    await update.message.reply_text("▶ Trading *RESUMED*.", parse_mode=ParseMode.MARKDOWN)


@_owner_only
async def cmd_fr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Submit a Feature Request — processed IMMEDIATELY by Gemini."""
    fr_text = " ".join(context.args) if context.args else ""
    if not fr_text:
        await update.message.reply_text(
            "📝 Usage: `/fr <description>`\n"
            "Example: `/fr add trailing stop loss to all trades`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.reply_text(
        f"📝 *FR Received*\n`{fr_text}`\n🔄 Processing...",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        settings = get_settings()
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.3,
        )

        status = await _api("/api/status") or {}
        response = await llm.ainvoke(
            f"You are Jarvis, CEO of SelfEvolve. Feature request from owner:\n\n"
            f"FR: {fr_text}\n\n"
            f"System: {status.get('status', 'RUNNING')}\n\n"
            f"Respond with:\n"
            f"1. FEASIBILITY: Easy/Medium/Hard\n"
            f"2. ASSIGNED_TO: which agent\n"
            f"3. PRIORITY: P1-P4\n"
            f"4. PLAN: 2-3 steps\n"
            f"5. ETA: time estimate\n"
            f"6. STATUS: what you're doing now"
        )

        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz
        fr_record = {
            "id": str(_uuid.uuid4()),
            "title": fr_text[:100],
            "status": "IN_PROGRESS",
            "created_at": _dt.now(_tz.utc).isoformat(),
        }
        from dashboard.api.main import system_state
        system_state.setdefault("feature_requests", []).append(fr_record)

        await update.message.reply_text(
            f"✅ *FR #{fr_record['id'][:8]}*\n\n{response.content[:800]}",
            parse_mode=None,
        )
        logger.info("feature_request", fr_id=fr_record["id"][:8], text=fr_text[:50])

    except Exception as e:
        await update.message.reply_text(f"❌ FR error: {str(e)[:100]}")


@_owner_only
async def cmd_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/crypto — Immediate crypto scan."""
    await update.message.reply_text("🪙 Scanning crypto NOW...")
    try:
        from integrations.crypto_data import CryptoDataClient, CryptoScreener
        cdc = CryptoDataClient()
        screener = CryptoScreener(cdc)
        candidates = await screener.screen_candidates(max_results=5)
        quotes = await cdc.get_latest_quotes()
        await cdc.close()

        if not candidates:
            btc = quotes.get("BTC/USD", {})
            eth = quotes.get("ETH/USD", {})
            await update.message.reply_text(
                f"📭 No strong signals\nBTC: ${btc.get('ask',0):,.2f} | ETH: ${eth.get('ask',0):,.2f}"
            )
            return

        msg = "🪙 *Crypto Scan*\n\n"
        for c in candidates[:5]:
            e = "🟢" if c["momentum_score"] > 0.3 else "🟡" if c["momentum_score"] > 0 else "🔴"
            msg += f"{e} `{c['ticker']:10s}` ${c['price']:>10,.2f} ({c['change_pct']:+.1f}%) m={c['momentum_score']:.2f}\n"
        btc = quotes.get("BTC/USD", {})
        eth = quotes.get("ETH/USD", {})
        msg += f"\nBTC: ${btc.get('ask',0):,.2f} | ETH: ${eth.get('ask',0):,.2f}"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:100]}")


@_owner_only
async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scan — Immediate stock scan."""
    await update.message.reply_text("🔍 Scanning stocks NOW...")
    try:
        from integrations.market_data import MarketDataClient
        from research.screener import StockScreener
        mdc = MarketDataClient()
        screener = StockScreener(mdc)
        candidates = await screener.screen_candidates(max_results=5)
        is_open = await mdc.is_market_open()
        await mdc.close()

        if not candidates:
            await update.message.reply_text(f"📭 No signals. Market: {'Open' if is_open else 'Closed'}")
            return

        msg = "📈 *Stock Scan*\n\n"
        for c in candidates[:5]:
            e = "🟢" if c["momentum_score"] > 0.3 else "🟡" if c["momentum_score"] > 0 else "🔴"
            msg += f"{e} `{c['ticker']:6s}` ${c['price']:>8.2f} ({c['change_pct']:+.1f}%) m={c['momentum_score']:.2f}\n"
        msg += f"\nMarket: {'🟢 Open' if is_open else '🔴 Closed'}"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)[:100]}")


@_owner_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Jarvis Command Center*\n\n"
        "*Trading:*\n"
        "/status — System health\n"
        "/portfolio — Live Alpaca portfolio\n"
        "/scan — Stock scan NOW\n"
        "/crypto — Crypto scan NOW\n"
        "/pause — Pause trading\n"
        "/resume — Resume trading\n\n"
        "*Company:*\n"
        "/agents — All agents\n"
        "/roadmap — Evolution roadmap\n"
        "/bugs — Bug tracker\n"
        "/fr <text> — Feature request (instant)\n"
        "/audit — System audit\n\n"
        "_Or just type any question!_",
        parse_mode=ParseMode.MARKDOWN,
    )



async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Free-form conversation with Jarvis via Gemini.
    
    Ask anything: strategies, agent roles, roadmap, trade analysis,
    company direction, debugging help, etc.
    """
    settings = get_settings()
    if str(update.effective_chat.id) != str(settings.telegram_chat_id):
        return

    user_msg = update.message.text.strip()
    if not user_msg:
        return

    await update.message.reply_text("🤔 Thinking...")

    try:
        # Gather live system context for Jarvis
        status_data = await _api("/api/status") or {}
        portfolio_data = await _api("/api/portfolio") or {}
        agents_data = await _api("/api/agents") or {}

        p = portfolio_data
        equity = p.get("total_equity", 0)
        cash = p.get("settled_cash", 0)
        pnl = p.get("daily_pnl", 0)
        positions = p.get("positions", {})

        agents_list = agents_data.get("agents", [])
        agent_summary = "\n".join(
            f"  - {a['name']} ({a.get('type','?')}): trust={a.get('trust_weight',1)*100:.0f}%, "
            f"brier={a.get('brier_score', 'N/A')}"
            for a in agents_list[:10]
        )

        pos_summary = "None" if not positions else "\n".join(
            f"  - {t}: {pos.get('quantity',0)} shares @ ${pos.get('avg_entry_price',0):.2f} "
            f"(P&L: ${pos.get('unrealized_pnl',0):.2f})"
            for t, pos in positions.items()
        )

        system_prompt = f"""You are Jarvis, the CEO and master AI of the SelfEvolve autonomous trading company.
You manage a team of 17 AI agents that analyze markets and trade stocks via Alpaca.

CURRENT SYSTEM STATE:
- Status: {status_data.get('status', 'RUNNING')}
- Phase: {status_data.get('current_phase', 'IDLE')}
- Uptime: {status_data.get('uptime_hours', 0):.1f}h

PORTFOLIO (Alpaca Paper Trading):
- Equity: ${equity:,.2f}
- Cash: ${cash:,.2f}
- Daily P&L: ${pnl:,.2f}
- Positions: {pos_summary}

AGENT TEAM:
{agent_summary}

TRADING SCHEDULE:
- 08:00 ET: Pre-market screening (momentum + volume)
- 09:30 ET: Market open — Gemini analysis + order submission ($10K tranches)
- 10:30 ET: Mid-morning intraday scan
- 12:30 ET: Midday intraday scan  
- 14:30 ET: Afternoon intraday scan
- 16:00 ET: Market close — P&L report
- 16:30 ET: Post-market evolution — audit + reflexion

TRADING STRATEGY:
- Screen top 20 liquid stocks for momentum + volume signals
- Gemini analyzes each candidate with price data, momentum score, recent bars
- $10K tranches per trade, max 5 concurrent positions
- Bracket orders with stop-loss and take-profit
- Max 3 new positions at open, 1 per intraday scan

COMPANY VISION:
- Self-evolving system that improves its own algorithms
- Agents have trust scores (Brier scores) that determine influence
- Underperforming agents get evolved, new strategies get A/B tested
- Goal: consistent alpha through autonomous research and adaptation

RULES:
1. Be concise but thorough (max 500 words)
2. Use emojis sparingly for readability
3. If asked about a specific agent, describe their role, goals, and current performance
4. If asked about strategy, explain the current approach and planned improvements
5. If asked to do something (change settings, pause trading), tell them the appropriate /command
6. Be honest about limitations — say what's built vs what's planned
"""

        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.7,
        )
        response = await llm.ainvoke(
            f"{system_prompt}\n\nOwner asks: {user_msg}"
        )

        reply = response.content

        # Telegram has a 4096 char limit
        if len(reply) > 4000:
            reply = reply[:3997] + "..."

        await update.message.reply_text(reply, parse_mode=None)
        logger.info("jarvis_chat", question=user_msg[:50], reply_len=len(reply))

    except Exception as e:
        logger.error("jarvis_chat_failed", error=str(e))
        await update.message.reply_text(
            f"❌ Sorry, I hit an error: `{str(e)[:100]}`\n\n"
            f"Try a /command instead, or ask again.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ══════════════════════════════════════════════════════════════════
# ALERT SYSTEM — called by other parts of the system
# ══════════════════════════════════════════════════════════════════

async def send_alert(message: str, parse_mode: str = ParseMode.MARKDOWN):
    """
    Send an alert message to the owner via Telegram.

    Call this from anywhere in the system:
        from integrations.telegram_bot import send_alert
        await send_alert("🚨 Trade executed: AAPL $10,000")
    """
    try:
        settings = get_settings()
        token = settings.telegram_bot_token
        chat_id = settings.telegram_chat_id
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                },
            )
        logger.info("telegram_alert_sent", length=len(message))
    except Exception as e:
        logger.error("telegram_alert_failed", error=str(e))


# ══════════════════════════════════════════════════════════════════
# LIFECYCLE
# ══════════════════════════════════════════════════════════════════

async def start_bot() -> Optional[Application]:
    """Start the Telegram bot (non-blocking, runs in background)."""
    global _app
    try:
        settings = get_settings()
        if not settings.telegram_bot_token:
            logger.warning("telegram_bot_disabled", reason="no token")
            return None

        _app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )

        # Register commands
        _app.add_handler(CommandHandler("start", cmd_start))
        _app.add_handler(CommandHandler("status", cmd_status))
        _app.add_handler(CommandHandler("portfolio", cmd_portfolio))
        _app.add_handler(CommandHandler("agents", cmd_agents))
        _app.add_handler(CommandHandler("roadmap", cmd_roadmap))
        _app.add_handler(CommandHandler("bugs", cmd_bugs))
        _app.add_handler(CommandHandler("audit", cmd_audit))
        _app.add_handler(CommandHandler("pause", cmd_pause))
        _app.add_handler(CommandHandler("resume", cmd_resume))
        _app.add_handler(CommandHandler("fr", cmd_fr))
        _app.add_handler(CommandHandler("crypto", cmd_crypto))
        _app.add_handler(CommandHandler("scan", cmd_scan))
        _app.add_handler(CommandHandler("help", cmd_help))
        _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Set bot commands menu
        await _app.bot.set_my_commands([
            BotCommand("status", "System status & health"),
            BotCommand("portfolio", "Live Alpaca portfolio"),
            BotCommand("scan", "Run stock scan NOW"),
            BotCommand("crypto", "Run crypto scan NOW"),
            BotCommand("agents", "All agents with trust scores"),
            BotCommand("fr", "Submit feature request (instant)"),
            BotCommand("roadmap", "Evolution roadmap"),
            BotCommand("bugs", "Bug tracker"),
            BotCommand("audit", "System audit"),
            BotCommand("pause", "Pause trading"),
            BotCommand("resume", "Resume trading"),
            BotCommand("help", "Show all commands"),
        ])

        # Initialize and start polling (non-blocking)
        await _app.initialize()
        await _app.start()
        await _app.updater.start_polling(drop_pending_updates=True)

        logger.info("telegram_bot_started", username=_app.bot.username)

        # Send startup notification
        await send_alert(
            "🟢 *Jarvis Online*\n\n"
            "Dashboard: `http://localhost:8000`\n"
            "Type /status for system health.",
        )

        return _app

    except Exception as e:
        logger.error("telegram_bot_start_failed", error=str(e))
        return None


async def stop_bot():
    """Stop the Telegram bot gracefully."""
    global _app
    if _app:
        try:
            await send_alert("🔴 *Jarvis shutting down*")
            await _app.updater.stop()
            await _app.stop()
            await _app.shutdown()
            logger.info("telegram_bot_stopped")
        except Exception as e:
            logger.error("telegram_bot_stop_failed", error=str(e))
        _app = None
