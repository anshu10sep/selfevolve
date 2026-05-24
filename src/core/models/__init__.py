"""
Core domain models for the SelfEvolve trading system.

All models use Pydantic v2 for strict validation, serialization,
and type safety throughout the multi-agent pipeline.
"""

from core.models.portfolio import (
    PortfolioState,
    Position,
    TrancheState,
    TrancheStatus,
    TradeIntent,
    TradeSide,
    SettlementRecord,
)
from core.models.signals import (
    ConvictionScore,
    DebateState,
    ExecutionOrder,
    ExecutionAction,
    MarketRegime,
    RegimeType,
    AggregatedResearch,
)
from core.models.agents import (
    AgentIdentity,
    AgentRole,
    AgentType,
    AgentStatus,
    AgentUpdate,
    TrustWeight,
    AgentHealthReport,
)
from core.models.audit import (
    AuditEvent,
    AuditEventType,
    BugReport,
    BugSeverity,
    BugStatus,
    EvolutionRecord,
    SystemHealthEvent,
    HealthEventType,
    CostRecord,
)

__all__ = [
    # Portfolio
    "PortfolioState", "Position", "TrancheState", "TrancheStatus",
    "TradeIntent", "TradeSide", "SettlementRecord",
    # Signals
    "ConvictionScore", "DebateState", "ExecutionOrder", "ExecutionAction",
    "MarketRegime", "RegimeType", "AggregatedResearch",
    # Agents
    "AgentIdentity", "AgentRole", "AgentType", "AgentStatus",
    "AgentUpdate", "TrustWeight", "AgentHealthReport",
    # Audit
    "AuditEvent", "AuditEventType", "BugReport", "BugSeverity", "BugStatus",
    "EvolutionRecord", "SystemHealthEvent", "HealthEventType", "CostRecord",
]
