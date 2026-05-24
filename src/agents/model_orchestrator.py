"""
Model Orchestrator Agent

Dynamically evaluates and switches LLMs (Gemini, GPT, Claude) for different
agents based on A/B testing and performance metrics.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Dict, List, Optional
import structlog
from pydantic import BaseModel, Field

from config.constants import EFFICIENT_TIER_MODELS, PREMIUM_TIER_MODELS
from core.llm_factory import get_llm_by_name

logger = structlog.get_logger(component="model_orchestrator")

class ModelPerformanceMetrics(BaseModel):
    """Tracks performance of a specific model for a specific agent role."""
    model_name: str
    agent_role: str
    total_executions: int = 0
    successful_executions: int = 0
    total_cost_usd: float = 0.0
    average_latency_sec: float = 0.0
    cumulative_brier_score: float = 0.0
    win_rate: float = 0.0
    
    @property
    def cost_adjusted_performance(self) -> float:
        """Heuristic: Win rate divided by cost per execution (with baseline protection)"""
        cost_per_exec = self.total_cost_usd / max(1, self.total_executions)
        return self.win_rate / max(0.0001, cost_per_exec)

class ModelOrchestrator:
    """
    Agent responsible for model routing and A/B testing.
    """
    
    def __init__(self):
        # In-memory tracking (in production, this syncs with DB)
        self._metrics_cache: Dict[str, Dict[str, ModelPerformanceMetrics]] = {}
        # Format: { 'agent_role': { 'model_name': Metrics } }

    def get_optimal_model_for_agent(self, agent_role: str, agent_type: str, exploration_rate: float = 0.1) -> str:
        """
        Returns the best model name to use for the given agent role.
        Exploration rate determines how often to test a random valid model.
        """
        # Determine candidate models based on agent type
        if agent_type in ["EXECUTIVE", "MANAGER"]:
            candidates = PREMIUM_TIER_MODELS
        else:
            candidates = EFFICIENT_TIER_MODELS

        # Initialize tracking if new
        if agent_role not in self._metrics_cache:
            self._metrics_cache[agent_role] = {
                model: ModelPerformanceMetrics(model_name=model, agent_role=agent_role)
                for model in candidates
            }

        # Exploration phase
        if random.random() < exploration_rate:
            selected_model = random.choice(candidates)
            logger.info("model_exploration", agent_role=agent_role, selected_model=selected_model)
            return selected_model

        # Exploitation phase (pick highest performing model based on metrics)
        # Note: If no executions, default to first candidate
        best_model = candidates[0]
        best_score = -1.0
        
        for model_name, metrics in self._metrics_cache[agent_role].items():
            if metrics.total_executions < 5:
                # Give new models a baseline chance before judging them strictly
                score = 1.0 
            else:
                # Currently optimizing for win_rate, but could use cost_adjusted_performance
                score = metrics.win_rate

            if score > best_score:
                best_score = score
                best_model = model_name

        logger.info("model_exploitation", agent_role=agent_role, selected_model=best_model, score=best_score)
        return best_model

    def record_execution_result(self, agent_role: str, model_name: str, success: bool, cost_usd: float, latency_sec: float, brier_score: Optional[float] = None):
        """
        Record the results of an execution to update the A/B testing metrics.
        """
        if agent_role not in self._metrics_cache:
            return # Ignore untracked roles for now
            
        if model_name not in self._metrics_cache[agent_role]:
            self._metrics_cache[agent_role][model_name] = ModelPerformanceMetrics(model_name=model_name, agent_role=agent_role)
            
        metrics = self._metrics_cache[agent_role][model_name]
        
        metrics.total_executions += 1
        if success:
            metrics.successful_executions += 1
            
        metrics.total_cost_usd += cost_usd
        
        # Moving average latency
        n = metrics.total_executions
        metrics.average_latency_sec = ((metrics.average_latency_sec * (n - 1)) + latency_sec) / n
        
        metrics.win_rate = metrics.successful_executions / metrics.total_executions
        
        if brier_score is not None:
            metrics.cumulative_brier_score += brier_score

        logger.debug("model_metric_updated", agent_role=agent_role, model=model_name, win_rate=metrics.win_rate, executions=metrics.total_executions)

# Global orchestrator singleton
orchestrator = ModelOrchestrator()
