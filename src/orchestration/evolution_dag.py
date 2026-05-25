"""
Evolution DAG

Post-market self-evolution workflow.
Executes the Reflexion framework: Brier scoring -> linguistic post-mortem ->
rule consolidation -> Shadow Crew A/B testing -> statistical significance -> promotion.

Now wired to real data via:
- prediction_tracker: provides actual predictions/outcomes
- BrierScoreEngine: computes calibration scores
- MetaReviewAgent: generates post-mortems and prompt proposals
- PromptEvolution: runs statistical significance tests
- persistence.db: stores/retrieves prompt versions
"""

from __future__ import annotations

import uuid
import structlog
from typing import TypedDict
from langgraph.graph import StateGraph, END

from config.constants import (
    BRIER_WINDOW_SIZE,
    SHADOW_MIN_TRADES,
    EVOLUTION_P_VALUE_THRESHOLD,
)
from evolution.reflexion import BrierScoreEngine, PromptEvolution
from evolution.prediction_tracker import prediction_tracker
from persistence.db import (
    get_active_prompt,
    get_pending_prompt_versions,
    get_predictions_for_prompt_version,
)

logger = structlog.get_logger(component="evolution_dag")


class EvolutionState(TypedDict):
    """State for the evolution DAG."""
    agent_id: str
    agent_role: str
    recent_trades: list[dict]
    brier_score: float
    post_mortem: str
    proposed_nuance: str
    shadow_crew_results: dict
    promotion_decision: str
    step: str
    error: str


async def brier_score_node(state: EvolutionState) -> EvolutionState:
    """Compute real Brier score from prediction data."""
    role = state.get("agent_role", "")
    logger.info("evolution_node", node="brier_score", agent=role)

    try:
        predictions = prediction_tracker.get_resolved_predictions(
            agent_role=role, window=BRIER_WINDOW_SIZE,
        )

        if len(predictions) < 5:
            state["brier_score"] = 0.5  # Baseline — insufficient data
            state["error"] = f"Insufficient predictions ({len(predictions)})"
        else:
            probs, outcomes = prediction_tracker.extract_brier_inputs(predictions)
            state["brier_score"] = BrierScoreEngine.calculate(probs, outcomes)

        state["recent_trades"] = predictions
    except Exception as e:
        logger.error("brier_score_failed", agent=role, error=str(e))
        state["brier_score"] = 0.5
        state["error"] = str(e)

    state["step"] = "brier_score"
    return state


async def post_mortem_node(state: EvolutionState) -> EvolutionState:
    """Generate linguistic post-mortem via MetaReviewAgent."""
    role = state.get("agent_role", "")
    logger.info("evolution_node", node="post_mortem", agent=role)

    try:
        from core.llm_factory import get_efficient_llm
        from agents.meta_review_agent import MetaReviewAgent

        llm = get_efficient_llm()
        meta = MetaReviewAgent(llm)

        result = await meta.generate_post_mortem(
            agent_role=role,
            predictions=state.get("recent_trades", []),
            brier_score=state.get("brier_score", 0.5),
        )

        # Extract text from result
        if isinstance(result, dict):
            state["post_mortem"] = result.get("content", str(result))
        elif hasattr(result, "content"):
            state["post_mortem"] = str(result.content)
        else:
            state["post_mortem"] = str(result)

    except Exception as e:
        logger.error("post_mortem_failed", agent=role, error=str(e))
        state["post_mortem"] = f"Post-mortem generation failed: {e}"

    state["step"] = "post_mortem"
    return state


async def rule_consolidation_node(state: EvolutionState) -> EvolutionState:
    """Propose prompt update via MetaReviewAgent with rule consolidation."""
    role = state.get("agent_role", "")
    logger.info("evolution_node", node="rule_consolidation", agent=role)

    try:
        from core.llm_factory import get_efficient_llm
        from agents.meta_review_agent import MetaReviewAgent

        llm = get_efficient_llm()
        meta = MetaReviewAgent(llm)

        # Get current nuance
        active = get_active_prompt(role)
        current_nuance = active["prompt_text"] if active else ""
        current_rules_count = current_nuance.count("- ") if current_nuance else 0

        result = await meta.propose_prompt_update(
            agent_role=role,
            current_nuance=current_nuance,
            brier_score=state.get("brier_score", 0.5),
            post_mortem=state.get("post_mortem", ""),
            current_rules_count=current_rules_count,
        )

        if isinstance(result, dict):
            state["proposed_nuance"] = result.get("content", str(result))
        elif hasattr(result, "content"):
            state["proposed_nuance"] = str(result.content)
        else:
            state["proposed_nuance"] = str(result)

    except Exception as e:
        logger.error("rule_consolidation_failed", agent=role, error=str(e))
        state["proposed_nuance"] = ""

    state["step"] = "rule_consolidation"
    return state


