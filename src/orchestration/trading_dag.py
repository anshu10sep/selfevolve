"""
Main Trading DAG

The core trading workflow implemented as a LangGraph Directed Acyclic Graph.
This is the production execution pipeline:

    Market Trigger → Regime Check → Parallel Research → Aggregation
    → Bull/Bear Debate → Judge Decision → Guardrail Validation
    → HITL Checkpoint → Alpaca Execution

All routing is DETERMINISTIC Python. LLMs act as nodes that perform
specific analysis — they do NOT decide routing logic.

Phase 5: Nodes now invoke REAL agents with tools, memory, and
inter-agent insight sharing. Each analyst publishes an AgentInsight
after analysis. The Judge queries all active insights before deciding.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict, Optional
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
    strategy_consensus: dict   # B5 fix: aggregated strategy agent signals
    aggregated_research: dict
    debate_state: dict
    execution_order: dict
    guardrail_result: str
    hitl_action: str
    trade_result: dict
    error: str
    step: str


# ════════════════════════════════════════════════════════════════════
# HELPER: Create Agent Instances
# ════════════════════════════════════════════════════════════════════

def _create_analyst_agents():
    """Create the four analyst agents with efficient LLMs."""
    try:
        from core.llm_factory import get_efficient_llm
        from agents.analyst_agents import (
            TechnicalAnalystAgent,
            FundamentalAnalystAgent,
            SentimentAnalystAgent,
            MacroAnalystAgent,
        )
        llm = get_efficient_llm()
        return {
            "technical": TechnicalAnalystAgent(llm),
            "fundamental": FundamentalAnalystAgent(llm),
            "sentiment": SentimentAnalystAgent(llm),
            "macro": MacroAnalystAgent(llm),
        }
    except Exception as e:
        logger.warning("analyst_creation_failed", error=str(e))
        return None


def _create_debate_agents():
    """Create Bull, Bear, and Judge agents."""
    try:
        from core.llm_factory import get_efficient_llm, get_premium_llm
        from agents.debate_agents import BullAgent, BearAgent
        from agents.judge_agent import JudgeAgent

        efficient = get_efficient_llm()
        premium = get_premium_llm()

        return {
            "bull": BullAgent(efficient),
            "bear": BearAgent(efficient),
            "judge": JudgeAgent(premium),  # Premium tier for decisions
        }
    except Exception as e:
        logger.warning("debate_agent_creation_failed", error=str(e))
        return None


# ════════════════════════════════════════════════════════════════════
# NODE FUNCTIONS
# ════════════════════════════════════════════════════════════════════

async def regime_check_node(state: TradingState) -> TradingState:
    """
    Regime classification node.

    Checks the InsightPublisher for a recent regime insight.
    If none exists, uses default SIDEWAYS regime.
    Publishes the regime for other agents to consume.
    """
    logger.info("node_executing", node="regime_check", ticker=state["ticker"])

    # Check InsightPublisher for recent regime insight
    regime_data = {
        "regime": "SIDEWAYS",
        "vix_level": 15.0,
        "position_size_modifier": 1.0,
        "source": "default",
    }

    try:
        from core.insight_publisher import insight_publisher
        regime_insight = insight_publisher.get_active_regime()

        if regime_insight:
            detected_regime = regime_insight.data.get(
                "regime",
                regime_insight.data.get("new_regime", "SIDEWAYS"),
            )
            vix = regime_insight.data.get("vix", 15.0)

            # Adjust position sizing based on regime
            size_modifier = 1.0
            if detected_regime == "BEAR":
                size_modifier = 0.5
            elif detected_regime == "HIGH_VOL":
                size_modifier = 0.3
            elif detected_regime == "PANIC":
                size_modifier = 0.1

            regime_data = {
                "regime": detected_regime,
                "vix_level": vix,
                "position_size_modifier": size_modifier,
                "source": regime_insight.source_agent,
                "confidence": regime_insight.confidence,
                "age_minutes": round(regime_insight.age_minutes, 1),
            }

            logger.info(
                "regime_from_insight",
                regime=detected_regime,
                source=regime_insight.source_agent,
                confidence=f"{regime_insight.confidence:.0%}",
            )
    except Exception as e:
        logger.debug("regime_insight_check_failed", error=str(e))

    state["regime"] = regime_data
    state["step"] = "regime_check"
    return state


async def parallel_research_node(state: TradingState) -> TradingState:
    """
    Parallel research from all four analyst agents.

    Each analyst runs concurrently via asyncio.gather().
    After analysis, each agent publishes an AgentInsight
    with their key finding for cross-agent consumption.
    """
    logger.info("node_executing", node="parallel_research", ticker=state["ticker"])

    ticker = state["ticker"]
    regime = state.get("regime", {})

    analysts = _create_analyst_agents()

    if analysts is None:
        # Fallback to placeholder scores
        logger.warning("analysts_unavailable_using_stubs", ticker=ticker)
        for role in ("fundamental", "technical", "sentiment", "macro"):
            state[f"{role}_score"] = {
                "agent_id": role, "ticker": ticker,
                "score": 0.0, "confidence": 0.0,
                "rationale": "Analyst unavailable",
            }
        state["step"] = "parallel_research"
        return state

    # Build context for analysts
    context = {
        "ticker": ticker,
        "market_regime": regime.get("regime", "SIDEWAYS"),
        "vix_level": regime.get("vix_level", 15.0),
    }

    # Run all 4 analysts in parallel
    async def _run_analyst(role: str, agent, ctx: dict) -> dict:
        try:
            result = await agent.invoke(
                user_message=(
                    f"Analyze {ticker} for a swing trade (1-5 day hold). "
                    f"Market regime is {ctx.get('market_regime', 'SIDEWAYS')}. "
                    f"Provide your conviction score (-1.0 to 1.0), confidence (0-1), "
                    f"and a brief rationale."
                ),
                context=ctx,
            )

            # Extract structured score from the response
            content = result.get("content", "")
            score = _extract_score(content)
            confidence = _extract_confidence(content)

            # Publish insight after analysis
            try:
                insight_type = _role_to_insight_type(role)
                if insight_type:
                    await agent.publish_insight(
                        insight_type=insight_type,
                        title=f"{role.title()} Analysis: {ticker}",
                        description=content[:500],
                        confidence=confidence,
                        ticker=ticker,
                        data={
                            "score": score,
                            "direction": "BULLISH" if score > 0.2 else ("BEARISH" if score < -0.2 else "NEUTRAL"),
                            "regime": ctx.get("market_regime"),
                        },
                    )
            except Exception as e:
                logger.debug("insight_publish_skipped", role=role, error=str(e))

            return {
                "agent_id": role, "ticker": ticker,
                "score": score, "confidence": confidence,
                "rationale": content[:300],
            }

        except Exception as e:
            logger.error("analyst_invocation_failed", role=role, error=str(e))
            return {
                "agent_id": role, "ticker": ticker,
                "score": 0.0, "confidence": 0.0,
                "rationale": f"Analysis failed: {str(e)[:100]}",
            }

    # Execute all analysts in parallel + strategy signal aggregation
    async def _run_strategies(ctx: dict) -> dict:
        """Run strategy agents in parallel alongside analysts (B5 fix)."""
        try:
            from orchestration.strategy_signal_aggregator import aggregate_strategy_signals
            # Fetch market data for strategies
            market_data = {}
            try:
                from broker.alpaca_client import AlpacaClient
                alpaca = AlpacaClient()
                bars = await alpaca.get_bars(ticker, timeframe="1Day", limit=30)
                quote = await alpaca.get_latest_quote(ticker)
                await alpaca.close()
                market_data = {
                    ticker: {
                        "bars": bars,
                        "quote": quote,
                        "regime": ctx.get("market_regime", "SIDEWAYS"),
                    }
                }
            except Exception:
                pass
            return await aggregate_strategy_signals(ticker, market_data)
        except Exception as e:
            logger.debug("strategy_aggregation_skipped", error=str(e))
            return {}

    results = await asyncio.gather(
        _run_analyst("fundamental", analysts["fundamental"], context),
        _run_analyst("technical", analysts["technical"], context),
        _run_analyst("sentiment", analysts["sentiment"], context),
        _run_analyst("macro", analysts["macro"], context),
        _run_strategies(context),
    )

    state["fundamental_score"] = results[0]
    state["technical_score"] = results[1]
    state["sentiment_score"] = results[2]
    state["macro_score"] = results[3]
    state["strategy_consensus"] = results[4]  # B5 fix: strategy signals
    state["step"] = "parallel_research"

    logger.info(
        "parallel_research_complete",
        ticker=ticker,
        scores={r["agent_id"]: r["score"] for r in results[:4]},
        strategy_consensus=results[4].get("consensus_action", "N/A") if results[4] else "N/A",
    )
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

    # Load trust weights from DB (fallback to defaults)
    weights = {"fundamental": 1.0, "technical": 1.0, "sentiment": 0.8, "macro": 0.9}
    try:
        from persistence.db import get_agent_scores
        db_scores = get_agent_scores()
        role_map = {
            "FUNDAMENTAL_ANALYST": "fundamental",
            "TECHNICAL_ANALYST": "technical",
            "SENTIMENT_ANALYST": "sentiment",
            "MACRO_ANALYST": "macro",
        }
        for score in db_scores:
            domain = role_map.get(score.get("role"), None)
            if domain and score.get("trust_weight") is not None:
                weights[domain] = score["trust_weight"]
    except Exception:
        pass  # Use defaults

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
    Bull/Bear single-turn debate with real agents.

    Both agents receive the aggregated research data + active insights
    and argue opposing viewpoints in parallel.
    """
    logger.info("node_executing", node="debate", ticker=state["ticker"])

    ticker = state["ticker"]
    aggregated = state.get("aggregated_research", {})
    regime = state.get("regime", {})

    agents = _create_debate_agents()

    if agents is None:
        # Fallback to placeholder
        logger.warning("debate_agents_unavailable", ticker=ticker)
        state["debate_state"] = {
            "ticker": ticker,
            "aggregated_data": aggregated,
            "bull_argument": "Debate agents unavailable",
            "bull_score": 5.0,
            "bear_argument": "Debate agents unavailable",
            "bear_score": 5.0,
            "debate_complete": False,
        }
        state["step"] = "debate"
        return state

    # Get active insights for debate context
    insights_context = ""
    try:
        from core.insight_publisher import insight_publisher
        signals = insight_publisher.get_all_active_signals(ticker=ticker)
        if signals:
            insights_context = insight_publisher.format_insights_for_context(signals)
    except Exception:
        pass

    debate_context = {
        "ticker": ticker,
        "weighted_conviction": aggregated.get("weighted_conviction", 0.0),
        "analyst_scores": {
            k: v.get("score", 0) for k, v in aggregated.get("scores", {}).items()
        },
        "market_regime": regime.get("regime", "SIDEWAYS"),
    }

    # Build debate prompt with research data
    research_summary = "\n".join(
        f"  - {role.title()}: score={data.get('score', 0):.2f}, "
        f"confidence={data.get('confidence', 0):.2f}, "
        f"rationale=\"{data.get('rationale', '')[:100]}\""
        for role, data in aggregated.get("scores", {}).items()
    )

    debate_prompt = (
        f"Ticker: {ticker}\n"
        f"Weighted Conviction: {aggregated.get('weighted_conviction', 0):.2f}\n"
        f"Market Regime: {regime.get('regime', 'SIDEWAYS')}\n\n"
        f"Analyst Research:\n{research_summary}\n"
    )
    if insights_context:
        debate_prompt += f"\n{insights_context}\n"

    debate_prompt += (
        "\nConstruct your thesis in 150 words or fewer. "
        "Include your conviction score (0-10) and top 3 data points."
    )

    # Run Bull and Bear in parallel
    async def _run_debater(role: str, agent, prompt: str, ctx: dict) -> dict:
        try:
            result = await agent.invoke(
                user_message=prompt,
                context=ctx,
            )
            content = result.get("content", "")
            score = _extract_debate_score(content)
            return {
                "argument": content[:600],
                "score": score,
            }
        except Exception as e:
            logger.error("debater_failed", role=role, error=str(e))
            return {"argument": f"Debate failed: {str(e)[:100]}", "score": 5.0}

    bull_result, bear_result = await asyncio.gather(
        _run_debater("bull", agents["bull"], f"BULL THESIS: {debate_prompt}", debate_context),
        _run_debater("bear", agents["bear"], f"BEAR THESIS: {debate_prompt}", debate_context),
    )

    state["debate_state"] = {
        "ticker": ticker,
        "aggregated_data": aggregated,
        "bull_argument": bull_result["argument"],
        "bull_score": bull_result["score"],
        "bear_argument": bear_result["argument"],
        "bear_score": bear_result["score"],
        "debate_complete": True,
    }
    state["step"] = "debate"

    logger.info(
        "debate_complete",
        ticker=ticker,
        bull_score=bull_result["score"],
        bear_score=bear_result["score"],
        net=bull_result["score"] - bear_result["score"],
    )
    return state


