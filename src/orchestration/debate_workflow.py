"""
Debate Workflow

Parallel Bull/Bear debate sub-graph with real agent invocations.
Executes the debate phase where Bull and Bear agents construct theses
and the Judge agent evaluates them.

Phase 5: Nodes now invoke real agents with tool-calling capabilities.
Bull and Bear agents receive aggregated research + active insights
from the InsightPublisher, enabling them to reference other agents'
findings in their arguments.
"""

from __future__ import annotations

import asyncio
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
    """Bull Agent — constructs the bullish thesis with real LLM."""
    logger.info("debate_node", node="bull", ticker=state["ticker"])

    try:
        from core.llm_factory import get_efficient_llm
        from agents.debate_agents import BullAgent

        llm = get_efficient_llm()
        bull = BullAgent(llm)

        # Get active insights for context
        insights_ctx = ""
        try:
            from core.insight_publisher import insight_publisher
            signals = insight_publisher.get_all_active_signals(ticker=state["ticker"])
            if signals:
                insights_ctx = insight_publisher.format_insights_for_context(signals)
        except Exception:
            pass

        market_data = state.get("market_data", {})
        prompt = (
            f"BULL THESIS for {state['ticker']}.\n"
            f"Market data: {str(market_data)[:300]}\n"
        )
        if insights_ctx:
            prompt += f"\n{insights_ctx}\n"
        prompt += (
            "\nMake the strongest bullish case in 150 words or fewer. "
            "Include conviction score (0-10) and top 3 data points."
        )

        result = await bull.invoke(user_message=prompt, context=market_data)
        content = result.get("content", "")

        state["bull_thesis"] = content[:600]

        # Extract score
        import re
        score_match = re.search(r"(?:conviction|score)\s*[:=]\s*([0-9]+\.?[0-9]*)", content, re.IGNORECASE)
        state["bull_score"] = min(10.0, float(score_match.group(1))) if score_match else 7.0

    except Exception as e:
        logger.error("bull_node_failed", error=str(e))
        state["bull_thesis"] = "Strong technical breakout and positive sentiment."
        state["bull_score"] = 6.5

    state["step"] = "bull"
    return state


async def bear_node(state: DebateState) -> DebateState:
    """Bear Agent — constructs the bearish thesis with real LLM."""
    logger.info("debate_node", node="bear", ticker=state["ticker"])

    try:
        from core.llm_factory import get_efficient_llm
        from agents.debate_agents import BearAgent

        llm = get_efficient_llm()
        bear = BearAgent(llm)

        # Get active insights for context
        insights_ctx = ""
        try:
            from core.insight_publisher import insight_publisher
            signals = insight_publisher.get_all_active_signals(ticker=state["ticker"])
            if signals:
                insights_ctx = insight_publisher.format_insights_for_context(signals)
        except Exception:
            pass

        market_data = state.get("market_data", {})
        prompt = (
            f"BEAR THESIS for {state['ticker']}.\n"
            f"Market data: {str(market_data)[:300]}\n"
        )
        if insights_ctx:
            prompt += f"\n{insights_ctx}\n"
        prompt += (
            "\nMake the strongest bearish case in 150 words or fewer. "
            "Include conviction score (0-10) and top 3 data points."
        )

        result = await bear.invoke(user_message=prompt, context=market_data)
        content = result.get("content", "")

        state["bear_thesis"] = content[:600]

        import re
        score_match = re.search(r"(?:conviction|score)\s*[:=]\s*([0-9]+\.?[0-9]*)", content, re.IGNORECASE)
        state["bear_score"] = min(10.0, float(score_match.group(1))) if score_match else 6.0

    except Exception as e:
        logger.error("bear_node_failed", error=str(e))
        state["bear_thesis"] = "Macro headwinds and overextended valuation."
        state["bear_score"] = 5.5

    state["step"] = "bear"
    return state


async def judge_node(state: DebateState) -> DebateState:
    """Judge Agent — evaluates the debate with real LLM and tools."""
    logger.info("debate_node", node="judge", ticker=state["ticker"])

    try:
        from core.llm_factory import get_premium_llm
        from agents.judge_agent import JudgeAgent

        llm = get_premium_llm()
        judge = JudgeAgent(llm)

        prompt = (
            f"JUDGE DECISION for {state['ticker']}.\n\n"
            f"Bull Thesis (conviction {state.get('bull_score', 0):.1f}/10):\n"
            f"{state.get('bull_thesis', 'N/A')[:300]}\n\n"
            f"Bear Thesis (conviction {state.get('bear_score', 0):.1f}/10):\n"
            f"{state.get('bear_thesis', 'N/A')[:300]}\n\n"
            f"Use your tools (get_active_signals, get_risk_alerts) "
            f"to gather additional intelligence.\n\n"
            f"Decide: BUY, PASS, or HOLD.\n"
            f"Respond: ACTION: ..., CONFIDENCE: 0-10, REASONING: one line"
        )

        context = {
            "ticker": state["ticker"],
            "bull_score": state.get("bull_score", 0),
            "bear_score": state.get("bear_score", 0),
            "net_conviction": state.get("bull_score", 0) - state.get("bear_score", 0),
        }

        result = await judge.invoke(user_message=prompt, context=context)
        content = result.get("content", "")

        # Parse Judge decision
        action = "BUY"
        confidence = 7.0
        reasoning = content[:200]

        for line in content.split("\n"):
            upper = line.upper().strip()
            if upper.startswith("ACTION:"):
                parsed_action = upper.split(":", 1)[1].strip()
                if parsed_action in ("BUY", "SELL", "HOLD", "PASS"):
                    action = parsed_action
            elif upper.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
            elif upper.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()[:200]

        state["judge_decision"] = {
            "action": action,
            "confidence": confidence,
            "reasoning": reasoning,
            "tools_used": result.get("_tools_used", []),
        }

    except Exception as e:
        logger.error("judge_node_failed", error=str(e))
        net = state.get("bull_score", 0) - state.get("bear_score", 0)
        state["judge_decision"] = {
            "action": "BUY" if net > 1.5 else "PASS",
            "confidence": abs(net),
            "reasoning": f"Fallback: Net conviction {net:.1f}",
        }

    state["step"] = "judge"
    return state


def build_debate_workflow() -> StateGraph:
    workflow = StateGraph(DebateState)

    workflow.add_node("bull", bull_node)
    workflow.add_node("bear", bear_node)
    workflow.add_node("judge", judge_node)

    # Bull and Bear run sequentially in LangGraph (parallel via trading_dag)
    workflow.set_entry_point("bull")

    workflow.add_edge("bull", "bear")
    workflow.add_edge("bear", "judge")
    workflow.add_edge("judge", END)

    return workflow


def compile_debate_workflow():
    return build_debate_workflow().compile()
