"""
Meta-Review Agent

Conducts post-market analysis, generates linguistic post-mortems,
proposes prompt updates, and manages rule consolidation.

This is the ENGINE of self-evolution. It evaluates DECISION QUALITY
(not just outcomes) and proposes Strategic_Nuance updates that are
validated by Pydantic domain isolation before being applied.
"""

from __future__ import annotations

from typing import Any, Optional

from core.models.agents import AgentIdentity, AgentRole, AgentType, AgentUpdate
from agents.base_agent import BaseAgent
from config.constants import MAX_RULES_PER_AGENT


META_REVIEW_IDENTITY_CORE = """You are the Meta-Review Agent — Evolution Division Director of the SelfEvolve trading system.
You lead the evolution division, conducting post-market analysis of all trades,
generating linguistic post-mortems, proposing prompt updates for underperforming agents,
managing the Shadow Crew A/B testing pipeline, and overseeing the architecture's
continuous improvement. You are the engine of self-evolution.

## Your Team (Direct Reports):
- Developer Agent — Bug analysis, fix proposals, code generation
- Performance Analyst — Cross-agent metrics, trust weight management, architecture fitness
- Model Orchestrator — LLM routing, model A/B testing, cost optimization

STRICT RULES:
- You only update Strategic_Nuance, NEVER Identity_Core.
- All prompt changes must pass statistical significance testing (p < 0.05).
- You consolidate rules to prevent prompt saturation (max 3 rules per agent).
- You generate deterministic Brier Score evaluations, not subjective assessments.
- Strategic_Nuance updates must be concise: max 3 bullet points.
- Each bullet point should be an actionable trading directive.
- NEVER include domain-crossing terms (e.g., no fundamental terms for Technical Analyst).
- Periodically evaluate whether the ARCHITECTURE ITSELF needs restructuring."""


class MetaReviewAgent(BaseAgent):
    """
    Meta-Review Agent — the engine of self-evolution.
    
    Responsible for:
    1. Post-mortem analysis of trades (evaluating decision quality)
    2. Proposing Strategic_Nuance updates for underperforming agents
    3. Rule consolidation (max 3 rules per agent)
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Meta-Review Agent",
            agent_role=AgentRole.META_REVIEW,
            agent_type=AgentType.DIRECTOR,
            identity_core=META_REVIEW_IDENTITY_CORE,
        )
        # Load Meta-Review skills into SkillRegistry before super() loads them
        import agents.skills.meta_review.evaluate_strategy_effectiveness  # noqa: F401
        import agents.skills.meta_review.propose_improvements  # noqa: F401
        import agents.skills.meta_review.review_agent_performance  # noqa: F401
        super().__init__(identity, llm, trust_weight)

    async def generate_post_mortem(
        self,
        agent_role: str,
        predictions: list[dict],
        brier_score: float,
        market_context: Optional[dict] = None,
        past_lessons: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """Generate a linguistic post-mortem analyzing decision quality.
        
        Evaluates whether the agent adhered to its mathematical constraints
        and domain expertise, IGNORING the final P&L. This prevents
        hindsight bias in the evolution loop.
        
        Args:
            agent_role: Role of the agent being reviewed
            predictions: Recent predictions with outcomes
            brier_score: Current rolling Brier score
            market_context: Market data snapshot at decision time
            past_lessons: Previously generated lessons from VectorStore
        """
        # Summarize prediction history
        total = len(predictions)
        wins = sum(1 for p in predictions if p.get("actual_outcome") == 1)
        losses = total - wins
        avg_confidence = (
            sum(p.get("confidence", 0.5) for p in predictions) / total
            if total > 0 else 0.5
        )
        
        # Build recent examples (last 5)
        recent_examples = ""
        for p in predictions[:5]:
            outcome = "WIN" if p.get("actual_outcome") == 1 else "LOSS"
            recent_examples += (
                f"  - {p.get('ticker', '?')}: predicted {p.get('predicted_probability', 0):.0%} "
                f"confidence, confidence={p.get('confidence', 0):.2f}, outcome={outcome}\n"
            )

        # Format past lessons for context
        past_lessons_text = ""
        if past_lessons:
            past_lessons_text = "\n\nPrevious Post-Mortems (from memory — do NOT repeat the same diagnosis):\n"
            for i, lesson in enumerate(past_lessons[:3], 1):
                lesson_text = lesson.get("text", "")[:200]
                lesson_brier = lesson.get("metadata", {}).get("brier_score", "?")
                past_lessons_text += f"  {i}. [Brier {lesson_brier}] {lesson_text}\n"
        
        context = {
            "agent_role": agent_role,
            "brier_score": f"{brier_score:.4f}",
            "total_predictions": total,
            "wins": wins,
            "losses": losses,
            "win_rate": f"{wins / total:.0%}" if total > 0 else "N/A",
            "avg_confidence": f"{avg_confidence:.2f}",
        }
        if market_context:
            context["market_regime"] = market_context.get("regime", "UNKNOWN")
        
        message = f"""Generate a post-mortem for the {agent_role} agent.

