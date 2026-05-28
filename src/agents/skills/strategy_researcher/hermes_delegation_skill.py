"""
Hermes Delegation Skill for Strategy Researcher

Allows the Strategy Researcher to offload computationally heavy parameter
testing and hypothesis backtesting to an asynchronous swarm of Hermes sub-agents.
"""

from __future__ import annotations

import logging
import json

from agents.skills.jarvis.agent_messaging import _skill_registry
from integrations.hermes_client import hermes_client

logger = logging.getLogger("hermes_delegation_skill")

async def delegate_backtest_to_hermes(strategy_name: str, parameters: dict, historical_data_summary: dict = None) -> str:
    """
    Dispatch an asynchronous Hermes sub-agent to backtest a parameter combination.
    
    Use this tool when you have formulated a hypothesis and need to test it
    across historical data without blocking the main execution loop.
    
    Args:
        strategy_name: The name of the strategy to backtest.
        parameters: The specific parameter combination to evaluate.
        historical_data_summary: Relevant market condition data for the test.
        
    Returns:
        A string containing the sub-agent's analysis of the backtest.
    """
    logger.info(f"Strategy Researcher delegating backtest for {strategy_name}")
    
    task_prompt = (
        f"Perform an intensive historical backtest for strategy '{strategy_name}' "
        f"using the following proposed parameters: {json.dumps(parameters)}. "
        f"Evaluate the Sharpe ratio, maximum drawdown, and win rate. "
        f"Provide a statistical significance determination (p < 0.05) if these "
        f"parameters outperform the baseline."
    )
    
    context = {
        "strategy": strategy_name,
        "parameters": parameters,
        "market_context": historical_data_summary or {}
    }
    
    result = await hermes_client.dispatch_subagent(
        task_prompt=task_prompt, 
        context=context,
        timeout=300 # 5 minutes for backtest
    )
    
    if result.get("success"):
        subagent_result = result.get("result", {})
        analysis = subagent_result.get("analysis", "No detailed analysis provided by subagent.")
        return f"Subagent Backtest Completed:\n{analysis}"
    else:
        error = result.get("error", "Unknown error")
        logger.error(f"Delegation failed for {strategy_name}: {error}")
        return f"Failed to complete delegated backtest. Error: {error}"


# Register the skill for the Strategy Researcher
_skill_registry.register_skill(
    "strategy_researcher",
    "delegate_backtest_to_hermes",
    delegate_backtest_to_hermes,
    description="Dispatch an asynchronous Hermes sub-agent to backtest strategy parameters without blocking the main loop."
)
