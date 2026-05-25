"""
Agent Event Handlers

Bridges Event Bus events to agent invocations.
When trade/evolution/health events fire, these handlers
automatically trigger the appropriate agents:

- TRADE_CLOSED → Journaling Agent (document) + Auditor (audit) + VectorStore (learn)
- EVOLUTION_EVENTS → QA Agent (validate)
- HEALTH_DEGRADED → CTO Agent (diagnose) + CSO Agent (security scan)

All handlers are async and error-isolated — one handler failure
does NOT affect other handlers or the event bus.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(component="agent_event_handlers")


# ═══════════════════════════════════════════════════════════════════
# TRADE EVENT → AGENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def handle_trade_closed_for_agents(event: dict[str, Any]) -> None:
    """
    When a trade is closed, automatically:
    1. Document the trade via the Journaling Agent
    2. Audit the trade via the Auditor Agent
    3. Store the trade context in VectorStore for cross-agent learning
    4. Record outcome for evolution prediction tracking
    """
    event_type = event.get("event_type", "")
    if event_type != "TRADE_CLOSED":
        return

    data = event.get("data", {})
    trade_id = data.get("trade_id", "")
    ticker = data.get("ticker", "?")

    logger.info(
        "agent_handler_trade_closed",
        trade_id=trade_id[:8] if trade_id else "?",
        ticker=ticker,
    )

    # Run all tasks concurrently
    tasks = [
        _journal_trade(data),
        _audit_trade(data),
        _store_trade_outcome(data),
        _cro_risk_check(data),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            task_names = ["journal", "audit", "store_outcome", "cro_risk"]
            logger.error(
                f"agent_handler_{task_names[i]}_failed",
                trade_id=trade_id[:8],
                error=str(result),
            )


async def _journal_trade(data: dict) -> None:
    """Trigger the Journaling Agent to document a closed trade."""
    try:
        from core.llm_factory import get_efficient_llm
        from agents.journaling_agent import JournalingAgent

        llm = get_efficient_llm()
        agent = JournalingAgent(llm)

        await agent.document_trade(
            trade_id=data.get("trade_id", ""),
            ticker=data.get("ticker", ""),
            action=data.get("action", "CLOSE"),
            debate_state={
                "bull_argument": data.get("bull_argument", ""),
                "bear_argument": data.get("bear_argument", ""),
                "net_conviction": data.get("net_conviction", 0),
            },
            analyst_scores=data.get("analyst_scores", {}),
            judge_reasoning=data.get("close_reason", ""),
            market_context=data.get("market_context", {}),
        )

        logger.info("trade_journaled", trade_id=data.get("trade_id", "")[:8])
    except Exception as e:
        logger.error("journal_trade_failed", error=str(e))


async def _audit_trade(data: dict) -> None:
    """Trigger the Auditor Agent to audit a closed trade."""
    try:
        from core.llm_factory import get_efficient_llm
        from agents.auditor_agent import AuditorAgent

        llm = get_efficient_llm()
        agent = AuditorAgent(llm)

        await agent.audit_trade(
            trade_id=data.get("trade_id", ""),
            ticker=data.get("ticker", ""),
            action=data.get("action", "CLOSE"),
            amount=abs(data.get("pnl", 0)),
            portfolio_state={
                "available_cash": data.get("available_cash", 0),
                "unsettled_proceeds": data.get("unsettled_proceeds", 0),
                "pending_settlements": data.get("pending_settlements", 0),
                "open_positions": data.get("open_positions", 0),
                "gfv_strikes": data.get("gfv_strikes", 0),
                "account_type": "cash",
            },
        )

        logger.info("trade_audited", trade_id=data.get("trade_id", "")[:8])
    except Exception as e:
        logger.error("audit_trade_failed", error=str(e))


async def _store_trade_outcome(data: dict) -> None:
    """Store the trade outcome in VectorStore for cross-agent learning."""
    try:
        from memory.vector_store import get_vector_store
        vs = get_vector_store()

        await vs.store_trade_context(
            trade_id=data.get("trade_id", ""),
            ticker=data.get("ticker", ""),
            action=data.get("action", "CLOSE"),
            context_text=(
                f"Trade closed: {data.get('ticker', '?')} "
                f"PnL: ${data.get('pnl', 0):.2f} "
                f"({data.get('close_reason', 'unknown reason')})"
            ),
            analyst_scores=data.get("analyst_scores", {}),
            debate_summary=data.get("debate_summary", ""),
            judge_reasoning=data.get("close_reason", ""),
            market_regime=data.get("market_regime", "UNKNOWN"),
            outcome="win" if data.get("profitable", False) else "loss",
            pnl=data.get("pnl", 0),
        )

        logger.info(
            "trade_outcome_stored",
            trade_id=data.get("trade_id", "")[:8],
            outcome="win" if data.get("profitable", False) else "loss",
        )
    except Exception as e:
        logger.error("store_trade_outcome_failed", error=str(e))

async def _cro_risk_check(data: dict) -> None:
    """Trigger the CRO Agent to assess risk after a trade closes."""
    try:
        from core.llm_factory import get_premium_llm
        from agents.cro_agent import CroAgent
        from persistence.db import get_recent_trades
        from core.state_manager import StateManager
        from persistence.redis_client import get_redis_client
        
        redis = await get_redis_client()
        sm = StateManager(redis)
        portfolio = await sm.get_portfolio_state()
        recent = get_recent_trades(limit=10)
        
        llm = get_premium_llm()
        agent = CroAgent(llm)
        
        # We invoke assess_portfolio_risk
        report = await agent.assess_portfolio_risk(
            portfolio_state=portfolio.model_dump() if hasattr(portfolio, "model_dump") else portfolio,
            strategy_allocations={},
            recent_trades=recent,
        )
        
        logger.info("cro_risk_assessed", risk_level=report.get("overall_risk_level", "UNKNOWN"))
        
        # Publish alert if halt recommended
        if report.get("halt_recommended", False):
            from core.event_bus import EventBus, EventChannels, Event
            bus = EventBus(redis)
            await bus.publish(EventChannels.HEALTH_EVENTS, Event(
                event_type="CIRCUIT_BREAKER_TRIPPED",
                data={"severity": "CRITICAL", "message": "CRO recommends trading halt.", "report": report},
                source="cro_agent"
            ))
            
    except Exception as e:
        logger.error("cro_risk_check_failed", error=str(e))


# ═══════════════════════════════════════════════════════════════════
# EVOLUTION EVENT → AGENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def handle_evolution_for_agents(event: dict[str, Any]) -> None:
    """
    When a Shadow Crew prompt is promoted or discarded,
    trigger QA validation and store the outcome in VectorStore.
    """
    event_type = event.get("event_type", "")
    data = event.get("data", {})

    if event_type not in ("SHADOW_PROMOTED", "SHADOW_DISCARDED"):
        return

    logger.info(
        "agent_handler_evolution_event",
        event_type=event_type,
        agent_role=data.get("agent_role", "?"),
    )

    # Store the evolution outcome in VectorStore
    try:
        from memory.vector_store import get_vector_store
        vs = get_vector_store()

        status = "PROMOTED" if event_type == "SHADOW_PROMOTED" else "DISCARDED"
        agent_role = data.get("agent_role", "")
        version = data.get("version", 0)

        await vs.store_rule_evolution(
            agent_role=agent_role,
            version=version,
            nuance_text=data.get("nuance_text", ""),
            change_description=f"Shadow test result: {status}",
            brier_before=data.get("prod_brier", 0),
            brier_after=data.get("shadow_brier"),
            status=status,
        )

        logger.info(
            "evolution_outcome_stored",
            agent_role=agent_role,
            version=version,
            status=status,
        )
    except Exception as e:
        logger.error("evolution_outcome_storage_failed", error=str(e))

    # Trigger QA validation if a prompt was promoted
    if event_type == "SHADOW_PROMOTED":
        try:
            from core.llm_factory import get_efficient_llm
            from agents.qa_agent import QaAgent

            llm = get_efficient_llm()
            qa = QaAgent(llm)

            await qa.validate_agent_output(
                agent_name=data.get("agent", data.get("agent_role", "")),
                agent_role=data.get("agent_role", ""),
                output={
                    "event": "prompt_promoted",
                    "version": data.get("version"),
                    "p_value": data.get("p_value"),
                    "shadow_brier": data.get("shadow_brier"),
                    "prod_brier": data.get("prod_brier"),
                },
                expected_schema="EvolutionEvent",
            )

            logger.info("qa_validated_promotion", agent_role=data.get("agent_role", ""))
        except Exception as e:
            logger.error("qa_validation_failed", error=str(e))


# ═══════════════════════════════════════════════════════════════════
# HEALTH EVENT → AGENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

async def handle_health_for_agents(event: dict[str, Any]) -> None:
    """
    When system health degrades, trigger CTO diagnosis.
    If CRITICAL, also trigger CSO security scan.
    """
    event_type = event.get("event_type", "")
    data = event.get("data", {})
    status = data.get("status", "")

    if status not in ("DEGRADED", "CRITICAL"):
        return

    logger.info(
        "agent_handler_health_event",
        status=status,
        component=data.get("component", "?"),
    )

    # CTO health assessment
    try:
        from core.llm_factory import get_efficient_llm
        from agents.cto_agent import CtoAgent

        llm = get_efficient_llm()
        cto = CtoAgent(llm)

        await cto.assess_system_health(
            agent_health_data={
                "trigger": event_type,
                "affected_component": data.get("component", "unknown"),
                "reason": data.get("reason", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            infra_metrics=data.get("metrics", {}),
        )

        logger.info("cto_health_assessment_triggered")
    except Exception as e:
        logger.error("cto_assessment_failed", error=str(e))

    # CSO security scan on CRITICAL
    if status == "CRITICAL":
        try:
            from core.llm_factory import get_efficient_llm
            from agents.cso_agent import CsoAgent

            llm = get_efficient_llm()
            cso = CsoAgent(llm)

            await cso.run_security_scan(
                agent_outputs={
                    "health_event": data,
                    "trigger": "CRITICAL health event",
                },
            )

            logger.info("cso_security_scan_triggered")
        except Exception as e:
            logger.error("cso_scan_failed", error=str(e))


# ═══════════════════════════════════════════════════════════════════
# REGISTRATION HELPER
# ═══════════════════════════════════════════════════════════════════

def register_agent_event_handlers(event_bus) -> None:
    """
    Register all agent event handlers with the Event Bus.
    Call this during system startup in main.py.

    Args:
        event_bus: The EventBus instance to register handlers with
    """
    from core.event_bus import EventChannels

    event_bus.subscribe(EventChannels.TRADE_EVENTS, handle_trade_closed_for_agents)
    event_bus.subscribe(EventChannels.EVOLUTION_EVENTS, handle_evolution_for_agents)
    event_bus.subscribe(EventChannels.HEALTH_EVENTS, handle_health_for_agents)

    logger.info(
        "agent_event_handlers_registered",
        handlers=[
            "trade_closed → journaling + auditor + vector_store",
            "evolution → qa_validation + rule_storage",
            "health → cto_diagnosis + cso_scan",
        ],
    )