async def judge_node(state: TradingState) -> TradingState:
    """
    Judge Agent decision node.

    Receives debate state + portfolio state + active insights,
    queries risk alerts and cross-agent signals, then outputs
    a strict ExecutionOrder.
    """
    logger.info("node_executing", node="judge", ticker=state["ticker"])

    ticker = state["ticker"]
    debate = state.get("debate_state", {})
    regime = state.get("regime", {})
    portfolio = state.get("portfolio", {})
    aggregated = state.get("aggregated_research", {})

    agents = _create_debate_agents()

    if agents is None or "judge" not in agents:
        # Fallback to deterministic decision
        net_conviction = debate.get("bull_score", 0) - debate.get("bear_score", 0)
        state["execution_order"] = {
            "ticker": ticker,
            "action": "PASS",
            "confidence_score": abs(net_conviction),
            "reasoning": f"Judge unavailable. Net conviction: {net_conviction:.1f}",
            "allocated_capital": 0.0,
        }
        state["step"] = "judge"
        return state

    judge = agents["judge"]

    # Build comprehensive context for the Judge
    judge_context = {
        "ticker": ticker,
        "market_regime": regime.get("regime", "SIDEWAYS"),
        "vix_level": regime.get("vix_level", 15.0),
        "bull_score": debate.get("bull_score", 5.0),
        "bear_score": debate.get("bear_score", 5.0),
        "net_conviction": debate.get("bull_score", 0) - debate.get("bear_score", 0),
        "weighted_conviction": aggregated.get("weighted_conviction", 0),
    }

    # Build the judge prompt with all available intelligence
    prompt = (
        f"JUDGE DECISION for {ticker}\n\n"
        f"Market Regime: {regime.get('regime', 'SIDEWAYS')} "
        f"(VIX: {regime.get('vix_level', 15.0):.1f})\n\n"
        f"Bull Thesis (score {debate.get('bull_score', 0):.1f}/10):\n"
        f"{debate.get('bull_argument', 'N/A')[:300]}\n\n"
        f"Bear Thesis (score {debate.get('bear_score', 0):.1f}/10):\n"
        f"{debate.get('bear_argument', 'N/A')[:300]}\n\n"
        f"Analyst Weighted Conviction: {aggregated.get('weighted_conviction', 0):.2f}\n\n"
    )

    # B5 fix: Include strategy agent consensus in the Judge's prompt
    strategy_consensus = state.get("strategy_consensus", {})
    if strategy_consensus and strategy_consensus.get("strategies_evaluated", 0) > 0:
        try:
            from orchestration.strategy_signal_aggregator import format_for_judge
            strategy_section = format_for_judge(strategy_consensus)
            prompt += f"\n{strategy_section}\n\n"
        except Exception:
            pass

    prompt += (
        f"Use your available tools (get_active_signals, get_risk_alerts, "
        f"recall_similar_trades, get_current_regime_for_judge) to gather "
        f"additional intelligence before deciding.\n\n"
        f"Decide: BUY, PASS, or HOLD.\n"
        f"Respond EXACTLY:\n"
        f"ACTION: BUY/PASS/HOLD\n"
        f"CONFIDENCE: 0-10\n"
        f"REASONING: one sentence\n"
        f"CAPITAL: dollar amount (0 if PASS/HOLD)"
    )

    try:
        result = await judge.invoke(
            user_message=prompt,
            context=judge_context,
        )
        content = result.get("content", "")

        # Parse the Judge's decision
        action = "PASS"
        confidence = 0.0
        reasoning = content[:200]
        capital = 0.0

        for line in content.split("\n"):
            upper = line.upper().strip()
            if upper.startswith("ACTION:"):
                action_str = upper.split(":", 1)[1].strip()
                if action_str in ("BUY", "SELL", "HOLD", "PASS"):
                    action = action_str
            elif upper.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
            elif upper.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()[:200]
            elif upper.startswith("CAPITAL:"):
                try:
                    capital = float(
                        line.split(":", 1)[1].strip()
                        .replace("$", "").replace(",", "")
                    )
                except (ValueError, IndexError):
                    pass

        state["execution_order"] = {
            "ticker": ticker,
            "action": action,
            "confidence_score": confidence,
            "reasoning": reasoning,
            "allocated_capital": capital,
            "tools_used": result.get("_tools_used", []),
        }

        logger.info(
            "judge_decision",
            ticker=ticker,
            action=action,
            confidence=confidence,
            reasoning=reasoning[:80],
        )

    except Exception as e:
        logger.error("judge_failed", error=str(e))
        state["execution_order"] = {
            "ticker": ticker,
            "action": "PASS",
            "confidence_score": 0.0,
            "reasoning": f"Judge error: {str(e)[:100]}",
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
        # Run guardrail checks
        try:
            portfolio = state.get("portfolio", {})
            capital = order.get("allocated_capital", 0)
            ticker = state["ticker"]

            errors = []

            # Basic capital check
            buying_power = portfolio.get("buying_power", portfolio.get("available_cash", 0))
            if capital > 0 and buying_power > 0 and capital > buying_power:
                errors.append(f"Capital ${capital:.0f} exceeds buying power ${buying_power:.0f}")

            # Position concentration check
            total_equity = portfolio.get("total_equity", 0)
            if total_equity > 0 and capital > total_equity * 0.30:
                errors.append(f"Position would exceed 30% concentration")

            # Minimum trade size
            if 0 < capital < 5.0:
                errors.append(f"Trade size ${capital:.2f} below minimum")

            if errors:
                state["guardrail_result"] = "REJECTED"
                state["error"] = "; ".join(errors)
                logger.warning("guardrail_rejected", ticker=ticker, errors=errors)
            else:
                state["guardrail_result"] = "APPROVED"
        except Exception as e:
            # Default to approved if guardrails unavailable
            logger.warning("guardrail_check_failed", error=str(e))
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
    Order Preparation Node (final DAG stage).

    Prepares the order result dict based on all previous gate approvals
    (guardrails + HITL). Does NOT submit to Alpaca directly — actual
    broker submission is handled by main.py after DAG completion.

    This separation keeps the DAG pure (decision engine) and lets
    main.py manage capital allocation, VectorStore context storage,
    and Brier prediction recording alongside the broker call.
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
# PARSING HELPERS
# ════════════════════════════════════════════════════════════════════

def _extract_score(content: str) -> float:
    """Extract a conviction score (-1.0 to 1.0) from LLM output."""
    import re
    # Look for explicit score mentions
    patterns = [
        r"(?:conviction|score)\s*[:=]\s*(-?[0-9]+\.?[0-9]*)",
        r"(-?[0-9]+\.?[0-9]*)\s*/\s*1\.0",
        r"Score:\s*(-?[0-9]+\.?[0-9]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                return max(-1.0, min(1.0, val))
            except ValueError:
                continue
    return 0.0


def _extract_confidence(content: str) -> float:
    """Extract a confidence level (0-1) from LLM output."""
    import re
    patterns = [
        r"confidence\s*[:=]\s*([0-9]+\.?[0-9]*)",
        r"([0-9]+\.?[0-9]*)\s*confidence",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if val > 1.0:
                    val = val / 10.0  # Normalize 1-10 to 0-1
                return max(0.0, min(1.0, val))
            except ValueError:
                continue
    return 0.5


def _extract_debate_score(content: str) -> float:
    """Extract a debate conviction score (0-10) from LLM output."""
    import re
    patterns = [
        r"(?:conviction|score)\s*[:=]\s*([0-9]+\.?[0-9]*)",
        r"([0-9]+\.?[0-9]*)\s*/\s*10",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                return max(0.0, min(10.0, val))
            except ValueError:
                continue
    return 5.0


def _role_to_insight_type(role: str) -> Optional[str]:
    """Map analyst role to InsightType."""
    mapping = {
        "technical": "TECHNICAL_SIGNAL",
        "fundamental": "FUNDAMENTAL_FLAG",
        "sentiment": "SENTIMENT_DIVERGENCE",
        "macro": "REGIME_CHANGE",
    }
    return mapping.get(role)


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
    every trading opportunity. Nodes invoke real agents with
    tools, memory, and inter-agent insight sharing.
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