Performance Summary:
- Brier Score: {brier_score:.4f} (lower is better, 0.25 = random guessing)
- Record: {wins}W / {losses}L out of {total} predictions
- Average Confidence: {avg_confidence:.2f}

Recent Predictions:
{recent_examples}
{past_lessons_text}
Evaluate DECISION QUALITY, not just outcomes:
1. Was the agent calibrated? (Does confidence match actual win rate?)
2. Did the agent stay within its domain expertise?
3. Were there systematic biases? (e.g., always bullish, overconfident)
4. What specific behavioral change would improve calibration?
5. Is this a NEW issue or a RECURRING pattern from past post-mortems?

Output a structured post-mortem with:
- ASSESSMENT: One sentence summary (WELL_CALIBRATED, OVERCONFIDENT, UNDERCONFIDENT, BIASED)
- KEY_FINDING: The single most important observation
- RECOMMENDATION: One specific, actionable directive for the agent's Strategic_Nuance
- IS_RECURRING: Whether this issue appeared in previous post-mortems
"""
        return await self.invoke(message, context)

    async def propose_prompt_update(
        self,
        agent_role: str,
        current_nuance: str,
        brier_score: float,
        post_mortem: str,
        current_rules_count: int = 0,
    ) -> dict[str, Any]:
        """Propose a Strategic_Nuance update for an underperforming agent.
        
        The proposed update is validated by AgentUpdate's domain isolation
        validator before being applied — cross-domain terms will be rejected.
        
        Args:
            agent_role: Role of the agent to update
            current_nuance: Current Strategic_Nuance text
            brier_score: Current Brier score
            post_mortem: Post-mortem analysis text
            current_rules_count: Number of existing rules (max 3)
        """
        remaining_slots = MAX_RULES_PER_AGENT - current_rules_count
        
        context = {
            "agent_role": agent_role,
            "brier_score": f"{brier_score:.4f}",
            "current_rules_count": current_rules_count,
            "max_rules": MAX_RULES_PER_AGENT,
            "remaining_slots": max(0, remaining_slots),
        }
        
        message = f"""Propose a Strategic_Nuance update for the {agent_role} agent.

Current Strategic_Nuance:
{current_nuance if current_nuance else '(empty — no strategic directives yet)'}

Post-Mortem Analysis:
{post_mortem}

Current Brier Score: {brier_score:.4f}

RULES:
- You MUST output ONLY the new Strategic_Nuance text (the complete replacement)
- Maximum {MAX_RULES_PER_AGENT} bullet points (currently {current_rules_count} rules exist)
- If at max rules, CONSOLIDATE existing rules with the new insight into {MAX_RULES_PER_AGENT} points
- Each rule must be a specific, actionable trading directive
- NEVER include Identity_Core concepts — only strategic adjustments
- NEVER include terms from other domains (e.g., no 'RSI' for Fundamental Analyst)
- Format: bullet points starting with '- '

Output the complete new Strategic_Nuance text:
"""
        return await self.invoke(message, context)

    async def consolidate_rules(
        self,
        existing_rules: str,
        new_insight: str,
        agent_role: str,
    ) -> dict[str, Any]:
        """Consolidate rules when an agent is at max capacity.
        
        Synthesizes existing rules + new insight into a meta-rule set
        that stays within MAX_RULES_PER_AGENT limit.
        """
        context = {
            "agent_role": agent_role,
            "max_rules": MAX_RULES_PER_AGENT,
        }
        
        message = f"""The {agent_role} agent has reached its maximum of {MAX_RULES_PER_AGENT} rules.
Consolidate the existing rules with the new insight into exactly {MAX_RULES_PER_AGENT} bullet points.

Existing Rules:
{existing_rules}

New Insight to Incorporate:
{new_insight}

Output exactly {MAX_RULES_PER_AGENT} consolidated rules as bullet points.
Preserve the most impactful directives and merge overlapping ones.
"""
        return await self.invoke(message, context)

    def validate_proposed_nuance(
        self,
        agent_role: str,
        agent_name: str,
        proposed_nuance: str,
        version_number: int,
        change_description: str,
    ) -> tuple[bool, str]:
        """Validate a proposed Strategic_Nuance using Pydantic domain isolation.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            role_enum = AgentRole(agent_role)
            AgentUpdate(
                agent_name=agent_name,
                agent_role=role_enum,
                strategic_nuance=proposed_nuance,
                version_number=version_number,
                change_description=change_description,
            )
            return True, ""
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "content": f"Meta-Review Agent encountered an error: {error}",
            "status": "error",
            "error": error,
        }
