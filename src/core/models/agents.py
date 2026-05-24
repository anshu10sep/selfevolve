"""
Agent Identity and Trust Models

Defines the agent hierarchy, identity separation (immutable core vs mutable strategy),
trust weights based on Brier scores, and domain isolation validators.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, computed_field


class AgentRole(str, Enum):
    """All possible agent roles in the hierarchy."""
    # Executive Layer
    MASTER = "MASTER"
    CEO = "CEO"
    CTO = "CTO"
    CSO = "CSO"

    # Management Layer
    QA = "QA"
    PRODUCT = "PRODUCT"

    # Specialist Layer - Research
    FUNDAMENTAL_ANALYST = "FUNDAMENTAL_ANALYST"
    TECHNICAL_ANALYST = "TECHNICAL_ANALYST"
    SENTIMENT_ANALYST = "SENTIMENT_ANALYST"
    MACRO_ANALYST = "MACRO_ANALYST"

    # Specialist Layer - Debate
    BULL = "BULL"
    BEAR = "BEAR"

    # Specialist Layer - Decision
    JUDGE = "JUDGE"

    # Specialist Layer - Evolution
    META_REVIEW = "META_REVIEW"

    # Specialist Layer - Support
    DEVELOPER = "DEVELOPER"
    JOURNALING = "JOURNALING"
    AUDITOR = "AUDITOR"


class AgentType(str, Enum):
    """Agent hierarchy level."""
    EXECUTIVE = "EXECUTIVE"
    MANAGER = "MANAGER"
    ANALYST = "ANALYST"
    SPECIALIST = "SPECIALIST"


class AgentStatus(str, Enum):
    """Agent lifecycle state."""
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    EVOLVING = "EVOLVING"
    RETIRED = "RETIRED"
    ERROR = "ERROR"


# Domain isolation: Technical analysts cannot use fundamental terms
DOMAIN_FORBIDDEN_WORDS = {
    AgentRole.TECHNICAL_ANALYST: [
        "earnings", "revenue", "CEO", "CPI", "Fed", "GDP",
        "balance sheet", "cash flow", "dividend", "PE ratio",
    ],
    AgentRole.FUNDAMENTAL_ANALYST: [
        "RSI", "MACD", "moving average", "bollinger",
        "candlestick", "fibonacci", "support line", "resistance line",
    ],
    AgentRole.SENTIMENT_ANALYST: [
        "DCF", "intrinsic value", "book value", "XBRL",
    ],
}


class AgentIdentity(BaseModel):
    """
    Full agent identity with immutable core and mutable strategy.
    
    Identity_Core: Read-only backstory and domain expertise.
    Strategic_Nuance: Read-write operational adjustments updated by evolution.
    """
    agent_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique agent identifier",
    )
    agent_name: str = Field(..., description="Human-readable agent name")
    agent_role: AgentRole = Field(..., description="Role in the hierarchy")
    agent_type: AgentType = Field(..., description="Hierarchy level")
    identity_core: str = Field(
        ...,
        description="IMMUTABLE identity, backstory, and domain expertise",
    )
    strategic_nuance: str = Field(
        default="",
        description="MUTABLE operational strategy (updated by evolution)",
    )
    status: AgentStatus = Field(
        default=AgentStatus.ACTIVE,
        description="Current lifecycle state",
    )
    parent_agent_id: Optional[str] = Field(
        default=None,
        description="Parent agent in the hierarchy",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    version: int = Field(default=1, description="Prompt version number")
    llm_model: Optional[str] = Field(
        default=None, 
        description="The LLM model assigned to this agent by the Model Orchestrator"
    )

    @computed_field
    @property
    def full_prompt(self) -> str:
        """Assembled system prompt from core identity + strategic nuance."""
        parts = [self.identity_core]
        if self.strategic_nuance:
            parts.append(f"\n\nCurrent Strategic Directives:\n{self.strategic_nuance}")
        return "\n".join(parts)


class AgentUpdate(BaseModel):
    """
    Proposed update to an agent's mutable strategy.
    
    Domain isolation is enforced via validators — a Technical Analyst
    cannot incorporate fundamental analysis terms into its strategy.
    """
    agent_name: str = Field(..., description="Target agent name")
    agent_role: AgentRole = Field(..., description="Agent role for validation")
    strategic_nuance: str = Field(
        ..., description="Updated strategic directives"
    )
    version_number: int = Field(..., gt=0, description="New version number")
    change_description: str = Field(
        ..., description="What changed and why"
    )

    @field_validator("strategic_nuance")
    @classmethod
    def enforce_domain_isolation(cls, v: str, info) -> str:
        """
        Prevent agents from incorporating out-of-domain terms.
        
        This prevents 'identity drift' where a Technical Analyst
        starts hallucinating fundamental data.
        """
        role = info.data.get("agent_role")
        if role and role in DOMAIN_FORBIDDEN_WORDS:
            forbidden = DOMAIN_FORBIDDEN_WORDS[role]
            violations = [
                word for word in forbidden
                if word.lower() in v.lower()
            ]
            if violations:
                raise ValueError(
                    f"{role.value} cannot incorporate terms: {violations}. "
                    f"This violates domain isolation."
                )
        return v


class TrustWeight(BaseModel):
    """
    Agent trust and performance metrics.
    
    Trust weights are calculated deterministically from Brier scores
    and stored in PostgreSQL — they are never hidden in an LLM's
    context window.
    """
    agent_id: str = Field(..., description="Agent identifier")
    current_weight: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Current trust weight for ensemble voting",
    )
    historical_brier_score: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Rolling 30-trade Brier score (lower = better)",
    )
    consecutive_failures: int = Field(
        default=0, ge=0,
        description="Number of consecutive prediction failures",
    )
    total_predictions: int = Field(
        default=0, ge=0,
        description="Total predictions made",
    )
    correct_predictions: int = Field(
        default=0, ge=0,
        description="Number of correct predictions",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @computed_field
    @property
    def win_rate(self) -> float:
        """Historical win rate."""
        if self.total_predictions == 0:
            return 0.0
        return self.correct_predictions / self.total_predictions

    @computed_field
    @property
    def should_retire(self) -> bool:
        """Whether the agent should be retired due to poor performance."""
        from config.constants import MIN_TRUST_WEIGHT
        return self.current_weight < MIN_TRUST_WEIGHT


class AgentHealthReport(BaseModel):
    """Comprehensive health report for a single agent."""
    agent_id: str
    agent_name: str
    agent_role: AgentRole
    status: AgentStatus
    last_activity: Optional[datetime] = None
    brier_score: float = 0.5
    trust_weight: float = 1.0
    win_rate: float = 0.0
    active_tasks: int = 0
    token_cost_today: float = 0.0
    version: int = 1
    uptime_hours: float = 0.0
    llm_model: Optional[str] = None
