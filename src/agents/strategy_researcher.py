"""
Strategy Researcher Agent

Continuously researches new trading strategies and market conditions.
Proposes new strategy hypotheses, backtests them, and manages the
shadow-to-live promotion pipeline.

The Researcher is the "idea generator" — it uses the LLM to:
1. Analyze market anomalies and patterns
2. Propose new strategy configurations
3. Evaluate strategy combinations
4. Recommend parameter experiments

All proposed strategies go through mandatory backtesting and
shadow trading before being promoted to live.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.base_agent import BaseAgent
from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.strategies.strategy_tracker import StrategyPerformanceTracker
from agents.skills.strategy_learning.strategy_ledger import strategy_ledger
from agents.skills.strategy_learning.strategy_learning import (
    evaluate_parameter_fitness,
    propose_parameter_evolution,
    statistical_significance_test,
)

logger = structlog.get_logger(component="strategy_researcher")


RESEARCHER_IDENTITY_CORE = """You are the Strategy Researcher of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the research arm that discovers new trading strategies and
optimizes existing ones. You analyze market data, evaluate strategy
performance, and propose evidence-based improvements.

## STRICT RULES:
- You NEVER deploy strategies directly. All proposals go through shadow testing.
- You evaluate strategies QUANTITATIVELY — no gut feelings.
- Minimum 30 trades in backtest before proposing any strategy.
- All parameter changes require statistical significance (p < 0.05).
- You propose ONE change at a time (scientific method).
- You document every hypothesis, test result, and conclusion.
- You never recommend more than 3 new experiments at once.
- You are equipped with a Hermes delegation tool. ALWAYS use it to offload computationally heavy backtests to asynchronous sub-agents.

