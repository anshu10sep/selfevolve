"""
Morning Briefing DAG

Pre-market agent warm-up workflow.
Aggregates news, macro context, and portfolio state before the trading session.
"""

from __future__ import annotations

import structlog
from typing import TypedDict
from langgraph.graph import StateGraph, END

logger = structlog.get_logger(component="morning_briefing")


class BriefingState(TypedDict):
    """State for the morning briefing workflow."""
    market_context: str
    portfolio_status: str
    key_events: list[str]
    briefing_report: str
    step: str


async def gather_macro_node(state: BriefingState) -> BriefingState:
    logger.info("briefing_node", node="gather_macro")
    state["market_context"] = "Market regime is BULL with high volatility expected."
    state["step"] = "gather_macro"
    return state


async def gather_portfolio_node(state: BriefingState) -> BriefingState:
    logger.info("briefing_node", node="gather_portfolio")
    state["portfolio_status"] = "Total Equity: $100.00, Settled Cash: $100.00."
    state["step"] = "gather_portfolio"
    return state


async def gather_events_node(state: BriefingState) -> BriefingState:
    logger.info("briefing_node", node="gather_events")
    state["key_events"] = ["FOMC meeting at 14:00 ET", "CPI data release at 08:30 ET"]
    state["step"] = "gather_events"
    return state


async def compile_briefing_node(state: BriefingState) -> BriefingState:
    logger.info("briefing_node", node="compile_briefing")
    state["briefing_report"] = (
        f"Morning Briefing:\\n"
        f"Macro: {state.get('market_context')}\\n"
        f"Portfolio: {state.get('portfolio_status')}\\n"
        f"Events: {', '.join(state.get('key_events', []))}"
    )
    state["step"] = "compile_briefing"
    return state


def build_morning_briefing() -> StateGraph:
    workflow = StateGraph(BriefingState)

    workflow.add_node("gather_macro", gather_macro_node)
    workflow.add_node("gather_portfolio", gather_portfolio_node)
    workflow.add_node("gather_events", gather_events_node)
    workflow.add_node("compile_briefing", compile_briefing_node)

    # In reality, the first 3 can be parallelized.
    workflow.set_entry_point("gather_macro")
    
    workflow.add_edge("gather_macro", "gather_portfolio")
    workflow.add_edge("gather_portfolio", "gather_events")
    workflow.add_edge("gather_events", "compile_briefing")
    workflow.add_edge("compile_briefing", END)

    return workflow


def compile_morning_briefing():
    return build_morning_briefing().compile()
