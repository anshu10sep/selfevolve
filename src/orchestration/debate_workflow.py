"""
Debate Workflow

Parallel Bull/Bear debate sub-graph.
Executes the debate phase where Bull and Bear agents construct theses
and the Judge agent evaluates them.
"""

from __future__ import annotations

import structlog
from typing import TypedDict
from langgraph.graph import StateGraph, END

logger = structlog.get_logger(component="debate_workflow")


class DebateState(TypedDict):
    """State for the debate workflow."""
    ticker: str
    market_data: dict
    bull_thesis: str
    bear_thesis: str
    bull_score: float
    bear_score: float
    judge_decision: dict
    step: str


async def bull_node(state: DebateState) -> DebateState:
    logger.info("debate_node", node="bull", ticker=state["ticker"])
    state["bull_thesis"] = "Strong technical breakout and positive sentiment."
    state["step"] = "bull"
    return state


async def bear_node(state: DebateState) -> DebateState:
    logger.info("debate_node", node="bear", ticker=state["ticker"])
    state["bear_thesis"] = "Macro headwinds and overextended valuation."
    state["step"] = "bear"
    return state


async def judge_node(state: DebateState) -> DebateState:
    logger.info("debate_node", node="judge", ticker=state["ticker"])
    state["bull_score"] = 7.5
    state["bear_score"] = 6.0
    state["judge_decision"] = {
        "action": "BUY",
        "confidence": 7.0,
        "reasoning": "Bull thesis outweighs bear thesis due to strong technicals.",
    }
    state["step"] = "judge"
    return state


def build_debate_workflow() -> StateGraph:
    workflow = StateGraph(DebateState)

    workflow.add_node("bull", bull_node)
    workflow.add_node("bear", bear_node)
    workflow.add_node("judge", judge_node)

    # Note: Bull and Bear can run in parallel in a real implementation
    # LangGraph supports parallel execution. Here we sequentialize them for simplicity
    # or rely on an aggregator node.
    workflow.set_entry_point("bull")
    
    workflow.add_edge("bull", "bear")
    workflow.add_edge("bear", "judge")
    workflow.add_edge("judge", END)

    return workflow


def compile_debate_workflow():
    return build_debate_workflow().compile()
