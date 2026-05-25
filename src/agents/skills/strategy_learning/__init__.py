"""
Strategy Learning Skills Package

Self-evolving parameter engine for all strategy agents.
Provides trade-level learning, parameter fitness evaluation,
regime detection, and an immutable evolution ledger.
"""

from agents.skills.strategy_learning.strategy_learning import (
    learn_from_trade,
    evaluate_parameter_fitness,
    propose_parameter_evolution,
    statistical_significance_test,
)
from agents.skills.strategy_learning.regime_detection import (
    detect_market_regime,
    get_regime_strategy_weights,
)
from agents.skills.strategy_learning.strategy_ledger import (
    strategy_ledger,
    record_evolution,
    get_evolution_summary,
)

__all__ = [
    "learn_from_trade",
    "evaluate_parameter_fitness",
    "propose_parameter_evolution",
    "statistical_significance_test",
    "detect_market_regime",
    "get_regime_strategy_weights",
    "strategy_ledger",
    "record_evolution",
    "get_evolution_summary",
]
