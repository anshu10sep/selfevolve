"""
Agent Messaging — Inter-agent communication for Jarvis.

Provides tools for Jarvis to send directives to subordinate agents
and query their health/status. Uses the existing agent infrastructure
(BaseAgent instances) and the persistence layer for agent scores.

This module is imported by Jarvis.__init__() to trigger @skill("master")
registration before BaseAgent._load_skills() runs.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Agent Registry (in-process singleton) ─────────────────────────
# Maps agent_name -> BaseAgent instance.
# Populated at startup by main.py or by Jarvis when it spawns agents.

_agent_registry: dict[str, Any] = {}


def register_agent_instance(name: str, agent: Any) -> None:
    """Register a live agent instance for inter-agent messaging.

    Called by main.py during startup to populate the registry.
    """
    _agent_registry[name.lower()] = agent
    logger.debug(f"Agent instance registered for messaging: {name}")


def get_registered_agents() -> dict[str, Any]:
    """Get all registered agent instances."""
    return dict(_agent_registry)


# ── LLM Tool-Calling Registration ─────────────────────────────────
from agents.skills.validator import skill


@skill("master")
def list_all_agents() -> str:
    """List all agents in the SelfEvolve hierarchy with their trust weights and status.
    Combines data from the agent_scores database table and the in-memory registry.
    Use this to see who is available and their performance.

    Returns:
        Formatted table of all agents with role, name, trust weight, Brier score, and status.
    """
    try:
        from persistence.db import get_agent_scores
        scores = get_agent_scores()
    except Exception as e:
        scores = []
        logger.warning(f"Could not fetch agent scores: {e}")

    if not scores and not _agent_registry:
        return "No agents registered yet. Use create_new_agent_file to create agents."

    lines = ["# Agent Roster", ""]
    lines.append("| Role | Name | Trust Weight | Brier Score | Live |")
    lines.append("|------|------|-------------|-------------|------|")

    # From DB scores
    seen_roles = set()
    for s in scores:
        role = s.get("role", "?")
        seen_roles.add(role.lower())
        name = s.get("name", role)
        tw = s.get("trust_weight", 1.0)
        brier = s.get("brier_score")
        brier_str = f"{brier:.4f}" if brier is not None else "—"
        live = "✅" if role.lower() in _agent_registry else "—"
        lines.append(f"| {role} | {name} | {tw:.3f} | {brier_str} | {live} |")

    # In-memory agents not in DB
    for name in _agent_registry:
        if name not in seen_roles:
            lines.append(f"| — | {name} | 1.000 | — | ✅ |")

    lines.append("")
    lines.append(f"**Total registered**: {len(scores)} (DB) + {len(_agent_registry)} (live)")
    return "\n".join(lines)


@skill("master")
def get_agent_trust_summary() -> str:
    """Get a detailed trust weight and Brier score summary for all scorable agents.
    Shows calibration quality (EXCELLENT/GOOD/FAIR/POOR) based on Brier thresholds.
    Use this for performance reviews and evolution decisions.

    Returns:
        Formatted trust summary with calibration ratings.
    """
    try:
        from evolution.trust_updater import get_trust_summary
        summary = get_trust_summary()
    except Exception as e:
        return f"Error fetching trust summary: {e}"

    if not summary:
        return "No trust data available yet. Agents need to make predictions first."

    lines = ["# Agent Trust Summary", ""]
    lines.append("| Role | Name | Trust | Brier | Calibration |")
    lines.append("|------|------|-------|-------|-------------|")

    for s in summary:
        role = s.get("role", "?")
        name = s.get("name", role)
        tw = s.get("trust_weight", 1.0)
        brier = s.get("brier_score")
        brier_str = f"{brier:.4f}" if brier is not None else "—"
        cal = s.get("calibration", "NO_DATA")
        cal_icon = {"EXCELLENT": "🟢", "GOOD": "🟡", "FAIR": "🟠", "POOR": "🔴", "NO_DATA": "⚪"}.get(cal, "⚪")
        lines.append(f"| {role} | {name} | {tw:.3f} | {brier_str} | {cal_icon} {cal} |")

    return "\n".join(lines)


@skill("master")
def get_evolution_history(limit: str = "10") -> str:
    """Get recent evolution events — trust weight changes, prompt promotions,
    agent spawns, system audits, etc.
    Use this to understand what the system has been doing recently.

    Args:
        limit: Maximum number of events to return (default "10").

    Returns:
        Formatted list of recent evolution events.
    """
    try:
        count = int(limit)
    except ValueError:
        count = 10

    try:
        from persistence.db import get_evolution_events
        events = get_evolution_events(limit=count)
    except Exception as e:
        return f"Error fetching evolution events: {e}"

    if not events:
        return "No evolution events recorded yet."

    lines = [f"# Recent Evolution Events (last {count})", ""]
    for evt in events:
        ts = evt.get("created_at", "?")
        etype = evt.get("event_type", "?")
        desc = evt.get("description", "")
        role = evt.get("agent_role", "")
        role_str = f" [{role}]" if role else ""
        lines.append(f"- **{etype}**{role_str} ({ts})")
        if desc:
            lines.append(f"  {desc[:150]}")

    return "\n".join(lines)


@skill("master")
def get_bug_status() -> str:
    """Get a summary of all bugs in the system — open, in-progress, resolved.
    Use this to understand what issues exist and their severity.

    Returns:
        Formatted bug summary with counts by status and severity.
    """
    try:
        from persistence.db import get_bug_summary, get_open_bugs_sorted
        summary = get_bug_summary()
        open_bugs = get_open_bugs_sorted()
    except Exception as e:
        return f"Error fetching bug data: {e}"

    lines = [
        "# Bug Status Summary",
        "",
        f"- **Total**: {summary.get('total', 0)}",
        f"- **Open**: {summary.get('open', 0)}",
        f"- **In Progress**: {summary.get('in_progress', 0)}",
        f"- **Resolved**: {summary.get('resolved', 0)}",
        f"- **Critical**: {summary.get('critical', 0)}",
        f"- **High**: {summary.get('high', 0)}",
        "",
    ]

    if open_bugs:
        lines.append("## Open Bugs (by severity)")
        for bug in open_bugs[:10]:
            sev = bug.get("severity", "?")
            title = bug.get("title", "?")
            sev_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev, "⚪")
            lines.append(f"- {sev_icon} **[{sev}]** {title[:100]}")
        if len(open_bugs) > 10:
            lines.append(f"- ... and {len(open_bugs) - 10} more")

    return "\n".join(lines)


@skill("master")
def get_recent_trades_summary(limit: str = "10") -> str:
    """Get a summary of recent trades — tickers, sides, PnL, and status.
    Use this to understand recent trading activity and performance.

    Args:
        limit: Maximum number of trades to return (default "10").

    Returns:
        Formatted list of recent trades.
    """
    try:
        count = int(limit)
    except ValueError:
        count = 10

    try:
        from persistence.db import get_recent_trades
        trades = get_recent_trades(limit=count)
    except Exception as e:
        return f"Error fetching trades: {e}"

    if not trades:
        return "No trades recorded yet."

    lines = [f"# Recent Trades (last {count})", ""]
    lines.append("| Ticker | Side | Notional | PnL | Status | Date |")
    lines.append("|--------|------|----------|-----|--------|------|")

    for t in trades:
        ticker = t.get("ticker", "?")
        side = t.get("side", "?")
        notional = t.get("notional", 0)
        pnl = t.get("realized_pnl")
        pnl_str = f"${pnl:.2f}" if pnl is not None else "—"
        status = t.get("status", "?")
        date = t.get("created_at", "?")[:10] if t.get("created_at") else "?"
        lines.append(f"| {ticker} | {side} | ${notional:.2f} | {pnl_str} | {status} | {date} |")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# GAP #5 — Task Delegation Tools
# ═══════════════════════════════════════════════════════════════════

@skill("master")
@skill("common")
def delegate_task_to_agent(agent_name: str, task: str) -> str:
    """Delegate a task to a specific sub-agent by name.
    The agent will process the task using its own LLM + tools and return
    a response. Use this to leverage specialized agent expertise.

    Args:
        agent_name: Name of the agent to delegate to (e.g., "CTO Agent", "cto", "developer").
        task: The task description or question for the agent.

    Returns:
        The agent's response, or an error message if the agent is not found.
    """
    import asyncio

    name_lower = agent_name.lower().replace(" ", "_")
    agent = _agent_registry.get(name_lower) or _agent_registry.get(agent_name.lower())

    if agent is None:
        available = ", ".join(sorted(_agent_registry.keys()))
        return f"❌ Agent '{agent_name}' not found. Available: {available or 'none'}"

    try:
        # Handle both sync and async contexts
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    lambda: asyncio.run(agent.invoke(task))
                ).result(timeout=120)
        else:
            result = asyncio.run(agent.invoke(task))

        # Extract text from response
        if isinstance(result, dict):
            content = result.get("content", str(result))
        elif hasattr(result, "content"):
            content = str(result.content)
        else:
            content = str(result)

        return f"📬 Response from {agent.name}:\n\n{content}"

    except Exception as e:
        return f"❌ Delegation to '{agent_name}' failed: {str(e)[:200]}"


@skill("master")
def broadcast_directive(directive: str, agent_roles: str) -> str:
    """Send a directive to multiple agents by role/name.
    Each specified agent will receive the directive independently.
    Use this for company-wide announcements or coordinated tasks.

    Args:
        directive: The message or task to broadcast to all specified agents.
        agent_roles: Comma-separated list of agent names/keys to target (e.g., "cto,cso,qa").

    Returns:
        Summary of which agents received the directive and any errors.
    """
    import asyncio

    roles = [r.strip().lower() for r in agent_roles.split(",") if r.strip()]
    if not roles:
        return "❌ No agent roles specified. Provide a comma-separated list."

    results = []
    for role_key in roles:
        agent = _agent_registry.get(role_key)
        if agent is None:
            results.append(f"❌ {role_key}: not found")
            continue

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(
                        lambda a=agent: asyncio.run(a.invoke(directive))
                    ).result(timeout=60)
            else:
                asyncio.run(agent.invoke(directive))

            results.append(f"✅ {role_key}: directive sent")
        except Exception as e:
            results.append(f"⚠️ {role_key}: {str(e)[:80]}")

    return f"📢 Broadcast to {len(roles)} agent(s):\n" + "\n".join(results)


# ═══════════════════════════════════════════════════════════════════
# GAP #7 — Event Bus Tools
# ═══════════════════════════════════════════════════════════════════

@skill("master")
def publish_event(channel: str, event_type: str, message: str) -> str:
    """Publish an event to the Event Bus for other agents and subsystems to react to.
    Use this to broadcast important information system-wide.

    Args:
        channel: Event channel name (e.g., "AGENT_INSIGHTS", "HEALTH_EVENTS", "TRADE_EVENTS").
        event_type: Type of event (e.g., "DIRECTIVE", "ALERT", "STATUS_UPDATE").
        message: The event message/data to publish.

    Returns:
        Confirmation that the event was published, or an error message.
    """
    import asyncio

    try:
        from core.event_bus import EventBus, EventChannels, Event
        from persistence.redis_client import get_redis_client

        # Map string channel to EventChannels enum
        channel_map = {
            "AGENT_INSIGHTS": EventChannels.AGENT_INSIGHTS,
            "TRADE_EVENTS": EventChannels.TRADE_EVENTS,
            "HEALTH_EVENTS": EventChannels.HEALTH_EVENTS,
            "EVOLUTION_EVENTS": EventChannels.EVOLUTION_EVENTS,
            "HITL_EVENTS": EventChannels.HITL_EVENTS,
        }

        channel_enum = channel_map.get(channel.upper())
        if channel_enum is None:
            return f"❌ Unknown channel '{channel}'. Available: {', '.join(channel_map.keys())}"

        async def _publish():
            redis = await get_redis_client()
            bus = EventBus(redis)
            event = Event(
                event_type=event_type,
                data={"message": message},
                source="jarvis",
            )
            await bus.publish(channel_enum, event)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(lambda: asyncio.run(_publish())).result(timeout=15)
        else:
            asyncio.run(_publish())

        return f"✅ Event published: [{event_type}] on {channel}"

    except Exception as e:
        return f"❌ Failed to publish event: {str(e)[:200]}"


@skill("master")
def get_event_bus_status() -> str:
    """Get the current status of the Event Bus — whether Redis is connected
    and which channels are active. Use this to diagnose communication issues.

    Returns:
        Status of the Event Bus connection and channel information.
    """
    try:
        from persistence.redis_client import get_redis_client
        import asyncio

        async def _check():
            redis = await get_redis_client()
            ping = await redis.ping()
            info = await redis.info("clients")
            return ping, info

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                ping, info = pool.submit(lambda: asyncio.run(_check())).result(timeout=10)
        else:
            ping, info = asyncio.run(_check())

        return (
            f"# Event Bus Status\n\n"
            f"- Redis connected: {'✅ Yes' if ping else '❌ No'}\n"
            f"- Connected clients: {info.get('connected_clients', '?')}\n"
            f"- Channels: AGENT_INSIGHTS, TRADE_EVENTS, HEALTH_EVENTS, "
            f"EVOLUTION_EVENTS, HITL_EVENTS\n"
            f"- Registered agents: {len(_agent_registry)}"
        )

    except Exception as e:
        return f"❌ Event Bus not available: {str(e)[:200]}"


# ═══════════════════════════════════════════════════════════════════
# GAP #8 — HITL Escalation Tool
# ═══════════════════════════════════════════════════════════════════

@skill("master")
def escalate_to_owner(message: str, severity: str, require_response: str) -> str:
    """Proactively send an alert to the system owner via Telegram.
    Use this for critical decisions, portfolio risk alerts, or system issues
    that need human attention.

    Args:
        message: The alert message to send to the owner.
        severity: Alert severity level ("LOW", "MEDIUM", "HIGH", "CRITICAL").
        require_response: Set to "true" to create a HITL approval request that
            blocks until the owner responds; "false" for a fire-and-forget alert.

    Returns:
        Confirmation of alert delivery, or the owner's response if require_response is true.
    """
    import asyncio

    severity_icons = {"LOW": "ℹ️", "MEDIUM": "⚠️", "HIGH": "🔴", "CRITICAL": "🚨"}
    icon = severity_icons.get(severity.upper(), "📢")

    # Fire-and-forget alert
    if require_response.lower() != "true":
        try:
            from integrations.telegram_bot import send_alert

            async def _send():
                alert_msg = f"{icon} *Jarvis Alert [{severity.upper()}]*\n\n{message}"
                await send_alert(alert_msg)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(lambda: asyncio.run(_send())).result(timeout=15)
            else:
                asyncio.run(_send())

            return f"✅ Alert sent to owner: [{severity.upper()}] {message[:100]}"

        except Exception as e:
            return f"⚠️ Telegram alert failed: {str(e)[:200]}. Message was: {message[:200]}"

    # HITL approval flow
    try:
        from core.hitl_gateway import hitl_gateway

        async def _hitl():
            request = await hitl_gateway.request_approval(
                ticker="SYSTEM",
                side="ALERT",
                notional=0,
                price=0,
                stop_loss=0,
                take_profit=0,
                confidence=0,
                trigger_reason=f"[{severity.upper()}] {message[:200]}",
                analysis=message,
            )
            resolved = await hitl_gateway.wait_for_resolution(request.id)
            return resolved

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                resolved = pool.submit(lambda: asyncio.run(_hitl())).result(timeout=120)
        else:
            resolved = asyncio.run(_hitl())

        status = resolved.status.value if hasattr(resolved.status, "value") else str(resolved.status)
        notes = resolved.human_notes or "No notes"
        return f"Owner response: {status} — {notes}"

    except Exception as e:
        return f"⚠️ HITL escalation failed: {str(e)[:200]}. Message was: {message[:200]}"
