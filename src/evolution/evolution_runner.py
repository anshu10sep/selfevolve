"""
Evolution Runner

The main orchestrator for the self-evolution cycle. Coordinates:
1. Brier score computation → trust weight updates
2. Post-mortem analysis for underperforming agents
3. Prompt mutation proposals → domain isolation validation
4. Shadow Crew A/B testing → statistical promotion

Run frequency: Daily via _run_post_market_evolution()

Safety invariants:
- Identity_Core is NEVER modified (only Strategic_Nuance)
- Domain isolation is enforced via Pydantic validators
- Prompt promotion requires p < 0.05 statistical significance
- Minimum SHADOW_MIN_TRADES before evaluation
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from config.constants import (
    BRIER_WINDOW_SIZE,
    SHADOW_MIN_TRADES,
    EVOLUTION_P_VALUE_THRESHOLD,
    MAX_RULES_PER_AGENT,
)
from core.llm_factory import get_efficient_llm
from evolution.reflexion import BrierScoreEngine, PromptEvolution
from evolution.prediction_tracker import prediction_tracker
from evolution.trust_updater import (
    update_all_trust_weights,
    SCORABLE_ROLES,
    ROLE_NAMES,
    BRIER_POOR,
)
from persistence.db import (
    get_agent_scores,
    get_active_prompt,
    get_pending_prompt_versions,
    get_latest_prompt_version_number,
    create_prompt_version,
    promote_prompt_version,
    discard_prompt_version,
    get_predictions_for_prompt_version,
    create_evolution_event,
)

logger = structlog.get_logger(component="evolution_runner")


class EvolutionRunner:
    """Orchestrates the full self-evolution cycle."""

    def __init__(self):
        self._meta_review = None  # Lazy-loaded to avoid import cycles
        self._vector_store = None  # Lazy-loaded VectorStore

    def _get_meta_review(self):
        """Lazy-load MetaReviewAgent to avoid circular imports."""
        if self._meta_review is None:
            from agents.meta_review_agent import MetaReviewAgent
            llm = get_efficient_llm()
            self._meta_review = MetaReviewAgent(llm)
        return self._meta_review

    def _get_vector_store(self):
        """Lazy-load VectorStore singleton."""
        if self._vector_store is None:
            from memory.vector_store import get_vector_store
            self._vector_store = get_vector_store()
        return self._vector_store

    async def run_full_cycle(self) -> dict[str, Any]:
        """Run the complete evolution cycle.
        
        Steps:
        1. Update trust weights for all agents (Brier scores)
        2. Identify underperforming agents (Brier > 0.35 or trust < 0.5)
        3. Generate post-mortems for underperformers
        4. Propose prompt mutations
        5. Validate via domain isolation
        6. Store candidates for Shadow Crew testing
        7. Evaluate any mature Shadow Crew tests
        
        Returns:
            Evolution report dict for Telegram/dashboard
        """
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trust_updates": {},
            "post_mortems": [],
            "prompt_proposals": [],
            "shadow_evaluations": [],
            "errors": [],
        }

        # Step 1: Update trust weights
        try:
            trust_report = update_all_trust_weights()
            report["trust_updates"] = trust_report
            # Publish trust update events to Event Bus
            await self._publish_evolution_event(
                "TRUST_WEIGHTS_UPDATED",
                {
                    "agents_updated": trust_report.get("agents_updated", 0),
                    "agents_evaluated": trust_report.get("agents_evaluated", 0),
                },
            )
        except Exception as e:
            logger.error("trust_update_phase_failed", error=str(e))
            report["errors"].append(f"Trust update failed: {e}")

        # Step 2: Identify underperformers
        underperformers = self._identify_underperformers()
        
        # Step 3-6: Process each underperformer
        for role, data in underperformers.items():
            try:
                result = await self._evolve_agent(role, data)
                if result.get("post_mortem"):
                    report["post_mortems"].append(result["post_mortem"])
                if result.get("prompt_proposal"):
                    report["prompt_proposals"].append(result["prompt_proposal"])
            except Exception as e:
                logger.error("agent_evolution_failed", agent=role, error=str(e))
                report["errors"].append(f"{role}: {e}")

        # Step 7: Evaluate mature Shadow Crew tests
        try:
            shadow_results = await self._evaluate_shadow_tests()
            report["shadow_evaluations"] = shadow_results
        except Exception as e:
            logger.error("shadow_evaluation_failed", error=str(e))
            report["errors"].append(f"Shadow evaluation failed: {e}")

        logger.info(
            "evolution_cycle_complete",
            underperformers=len(underperformers),
            proposals=len(report["prompt_proposals"]),
            shadow_evals=len(report["shadow_evaluations"]),
            errors=len(report["errors"]),
        )

        return report

    def _identify_underperformers(self) -> dict[str, dict]:
        """Find agents with poor Brier scores or low trust weights."""
        scores = {s["role"]: s for s in get_agent_scores()}
        underperformers = {}

        for role in SCORABLE_ROLES:
            data = scores.get(role, {})
            brier = data.get("brier_score")
            trust = data.get("trust_weight", 1.0)

            # Underperformer criteria
            if brier is not None and (brier > BRIER_POOR or trust < 0.5):
                underperformers[role] = {
                    "brier_score": brier,
                    "trust_weight": trust,
                    "name": ROLE_NAMES.get(role, role),
                }
                logger.info(
                    "underperformer_identified",
                    agent=role,
                    brier=f"{brier:.4f}",
                    trust=f"{trust:.3f}",
                )

        return underperformers

    async def _evolve_agent(self, role: str, data: dict) -> dict[str, Any]:
        """Run the evolution pipeline for a single underperforming agent."""
        result = {"post_mortem": None, "prompt_proposal": None}
        meta = self._get_meta_review()
        vs = self._get_vector_store()
        name = data["name"]
        brier = data["brier_score"]

        # Get recent predictions for context
        predictions = prediction_tracker.get_resolved_predictions(
            agent_role=role, window=BRIER_WINDOW_SIZE,
        )

        if len(predictions) < 5:
            logger.info("skipping_evolution_insufficient_data", agent=role, count=len(predictions))
            return result

        # ── Get Current Market Regime ───────────────────────────────────
        market_regime = "UNKNOWN"
        try:
            from integrations.market_data import MarketDataClient
            from agents.skills.strategy_learning.regime_detection import detect_market_regime
            mdc = MarketDataClient()
            bars = await mdc.get_bars("SPY", limit=50)
            await mdc.close()
            if len(bars) >= 50:
                closes = [b["close"] for b in bars]
                highs = [b["high"] for b in bars]
                lows = [b["low"] for b in bars]
                volumes = [b["volume"] for b in bars]
                regime_data = detect_market_regime(closes, highs, lows, volumes)
                market_regime = regime_data.get("regime", "UNKNOWN")
        except Exception as e:
            logger.debug("market_regime_fetch_failed", error=str(e))

        # ── Retrieve past lessons from VectorStore ──────────────────
        # This prevents the MetaReview from proposing changes that
        # have already been tried and failed.
        past_lessons = []
        past_rules = []
        try:
            past_lessons = await vs.retrieve_relevant(
                query_text=f"{role} underperforming brier {brier} in {market_regime}",
                metadata_filters={"agent_role": role},
                limit=3,
            )
            past_rules = await vs.retrieve_rule_history(
                agent_role=role,
                status="DISCARDED",
                limit=3,
            )
            logger.info(
                "past_context_retrieved",
                agent=role,
                lessons=len(past_lessons),
                discarded_rules=len(past_rules),
            )
        except Exception as e:
            logger.debug("past_context_retrieval_failed", agent=role, error=str(e))

        # Step 3: Generate post-mortem
        try:
            post_mortem_result = await meta.generate_post_mortem(
                agent_role=role,
                predictions=predictions,
                brier_score=brier,
                past_lessons=past_lessons,
            )
            post_mortem_text = self._extract_text(post_mortem_result)
            result["post_mortem"] = {
                "agent": role,
                "name": name,
                "brier_score": brier,
                "analysis": post_mortem_text[:500],
            }
            logger.info("post_mortem_generated", agent=role, length=len(post_mortem_text))

            # ── Store post-mortem in VectorStore ────────────────────
            try:
                await vs.store_postmortem(
                    agent_id=role,
                    trade_id=str(uuid.uuid4()),
                    postmortem_text=post_mortem_text,
                    metadata={
                        "agent_role": role,
                        "brier_score": brier,
                        "market_regime": market_regime,
                        "prediction_count": len(predictions),
                    },
                )
                logger.info("post_mortem_stored_in_vector_store", agent=role)
            except Exception as e:
                logger.debug("post_mortem_storage_failed", agent=role, error=str(e))

        except Exception as e:
            logger.error("post_mortem_failed", agent=role, error=str(e))
            return result

        # Step 4: Propose prompt update
        try:
            # Get current nuance
            active_prompt = get_active_prompt(role)
            current_nuance = active_prompt["prompt_text"] if active_prompt else ""
            current_rules_count = current_nuance.count("- ") if current_nuance else 0

            # Format past failed rules for MetaReview context
            failed_rules_context = ""
            if past_rules:
                failed_rules_context = "\nPreviously DISCARDED rules (DO NOT repeat these):\n"
                for pr in past_rules:
                    meta_data = pr.get("metadata", {})
                    failed_rules_context += (
                        f"  - v{meta_data.get('version', '?')}: "
                        f"{meta_data.get('nuance_text', '')[:150]}\n"
                    )

            proposal_result = await meta.propose_prompt_update(
                agent_role=role,
                current_nuance=current_nuance,
                brier_score=brier,
                post_mortem=post_mortem_text + failed_rules_context,
                current_rules_count=min(current_rules_count, MAX_RULES_PER_AGENT),
            )
            proposed_nuance = self._extract_text(proposal_result)
        except Exception as e:
            logger.error("prompt_proposal_failed", agent=role, error=str(e))
            return result

        # Step 5: Validate via domain isolation
        next_version = get_latest_prompt_version_number(role) + 1
        change_desc = f"Evolution cycle: Brier {brier:.4f}, post-mortem driven update"
        
        is_valid, error = meta.validate_proposed_nuance(
            agent_role=role,
            agent_name=name,
            proposed_nuance=proposed_nuance,
            version_number=next_version,
            change_description=change_desc,
        )

        if not is_valid:
            logger.warning(
                "prompt_proposal_rejected_domain_isolation",
                agent=role, error=error,
            )
            result["prompt_proposal"] = {
                "agent": role, "status": "REJECTED",
                "reason": f"Domain isolation: {error}",
            }
            return result

        # Step 6: Store candidate for Shadow Crew testing
        try:
            pv = create_prompt_version(
                id=str(uuid.uuid4()),
                agent_role=role,
                version_number=next_version,
                prompt_text=proposed_nuance,
                change_description=change_desc,
                brier_before=brier,
                is_active=False,  # Not active until promoted
            )
            result["prompt_proposal"] = {
                "agent": role, "name": name,
                "status": "CANDIDATE",
                "version": next_version,
                "change": change_desc,
                "nuance_preview": proposed_nuance[:200],
            }

            # Log evolution event
            create_evolution_event(
                id=str(uuid.uuid4()),
                event_type="PROMPT_UPDATE",
                description=f"Candidate prompt v{next_version} created for {name}",
                agent_role=role,
                details={
                    "version": next_version,
                    "brier_before": brier,
                    "nuance_length": len(proposed_nuance),
                },
            )

            # ── Store rule evolution in VectorStore ─────────────────
            try:
                await vs.store_rule_evolution(
                    agent_role=role,
                    version=next_version,
                    nuance_text=proposed_nuance,
                    change_description=change_desc,
                    brier_before=brier,
                    status="CANDIDATE",
                )
            except Exception as e:
                logger.debug("rule_evolution_storage_failed", error=str(e))

            logger.info(
                "prompt_candidate_created",
                agent=role, version=next_version,
                nuance_length=len(proposed_nuance),
            )

            # Publish to Event Bus
            await self._publish_evolution_event(
                "PROMPT_CANDIDATE_CREATED",
                {
                    "agent_role": role,
                    "agent_name": name,
                    "version": next_version,
                    "brier_before": brier,
                },
            )
        except Exception as e:
            logger.error("prompt_storage_failed", agent=role, error=str(e))

        return result

    async def _evaluate_shadow_tests(self) -> list[dict]:
        """Evaluate mature Shadow Crew A/B tests.
        
        For each pending prompt version that has enough predictions,
        compare shadow vs production results using Welch's t-test.
        """
        evaluations = []

        for role in SCORABLE_ROLES:
            pending = get_pending_prompt_versions(role)
            for pv in pending:
                try:
                    eval_result = await self._evaluate_single_shadow(role, pv)
                    if eval_result:
                        evaluations.append(eval_result)
                except Exception as e:
                    logger.error(
                        "shadow_test_evaluation_failed",
                        agent=role, version=pv["version_number"],
                        error=str(e),
                    )

        return evaluations

    async def _evaluate_single_shadow(self, role: str, pending_version: dict) -> Optional[dict]:
        """Evaluate a single shadow vs production comparison."""
        version = pending_version["version_number"]
        name = ROLE_NAMES.get(role, role)

        # Get shadow predictions for this version
        shadow_preds = get_predictions_for_prompt_version(
            agent_role=role, prompt_version=version, resolved_only=True,
        )

        if len(shadow_preds) < SHADOW_MIN_TRADES:
            # Not enough data yet
            return None

        # Get production predictions (non-shadow, active version)
        prod_preds = prediction_tracker.get_resolved_predictions(
            agent_role=role, window=len(shadow_preds), is_shadow=False,
        )

        if len(prod_preds) < SHADOW_MIN_TRADES:
            return None

        # Extract Brier-style results for comparison
        # Use prediction errors as the metric: lower = better
        shadow_errors = [
            (p["predicted_probability"] - p["actual_outcome"]) ** 2
            for p in shadow_preds
            if p.get("actual_outcome") is not None
        ]
        prod_errors = [
            (p["predicted_probability"] - p["actual_outcome"]) ** 2
            for p in prod_preds
            if p.get("actual_outcome") is not None
        ]

        if len(shadow_errors) < 5 or len(prod_errors) < 5:
            return None

        # Run statistical test
        # Note: For errors, lower is better, so we invert for the significance test
        # We want to test if shadow has LOWER errors than production
        sig_result = PromptEvolution.evaluate_significance(
            production_results=prod_errors,
            shadow_results=shadow_errors,
        )

        # Also compute Brier scores for reporting
        shadow_brier = sum(shadow_errors) / len(shadow_errors)
        prod_brier = sum(prod_errors) / len(prod_errors)

        recommendation = sig_result["recommendation"]
        p_value = sig_result["p_value"]

        # For error metrics, shadow_mean < production_mean = improvement
        # The significance test checks if shadow_mean > production_mean
        # So we need to invert the recommendation for error metrics
        if recommendation == "PROMOTE":
            # Shadow has significantly HIGHER errors → actually worse
            recommendation = "ROLLBACK"
        elif recommendation == "ROLLBACK":
            # Shadow has significantly LOWER errors → actually better
            recommendation = "PROMOTE"

        result = {
            "agent": role,
            "name": name,
            "version": version,
            "shadow_brier": round(shadow_brier, 4),
            "production_brier": round(prod_brier, 4),
            "p_value": p_value,
            "significant": sig_result["significant"],
            "recommendation": recommendation,
            "shadow_trades": len(shadow_errors),
            "production_trades": len(prod_errors),
        }

        # Act on the recommendation
        if recommendation == "PROMOTE":
            promoted = promote_prompt_version(role, version, p_value)
            if promoted:
                result["action"] = "PROMOTED"
                create_evolution_event(
                    id=str(uuid.uuid4()),
                    event_type="SHADOW_PROMOTION",
                    description=(
                        f"{name} v{version} PROMOTED: shadow Brier {shadow_brier:.4f} < "
                        f"prod Brier {prod_brier:.4f} (p={p_value:.4f})"
                    ),
                    agent_role=role,
                    details=result,
                )
                logger.info(
                    "shadow_prompt_promoted",
                    agent=role, version=version,
                    shadow_brier=f"{shadow_brier:.4f}",
                    prod_brier=f"{prod_brier:.4f}",
                    p_value=f"{p_value:.4f}",
                )

                # ── Gap 5 Fix: Apply promoted prompt to LIVE agent instance ──
                # Without this, the promoted prompt only takes effect after
                # a system restart. Now it's applied immediately at runtime.
                try:
                    from agents.skills.jarvis.agent_messaging import get_registered_agents
                    live_agents = get_registered_agents()
                    # Try multiple key formats: role key, role lowercase, name lowercase
                    role_keys = [
                        role.lower(),
                        role.lower().replace("_", " "),
                        name.lower(),
                        name.lower().replace(" ", "_"),
                    ]
                    for key in role_keys:
                        agent = live_agents.get(key)
                        if agent and hasattr(agent, 'update_strategic_nuance'):
                            prompt_text = pending_version.get("prompt_text", "")
                            if prompt_text:
                                agent.update_strategic_nuance(prompt_text, version)
                                logger.info(
                                    "live_agent_prompt_updated",
                                    agent=role, version=version,
                                    registry_key=key,
                                )
                                result["live_agent_updated"] = True
                            break
                    else:
                        logger.debug(
                            "live_agent_not_found_for_prompt_update",
                            agent=role,
                            tried_keys=role_keys,
                            message="Prompt will take effect after restart",
                        )
                except Exception as prompt_apply_err:
                    logger.warning(
                        "live_prompt_application_failed",
                        agent=role, error=str(prompt_apply_err),
                        message="Prompt promoted in DB; will apply on restart",
                    )

                # Publish promotion event
                await self._publish_evolution_event(
                    "SHADOW_PROMOTED",
                    {
                        "agent_role": role,
                        "agent": name,
                        "version": version,
                        "p_value": p_value,
                        "shadow_brier": round(shadow_brier, 4),
                        "prod_brier": round(prod_brier, 4),
                    },
                )
        elif recommendation == "ROLLBACK":
            discarded = discard_prompt_version(role, version, p_value)
            if discarded:
                result["action"] = "DISCARDED"
                logger.info(
                    "shadow_prompt_discarded",
                    agent=role, version=version,
                    p_value=f"{p_value:.4f}",
                )
                # Publish discard event
                await self._publish_evolution_event(
                    "SHADOW_DISCARDED",
                    {
                        "agent_role": role,
                        "agent": name,
                        "version": version,
                        "p_value": p_value,
                    },
                )
        else:
            result["action"] = "CONTINUE_TESTING"

        return result

    def format_telegram_report(self, report: dict) -> str:
        """Format evolution report for Telegram notification."""
        lines = ["🧬 *Evolution Cycle Report*\n"]

        # Trust updates
        trust = report.get("trust_updates", {})
        if trust.get("agents_updated", 0) > 0:
            lines.append(f"📊 Trust weights updated for {trust['agents_updated']} agents")
            for role, data in trust.get("results", {}).items():
                if data.get("updated"):
                    emoji = "📈" if data["direction"] == "IMPROVED" else "📉" if data["direction"] == "DECAYED" else "➡️"
                    lines.append(
                        f"  {emoji} {ROLE_NAMES.get(role, role)}: "
                        f"Brier `{data['brier_score']:.4f}` | "
                        f"Trust `{data['old_trust']:.3f}→{data['new_trust']:.3f}`"
                    )

        # Post-mortems
        mortems = report.get("post_mortems", [])
        if mortems:
            lines.append(f"\n🔍 Post-mortems: {len(mortems)}")
            for pm in mortems[:3]:
                lines.append(f"  - {pm['name']}: {pm['analysis'][:100]}...")

        # Prompt proposals
        proposals = report.get("prompt_proposals", [])
        if proposals:
            lines.append(f"\n🔧 Prompt candidates: {len(proposals)}")
            for pp in proposals:
                status = pp.get("status", "?")
                emoji = "✅" if status == "CANDIDATE" else "❌"
                lines.append(f"  {emoji} {pp.get('name', pp['agent'])}: {status}")

        # Shadow evaluations
        shadows = report.get("shadow_evaluations", [])
        if shadows:
            lines.append(f"\n🧪 Shadow Crew evaluations: {len(shadows)}")
            for se in shadows:
                action = se.get("action", "?")
                emoji = "🏆" if action == "PROMOTED" else "🗑" if action == "DISCARDED" else "⏳"
                lines.append(
                    f"  {emoji} {se['name']} v{se['version']}: {action} "
                    f"(p={se['p_value']:.4f})"
                )

        # Errors
        errors = report.get("errors", [])
        if errors:
            lines.append(f"\n⚠️ Errors: {len(errors)}")

        return "\n".join(lines)

    @staticmethod
    def _extract_text(result: Any) -> str:
        """Extract text content from an LLM result."""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get("content", str(result))
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, list):
                return " ".join(str(c) for c in content)
            return str(content)
        return str(result)

    async def _publish_evolution_event(
        self, event_type: str, data: dict
    ) -> None:
        """Publish an evolution event to the Event Bus (safe — no-ops if unavailable)."""
        try:
            from core.event_bus import EventBus, EventChannels, Event
            from persistence.redis_client import get_redis_client
            redis = await get_redis_client()
            bus = EventBus(redis)
            event = Event(event_type=event_type, data=data, source="evolution_runner")
            await bus.publish(EventChannels.EVOLUTION_EVENTS, event)
        except Exception as e:
            # Event publishing is best-effort — never block evolution
            logger.debug("evolution_event_publish_failed", event_type=event_type, error=str(e))


# Singleton instance
evolution_runner = EvolutionRunner()