async def shadow_crew_node(state: EvolutionState) -> EvolutionState:
    """Check Shadow Crew A/B test results for pending prompt versions."""
    role = state.get("agent_role", "")
    logger.info("evolution_node", node="shadow_crew", agent=role)

    try:
        pending = get_pending_prompt_versions(role)
        if not pending:
            state["shadow_crew_results"] = {"status": "NO_PENDING_TESTS"}
            state["step"] = "shadow_crew"
            return state

        # Evaluate the most recent pending version
        pv = pending[0]
        version = pv["version_number"]

        shadow_preds = get_predictions_for_prompt_version(
            agent_role=role, prompt_version=version, resolved_only=True,
        )

        if len(shadow_preds) < SHADOW_MIN_TRADES:
            state["shadow_crew_results"] = {
                "status": "INSUFFICIENT_DATA",
                "trades": len(shadow_preds),
                "required": SHADOW_MIN_TRADES,
            }
        else:
            prod_preds = prediction_tracker.get_resolved_predictions(
                agent_role=role, window=len(shadow_preds), is_shadow=False,
            )

            shadow_errors = [
                (p["predicted_probability"] - p["actual_outcome"]) ** 2
                for p in shadow_preds if p.get("actual_outcome") is not None
            ]
            prod_errors = [
                (p["predicted_probability"] - p["actual_outcome"]) ** 2
                for p in prod_preds if p.get("actual_outcome") is not None
            ]

            if len(shadow_errors) >= 5 and len(prod_errors) >= 5:
                sig = PromptEvolution.evaluate_significance(prod_errors, shadow_errors)
                # Invert for error metric (lower = better)
                recommendation = sig["recommendation"]
                if recommendation == "PROMOTE":
                    recommendation = "ROLLBACK"
                elif recommendation == "ROLLBACK":
                    recommendation = "PROMOTE"

                state["shadow_crew_results"] = {
                    "status": "EVALUATED",
                    "p_value": sig["p_value"],
                    "significant": sig["significant"],
                    "recommendation": recommendation,
                    "version": version,
                    "shadow_brier": round(sum(shadow_errors) / len(shadow_errors), 4),
                    "prod_brier": round(sum(prod_errors) / len(prod_errors), 4),
                }
            else:
                state["shadow_crew_results"] = {"status": "INSUFFICIENT_DATA"}

    except Exception as e:
        logger.error("shadow_crew_failed", agent=role, error=str(e))
        state["shadow_crew_results"] = {"status": "ERROR", "error": str(e)}

    state["step"] = "shadow_crew"
    return state


async def promotion_node(state: EvolutionState) -> EvolutionState:
    """Decide whether to promote, discard, or continue testing."""
    role = state.get("agent_role", "")
    logger.info("evolution_node", node="promotion", agent=role)

    results = state.get("shadow_crew_results", {})
    status = results.get("status", "")

    if status == "EVALUATED":
        recommendation = results.get("recommendation", "CONTINUE_TESTING")
        p_value = results.get("p_value", 1.0)

        if recommendation == "PROMOTE" and p_value < EVOLUTION_P_VALUE_THRESHOLD:
            state["promotion_decision"] = "PROMOTE"
            logger.info(
                "promotion_decision",
                agent=role, decision="PROMOTE",
                p_value=p_value,
            )
        elif recommendation == "ROLLBACK":
            state["promotion_decision"] = "DISCARD"
            logger.info(
                "promotion_decision",
                agent=role, decision="DISCARD",
                p_value=p_value,
            )
        else:
            state["promotion_decision"] = "CONTINUE_TESTING"
    else:
        state["promotion_decision"] = "NO_ACTION"

    state["step"] = "promotion"
    return state


def build_evolution_dag() -> StateGraph:
    workflow = StateGraph(EvolutionState)

    workflow.add_node("brier_score", brier_score_node)
    workflow.add_node("post_mortem", post_mortem_node)
    workflow.add_node("rule_consolidation", rule_consolidation_node)
    workflow.add_node("shadow_crew", shadow_crew_node)
    workflow.add_node("promotion", promotion_node)

    workflow.set_entry_point("brier_score")

    workflow.add_edge("brier_score", "post_mortem")
    workflow.add_edge("post_mortem", "rule_consolidation")
    workflow.add_edge("rule_consolidation", "shadow_crew")
    workflow.add_edge("shadow_crew", "promotion")
    workflow.add_edge("promotion", END)

    return workflow

def compile_evolution_dag():
    return build_evolution_dag().compile()