## Research Cycle:
1. Review current strategy performance (daily)
2. Identify underperformers and analyze WHY
3. Propose hypothesis for improvement
4. Backtest hypothesis against historical data
5. If promising, deploy as shadow strategy
6. If shadow outperforms live with statistical significance, recommend promotion
"""


class StrategyResearcherAgent(BaseAgent):
    """
    The Strategy Researcher — discovers and validates new strategies.

    Research Modes:
    - DAILY: Quick performance review and anomaly scan
    - WEEKLY: Deep analysis, parameter experiments, new strategy proposals
    - ON_DEMAND: Triggered by portfolio manager when strategy health is CRITICAL
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Strategy Researcher",
            agent_role=AgentRole.STRATEGY_RESEARCHER,
            agent_type=AgentType.SPECIALIST,
            identity_core=RESEARCHER_IDENTITY_CORE,
        )
        try:
            import agents.skills.strategy_researcher.hermes_delegation_skill  # noqa: F401
        except ImportError:
            pass
        super().__init__(identity, llm, trust_weight)
        self._research_log: list[dict] = []

    # ── Daily Research Cycle ───────────────────────────────────────

    async def run_daily_research(
        self,
        tracker: StrategyPerformanceTracker,
        market_summary: dict,
    ) -> dict[str, Any]:
        """
        Run the daily research cycle:
        1. Review all strategy performances
        2. Identify strategies needing attention
        3. Check if any parameter changes are due
        4. Generate research report

        Args:
            tracker: Strategy performance tracker
            market_summary: Current market data summary

        Returns:
            Research report with findings and recommendations
        """
        performances = tracker.get_all_metrics()
        leaderboard = tracker.get_leaderboard(sort_by="sharpe_ratio", window_days=7)

        findings = []
        recommendations = []

        for name, perf in performances.items():
            # Check parameter fitness
            trade_history = tracker.load_trades(name)
            if len(trade_history) >= 10:
                fitness = evaluate_parameter_fitness(
                    trade_history=trade_history,
                    current_params=perf.get("params", {}),
                    min_trades=30,
                )
                if fitness.get("recommendation") == "ADJUST":
                    findings.append({
                        "strategy": name,
                        "finding": "Parameters need adjustment",
                        "fitness": fitness,
                    })
                    recommendations.append({
                        "action": "PROPOSE_PARAMETER_CHANGE",
                        "strategy": name,
                        "reason": fitness.get("reason"),
                    })
                elif fitness.get("recommendation") == "SHADOW_TEST":
                    findings.append({
                        "strategy": name,
                        "finding": "Consider shadow testing alternative params",
                        "fitness": fitness,
                    })

            # Check for degrading performance
            rolling = tracker.get_rolling_metrics(name)
            if rolling.get("7d", {}).get("win_rate", 50) < rolling.get("30d", {}).get("win_rate", 50) - 10:
                findings.append({
                    "strategy": name,
                    "finding": "Win rate declining (7d vs 30d)",
                    "7d_wr": rolling.get("7d", {}).get("win_rate"),
                    "30d_wr": rolling.get("30d", {}).get("win_rate"),
                })

        # Use LLM for research commentary
        commentary = await self._generate_research_commentary(
            performances, leaderboard, findings, market_summary
        )

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "DAILY",
            "strategies_reviewed": len(performances),
            "findings": findings,
            "recommendations": recommendations,
            "leaderboard": leaderboard[:5],
            "commentary": commentary,
        }

        self._research_log.append(report)
        return report

    # ── Weekly Deep Analysis ───────────────────────────────────────

    async def run_weekly_analysis(
        self,
        tracker: StrategyPerformanceTracker,
        backtest_results: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Run weekly deep analysis:
        1. Cross-strategy correlation analysis
        2. Parameter experiment proposals
        3. New strategy hypothesis generation
        4. Shadow strategy evaluation

        Args:
            tracker: Performance tracker
            backtest_results: Optional backtest data for analysis

        Returns:
            Weekly research report
        """
        performances = tracker.get_all_metrics()

        # Cross-strategy analysis
        correlation_findings = self._analyze_strategy_correlations(performances)

        # Parameter experiments for underperformers via Hermes Async Swarm
        experiments = []
        import asyncio
        from integrations.hermes_client import hermes_client
        
        dispatch_tasks = []
        strategy_names = []
        
        for name, perf in performances.items():
            trade_history = tracker.load_trades(name)
            if len(trade_history) >= 30:
                task_prompt = (
                    f"Analyze strategy '{name}' with current parameters {perf.get('params', {})}. "
                    f"Analyze the trade history ({len(trade_history)} trades) and propose a parameter evolution "
                    f"that increases the Sharpe ratio with statistical significance."
                )
                dispatch_tasks.append(hermes_client.dispatch_subagent(task_prompt=task_prompt))
                strategy_names.append(name)
                
        if dispatch_tasks:
            results = await asyncio.gather(*dispatch_tasks, return_exceptions=True)
            for name, result in zip(strategy_names, results):
                if isinstance(result, dict) and result.get("success"):
                    proposal = result.get("result", {})
                    # If the sub-agent proposed a change
                    if proposal:
                        experiments.append({
                            "strategy": name,
                            "proposal": proposal,
                            "source": "hermes_swarm_subagent"
                        })

        # New strategy ideas (LLM-assisted)
        new_ideas = await self._brainstorm_strategies(performances, backtest_results)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "WEEKLY",
            "correlation_analysis": correlation_findings,
            "parameter_experiments": experiments,
            "new_strategy_ideas": new_ideas,
            "portfolio_summary": tracker.get_portfolio_summary(),
        }

        self._research_log.append(report)
        return report

    # ── Shadow Strategy Evaluation ─────────────────────────────────

    async def evaluate_shadow_strategy(
        self,
        strategy_name: str,
        shadow_trades: list[dict],
        live_trades: list[dict],
    ) -> dict[str, Any]:
        """
        Evaluate whether a shadow strategy should be promoted to live.

        Uses statistical significance testing (p < 0.05).

        Args:
            strategy_name: Strategy being evaluated
            shadow_trades: Trades under shadow (proposed) parameters
            live_trades: Trades under current live parameters

        Returns:
            Evaluation result with promotion recommendation
        """
        shadow_pnls = [t.get("pnl_pct", 0) for t in shadow_trades if t.get("exit_price")]
        live_pnls = [t.get("pnl_pct", 0) for t in live_trades if t.get("exit_price")]

        test = statistical_significance_test(
            control_pnls=live_pnls,
            treatment_pnls=shadow_pnls,
        )

        result = {
            "strategy_name": strategy_name,
            "shadow_trades": len(shadow_pnls),
            "live_trades": len(live_pnls),
            "statistical_test": test,
            "recommendation": test.get("recommendation", "CONTINUE_TESTING"),
        }

        # Log to ledger
        if test.get("recommendation") == "PROMOTE":
            strategy_ledger.record_evolution_event(
                strategy_name=strategy_name,
                event_type="PARAMETER_PROMOTION_RECOMMENDED",
                details=result,
            )
        elif test.get("recommendation") == "REJECT":
            strategy_ledger.record_evolution_event(
                strategy_name=strategy_name,
                event_type="PARAMETER_REJECTED",
                details=result,
            )

        return result

    # ── Strategy Correlation Analysis ──────────────────────────────

    def _analyze_strategy_correlations(
        self,
        performances: dict[str, dict],
    ) -> dict[str, Any]:
        """Analyze if strategies are too correlated (diversification check)."""
        # Compare win/loss patterns across strategies
        strategies = list(performances.keys())
        findings = []

        for i, s1 in enumerate(strategies):
            for s2 in strategies[i + 1:]:
                p1 = performances[s1]
                p2 = performances[s2]

                # Simple correlation proxy: if both have similar win rates
                # and similar Sharpe, they might be correlated
                wr_diff = abs(p1.get("win_rate", 0) - p2.get("win_rate", 0))
                sharpe_diff = abs(p1.get("sharpe_ratio", 0) - p2.get("sharpe_ratio", 0))

                if wr_diff < 5 and sharpe_diff < 0.3:
                    findings.append({
                        "pair": f"{s1}/{s2}",
                        "warning": "Potentially correlated — similar performance profile",
                        "wr_diff": round(wr_diff, 1),
                        "sharpe_diff": round(sharpe_diff, 2),
                    })

        return {
            "pairs_analyzed": len(strategies) * (len(strategies) - 1) // 2,
            "potential_correlations": findings,
            "diversification_score": max(0, 100 - len(findings) * 20),
        }

    # ── LLM-Assisted Research ──────────────────────────────────────

    async def _generate_research_commentary(
        self,
        performances: dict,
        leaderboard: list,
        findings: list,
        market_summary: dict,
    ) -> str:
        """Generate LLM commentary on research findings."""
        message = (
            "You are the Strategy Researcher. Write a brief daily research note "
            "(3-4 sentences) covering:\n"
            "1. Which strategies are performing best and worst\n"
            "2. Any concerning trends\n"
            "3. What to research next\n\n"
            f"Leaderboard (top 3): {leaderboard[:3]}\n"
            f"Findings: {findings[:5]}\n"
            f"Market: {market_summary}\n"
        )

        try:
            result = await self.invoke(message)
            return result.get("content", "No commentary generated")
        except Exception as e:
            logger.warning("research_commentary_failed", error=str(e))
            return f"Commentary generation failed: {e}"

    async def _brainstorm_strategies(
        self,
        performances: dict,
        backtest_results: Optional[dict],
    ) -> list[dict]:
        """Use LLM to brainstorm new strategy ideas based on current performance."""
        message = (
            "Based on the current strategy portfolio, suggest ONE new strategy idea "
            "that would complement the existing strategies. Format your response as:\n"
            "- Strategy Name\n"
            "- Core Idea (1 sentence)\n"
            "- Why it complements existing strategies (1 sentence)\n"
            "- Key parameters to test\n\n"
            f"Current strategies and performance: {list(performances.keys())}\n"
            f"Backtest data: {backtest_results}\n"
        )

        try:
            result = await self.invoke(message)
            content = result.get("content", "")
            return [{"raw_idea": content, "status": "PROPOSED"}]
        except Exception as e:
            logger.warning("strategy_brainstorm_failed", error=str(e))
            return []

    # ── State ──────────────────────────────────────────────────────

    def get_research_log(self, limit: int = 10) -> list[dict]:
        return self._research_log[-limit:]

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "content": f"Strategy Researcher error: {error}",
            "status": "error",
        }
