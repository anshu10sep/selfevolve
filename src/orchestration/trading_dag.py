"""
Main Trading DAG

The core trading workflow implemented as a LangGraph Directed Acyclic Graph.
This is the production execution pipeline:

    Market Trigger → Regime Check → Parallel Research → Aggregation
    → Bull/Bear Debate → Judge Decision → Guardrail Validation
    → HITL Checkpoint → Alpaca Execution

All routing is DETERMINISTIC Python. LLMs act as nodes that perform
specific analysis — they do NOT decide routing logic.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict, Annotated, Optional
from datetime import datetime, timezone

import structlog
from langgraph.graph import StateGraph, END

from core.models.signals import (
    ConvictionScore,
    DebateState,
    ExecutionOrder,
    ExecutionAction,
    AggregatedResearch,
    MarketRegime,
    RegimeType,
)
from core.models.portfolio import PortfolioState
from config.constants import JUDGE_MIN_CONFIDENCE_FOR_EXECUTION

logger = structlog.get_logger(component="trading_dag")


# ════════════════════════════════════════════════════════════════════
# STATE DEFINITION
# ════════════════════════════════════════════════════════════════════

class TradingState(TypedDict):
    """State that flows through the trading DAG."""
    ticker: str
    regime: dict
    portfolio: dict
    fundamental_score: dict
    technical_score: dict
    sentiment_score: dict
    macro_score: dict
    aggregated_research: dict
    debate_state: dict
    execution_order: dict
    guardrail_result: str
    hitl_action: str
    trade_result: dict
    error: str
    step: str


# ════════════════════════════════════════════════════════════════════
# NODE FUNCTIONS
# ════════════════════════════════════════════════════════════════════

async def regime_check_node(state: TradingState) -> TradingState:
    """
    Deterministic regime classification.
    No LLM — pure Python using VIX and macro data.
    """
    logger.info("node_executing", node="regime_check", ticker=state["ticker"])

    # Default to normal regime — will be overridden by real data feeds
    regime = {
        "regime": "SIDEWAYS",
        "vix_level": 15.0,
        "position_size_modifier": 1.0,
    }
    state["regime"] = regime
    state["step"] = "regime_check"
    return state


async def parallel_research_node(state: TradingState) -> TradingState:
    """
    Parallel research from all four analyst agents.
    
    In production, each analyst runs concurrently via asyncio.gather().
    """
    logger.info("node_executing", node="parallel_research", ticker=state["ticker"])

    # These would be real agent invocations in production
    # For now, create placeholder scores that the agents will fill
    state["fundamental_score"] = {
        "agent_id": "fundamental", "ticker": state["ticker"],
        "score": 0.0, "confidence": 0.0, "rationale": "Awaiting analysis"
    }
    state["technical_score"] = {
        "agent_id": "technical", "ticker": state["ticker"],
        "score": 0.0, "confidence": 0.0, "rationale": "Awaiting analysis"
    }
    state["sentiment_score"] = {
        "agent_id": "sentiment", "ticker": state["ticker"],
        "score": 0.0, "confidence": 0.0, "rationale": "Awaiting analysis"
    }
    state["macro_score"] = {
        "agent_id": "macro", "ticker": state["ticker"],
        "score": 0.0, "confidence": 0.0, "rationale": "Awaiting analysis"
    }
    state["step"] = "parallel_research"
    return state


async def aggregation_node(state: TradingState) -> TradingState:
    """
    Deterministic Python aggregator.
    
    Calculates trust-weighted average conviction score.
    This is NOT an LLM — it's pure math.
    """
    logger.info("node_executing", node="aggregation", ticker=state["ticker"])

    scores = {
        "fundamental": state.get("fundamental_score", {}),
        "technical": state.get("technical_score", {}),
        "sentiment": state.get("sentiment_score", {}),
        "macro": state.get("macro_score", {}),
    }

    # Default weights (updated from trust_weights DB in production)
    weights = {
        "fundamental": 1.0,
        "technical": 1.0,
        "sentiment": 0.8,
        "macro": 0.9,
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for domain, score_data in scores.items():
        w = weights.get(domain, 1.0)
        s = score_data.get("score", 0.0)
        weighted_sum += s * w
        total_weight += w

    weighted_conviction = weighted_sum / total_weight if total_weight > 0 else 0.0

    state["aggregated_research"] = {
        "ticker": state["ticker"],
        "weighted_conviction": weighted_conviction,
        "scores": scores,
        "weights": weights,
    }
    state["step"] = "aggregation"
    return state


async def debate_node(state: TradingState) -> TradingState:
    """
    Bull/Bear single-turn debate.
    
    Both agents receive identical aggregated data and argue
    opposing viewpoints in parallel.
    """
    logger.info("node_executing", node="debate", ticker=state["ticker"])

    # In production, Bull and Bear agents run in parallel via asyncio.gather()
    state["debate_state"] = {
        "ticker": state["ticker"],
        "aggregated_data": state.get("aggregated_research", {}),
        "bull_argument": "Awaiting Bull Agent",
        "bull_score": 5.0,
        "bear_argument": "Awaiting Bear Agent",
        "bear_score": 5.0,
        "debate_complete": False,
    }
    state["step"] = "debate"
    return state


async def judge_node(state: TradingState) -> TradingState:
    """
    Judge Agent decision node.
    
    Receives debate state + portfolio state + macro regime,
    outputs a strict Pydantic ExecutionOrder.
    """
    logger.info("node_executing", node="judge", ticker=state["ticker"])

    debate = state.get("debate_state", {})
    net_conviction = debate.get("bull_score", 0) - debate.get("bear_score", 0)

    # Default to PASS — the Judge Agent will override in production
    state["execution_order"] = {
        "ticker": state["ticker"],
        "action": "PASS",
        "confidence_score": abs(net_conviction),
        "reasoning": f"Net conviction: {net_conviction:.1f}",
        "allocated_capital": 0.0,
    }
    state["step"] = "judge"
    return state


async def guardrail_node(state: TradingState) -> TradingState:
    """
    Deterministic execution guardrail validation.
    No LLM — pure Python safety checks.
    """
    logger.info("node_executing", node="guardrail", ticker=state["ticker"])

    order = state.get("execution_order", {})
    if order.get("action") in ("PASS", "HOLD"):
        state["guardrail_result"] = "PASSED_THROUGH"
    else:
        # Full guardrail validation in production
        state["guardrail_result"] = "APPROVED"

    state["step"] = "guardrail"
    return state


async def hitl_node(state: TradingState) -> TradingState:
    """
    Human-in-the-Loop checkpoint.
    
    Auto-passthrough under normal conditions.
    Interrupts and requests human approval when:
    - Confidence divergence > threshold
    - Drawdown limit approached
    - Anomalous volatility
    """
    logger.info("node_executing", node="hitl", ticker=state["ticker"])

    order = state.get("execution_order", {})
    if order.get("action") in ("PASS", "HOLD"):
        state["hitl_action"] = "AUTO_PASS"
    else:
        state["hitl_action"] = "AUTO_PASS"  # Default: auto-approve

    state["step"] = "hitl"
    return state


async def execution_node(state: TradingState) -> TradingState:
    """
    Alpaca order execution node.
    
    Only executes if all previous gates have approved.
    Uses bracket orders (OTOCO) for atomic SL/TP submission.
    """
    logger.info("node_executing", node="execution", ticker=state["ticker"])

    order = state.get("execution_order", {})
    guardrail = state.get("guardrail_result", "")
    hitl = state.get("hitl_action", "")

    if (
        order.get("action") == "BUY"
        and guardrail == "APPROVED"
        and hitl in ("AUTO_PASS", "HUMAN_APPROVED")
    ):
        # Execute via Alpaca in production
        state["trade_result"] = {
            "status": "SUBMITTED",
            "ticker": state["ticker"],
            "notional": order.get("allocated_capital", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    else:
        state["trade_result"] = {
            "status": "NO_TRADE",
            "reason": order.get("reasoning", "No trade signal"),
        }

    state["step"] = "execution"
    return state


# ════════════════════════════════════════════════════════════════════
# ROUTING LOGIC
# ════════════════════════════════════════════════════════════════════

def should_execute(state: TradingState) -> str:
    """Deterministic routing: should we proceed to execution?"""
    order = state.get("execution_order", {})
    if order.get("action") in ("BUY", "SELL"):
        return "guardrail"
    return "end"


def should_submit(state: TradingState) -> str:
    """Check guardrail result for execution."""
    if state.get("guardrail_result") == "APPROVED":
        return "hitl"
    return "end"


# ════════════════════════════════════════════════════════════════════
# DAG CONSTRUCTION
# ════════════════════════════════════════════════════════════════════

def build_trading_dag() -> StateGraph:
    """
    Build the main trading workflow DAG.
    
    This is the rigid, deterministic pipeline that processes
    every trading opportunity.
    """
    workflow = StateGraph(TradingState)

    # Add nodes
    workflow.add_node("regime_check", regime_check_node)
    workflow.add_node("parallel_research", parallel_research_node)
    workflow.add_node("aggregation", aggregation_node)
    workflow.add_node("debate", debate_node)
    workflow.add_node("judge", judge_node)
    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("hitl", hitl_node)
    workflow.add_node("execution", execution_node)

    # Set entry point
    workflow.set_entry_point("regime_check")

    # Define edges (deterministic routing)
    workflow.add_edge("regime_check", "parallel_research")
    workflow.add_edge("parallel_research", "aggregation")
    workflow.add_edge("aggregation", "debate")
    workflow.add_edge("debate", "judge")

    # Conditional routing after judge
    workflow.add_conditional_edges(
        "judge",
        should_execute,
        {"guardrail": "guardrail", "end": END},
    )

    workflow.add_conditional_edges(
        "guardrail",
        should_submit,
        {"hitl": "hitl", "end": END},
    )

    workflow.add_edge("hitl", "execution")
    workflow.add_edge("execution", END)

    return workflow


def compile_trading_dag():
    """Compile the trading DAG for execution."""
    workflow = build_trading_dag()
    return workflow.compile()
