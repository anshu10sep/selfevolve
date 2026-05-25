"""
Agent Insight Models

Structured payloads for inter-agent intelligence sharing.
Agents publish AgentInsight objects to the AGENT_INSIGHTS event channel,
and other agents query them during their reasoning loop.

This is the typed contract between agents — it ensures that
a Macro Analyst's regime change insight is consumed correctly
by the Technical Analyst and the Judge.

Design: Pub/Sub via Event Bus (decoupled), with in-memory cache
for on-demand queries. No direct agent-to-agent coupling.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class InsightType(str, Enum):
    """Types of insights agents can share."""

    # Market & Analysis Insights
    REGIME_CHANGE = "REGIME_CHANGE"
    """Macro Analyst detected a market regime shift (e.g., BULL → BEAR)."""

    SENTIMENT_DIVERGENCE = "SENTIMENT_DIVERGENCE"
    """Sentiment Analyst detected price vs. sentiment mismatch."""

    TECHNICAL_SIGNAL = "TECHNICAL_SIGNAL"
    """Technical Analyst detected a pattern (breakout, golden cross, etc.)."""

    FUNDAMENTAL_FLAG = "FUNDAMENTAL_FLAG"
    """Fundamental Analyst flagged a valuation extreme or earnings surprise."""

    # Risk & Compliance Insights
    RISK_ALERT = "RISK_ALERT"
    """Judge/Auditor raised a risk concern (circuit breaker, GFV, drawdown)."""

    COMPLIANCE_ALERT = "COMPLIANCE_ALERT"
    """Auditor raised a compliance issue (settlement, position limits)."""

    # Strategy Insights
    STRATEGY_SIGNAL = "STRATEGY_SIGNAL"
    """Strategy agent detected a backtested edge or regime opportunity."""

    # System Insights
    HEALTH_ALERT = "HEALTH_ALERT"
    """CTO/CSO detected a system issue (latency, security, infra)."""

    EVOLUTION_UPDATE = "EVOLUTION_UPDATE"
    """MetaReview: agent prompt was evolved, promoted, or discarded."""

    # Portfolio Insights
    PORTFOLIO_UPDATE = "PORTFOLIO_UPDATE"
    """Portfolio Manager: position opened, closed, or rebalanced."""


class InsightUrgency(str, Enum):
    """How urgently other agents should react to this insight."""
    LOW = "LOW"          # Informational — no immediate action needed
    MEDIUM = "MEDIUM"    # Should be considered in current analysis cycle
    HIGH = "HIGH"        # Should influence current decision
    CRITICAL = "CRITICAL"  # Requires immediate attention / circuit breaker


# Default expiry durations per insight type
INSIGHT_EXPIRY_MINUTES = {
    InsightType.REGIME_CHANGE: 1440,          # 24 hours
    InsightType.SENTIMENT_DIVERGENCE: 60,     # 1 hour
    InsightType.TECHNICAL_SIGNAL: 60,         # 1 hour
    InsightType.FUNDAMENTAL_FLAG: 480,        # 8 hours
    InsightType.RISK_ALERT: 120,              # 2 hours
    InsightType.COMPLIANCE_ALERT: 480,        # 8 hours
    InsightType.STRATEGY_SIGNAL: 240,         # 4 hours
    InsightType.HEALTH_ALERT: 60,             # 1 hour
    InsightType.EVOLUTION_UPDATE: 1440,       # 24 hours
    InsightType.PORTFOLIO_UPDATE: 120,        # 2 hours
}


class AgentInsight(BaseModel):
    """
    Structured insight shared between agents via the Event Bus.

    This is the fundamental unit of inter-agent communication.
    Each insight has a type, source, confidence, urgency, and
    optional ticker scope.

    Examples:
        # Macro Analyst publishes regime change
        AgentInsight(
            source_agent="MACRO_ANALYST",
            insight_type=InsightType.REGIME_CHANGE,
            title="Regime Change: BULL → BEAR",
            description="VIX crossed 25, yield curve inverted...",
            confidence=0.85,
            urgency=InsightUrgency.HIGH,
            data={"old_regime": "BULL", "new_regime": "BEAR", "vix": 27.5},
        )

        # Technical Analyst publishes breakout signal
        AgentInsight(
            source_agent="TECHNICAL_ANALYST",
            insight_type=InsightType.TECHNICAL_SIGNAL,
            ticker="AAPL",
            title="Bullish Breakout: AAPL",
            description="Price broke above 200-day MA with 2x avg volume",
            confidence=0.72,
            data={"pattern": "breakout", "ma_200": 178.50, "volume_mult": 2.1},
        )
    """
    insight_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique insight identifier",
    )
    source_agent: str = Field(
        ..., description="Role of the publishing agent (e.g., 'MACRO_ANALYST')",
    )
    insight_type: InsightType = Field(
        ..., description="Category of insight",
    )
    ticker: Optional[str] = Field(
        default=None,
        description="Ticker scope (None = system-wide insight)",
    )
    title: str = Field(
        ..., max_length=200,
        description="Short human-readable headline",
    )
    description: str = Field(
        ..., max_length=1000,
        description="Detailed explanation of the insight",
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Confidence in this insight (0 = uncertain, 1 = certain)",
    )
    urgency: InsightUrgency = Field(
        default=InsightUrgency.MEDIUM,
        description="How urgently other agents should react",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured supporting data (varies by insight type)",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="When this insight becomes stale (auto-set if not provided)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this insight was generated",
    )

    @field_validator("ticker", mode="before")
    @classmethod
    def uppercase_ticker(cls, v):
        if v is not None:
            return v.upper().strip()
        return v

    def model_post_init(self, __context: Any) -> None:
        """Auto-set expiry based on insight type if not provided."""
        if self.expires_at is None:
            expiry_minutes = INSIGHT_EXPIRY_MINUTES.get(
                self.insight_type, 60
            )
            self.expires_at = self.timestamp + timedelta(minutes=expiry_minutes)

    @property
    def is_expired(self) -> bool:
        """Check if this insight has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def age_minutes(self) -> float:
        """How many minutes old this insight is."""
        delta = datetime.now(timezone.utc) - self.timestamp
        return delta.total_seconds() / 60.0

    def to_context_string(self) -> str:
        """Format this insight as a string for LLM context injection."""
        ticker_str = f" [{self.ticker}]" if self.ticker else ""
        return (
            f"[{self.insight_type.value}]{ticker_str} "
            f"({self.source_agent}, {self.urgency.value}, "
            f"confidence={self.confidence:.0%}, "
            f"{self.age_minutes:.0f}m ago): "
            f"{self.title} — {self.description[:200]}"
        )

    def to_event_dict(self) -> dict[str, Any]:
        """Serialize for Event Bus transmission."""
        return {
            "insight_id": self.insight_id,
            "source_agent": self.source_agent,
            "insight_type": self.insight_type.value,
            "ticker": self.ticker,
            "title": self.title,
            "description": self.description[:500],
            "confidence": self.confidence,
            "urgency": self.urgency.value,
            "data": self.data,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_event_dict(cls, d: dict[str, Any]) -> "AgentInsight":
        """Deserialize from Event Bus transmission."""
        return cls(
            insight_id=d.get("insight_id", str(uuid.uuid4())),
            source_agent=d["source_agent"],
            insight_type=InsightType(d["insight_type"]),
            ticker=d.get("ticker"),
            title=d["title"],
            description=d["description"],
            confidence=d.get("confidence", 0.5),
            urgency=InsightUrgency(d.get("urgency", "MEDIUM")),
            data=d.get("data", {}),
            expires_at=(
                datetime.fromisoformat(d["expires_at"])
                if d.get("expires_at") else None
            ),
            timestamp=(
                datetime.fromisoformat(d["timestamp"])
                if d.get("timestamp")
                else datetime.now(timezone.utc)
            ),
        )
