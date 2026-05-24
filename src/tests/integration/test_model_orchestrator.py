"""
Integration tests for the Model Orchestrator and Agent Spawner.
"""

import pytest

from agents.model_orchestrator import orchestrator, ModelOrchestrator
from core.models.agents import AgentRole
from config.constants import EFFICIENT_TIER_MODELS, PREMIUM_TIER_MODELS
from evolution.agent_spawner import AgentSpawner

def test_orchestrator_initial_assignment():
    """Test that the orchestrator assigns models correctly based on agent type."""
    # Reset internal state for test
    test_orchestrator = ModelOrchestrator()
    
    # Executive -> Premium tier
    model = test_orchestrator.get_optimal_model_for_agent(AgentRole.CTO.value, "EXECUTIVE", exploration_rate=0.0)
    assert model in PREMIUM_TIER_MODELS
    
    # Analyst -> Efficient tier
    model = test_orchestrator.get_optimal_model_for_agent(AgentRole.TECHNICAL_ANALYST.value, "ANALYST", exploration_rate=0.0)
    assert model in EFFICIENT_TIER_MODELS

def test_orchestrator_exploitation():
    """Test that the orchestrator learns to pick the best model after multiple executions."""
    test_orchestrator = ModelOrchestrator()
    role = AgentRole.FUNDAMENTAL_ANALYST.value
    type_val = "ANALYST"
    
    model_a = EFFICIENT_TIER_MODELS[0]
    model_b = EFFICIENT_TIER_MODELS[1] if len(EFFICIENT_TIER_MODELS) > 1 else model_a
    
    # Initialize cache for this role
    test_orchestrator.get_optimal_model_for_agent(role, type_val, exploration_rate=0.0)

    # Record poor performance for model_a
    for _ in range(10):
        test_orchestrator.record_execution_result(role, model_a, success=False, cost_usd=0.01, latency_sec=1.0)
        
    # Record excellent performance for model_b
    for _ in range(10):
        test_orchestrator.record_execution_result(role, model_b, success=True, cost_usd=0.01, latency_sec=1.0)
        
    # Record poor performance for any other models to avoid them getting the 1.0 untested default
    for m in EFFICIENT_TIER_MODELS:
        if m not in [model_a, model_b]:
            for _ in range(10):
                test_orchestrator.record_execution_result(role, m, success=False, cost_usd=0.01, latency_sec=1.0)

    # Ask for optimal model (exploration=0 to force exploitation)
    best_model = test_orchestrator.get_optimal_model_for_agent(role, type_val, exploration_rate=0.0)
    
    if len(EFFICIENT_TIER_MODELS) > 1:
        assert best_model == model_b

def test_agent_spawner_integration():
    """Test that AgentSpawner uses the orchestrator when creating agents."""
    spawner = AgentSpawner()
    
    # Spawn an analyst (using a defined template)
    agent = spawner.spawn_agent(AgentRole.DEVELOPER)
    
    # Check that an LLM model was assigned
    assert agent.llm_model is not None
    assert agent.llm_model in EFFICIENT_TIER_MODELS

    # Spawn an executive
    exec_agent = spawner.spawn_agent(AgentRole.CTO)
    assert exec_agent.llm_model is not None
    assert exec_agent.llm_model in PREMIUM_TIER_MODELS
