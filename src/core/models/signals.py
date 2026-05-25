"""
Trading Signal Models

Pydantic models for conviction scores, debate state, execution orders,
market regimes, and aggregated research. These are the structured payloads
flowing through the LangGraph DAG between agent nodes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, computed_field


class RegimeType(str, Enum):
    """Market regime classification."""
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOL = "HIGH_VOL"
    PANIC = "PANIC"


class ExecutionAction(str, Enum):
    """Possible trade actions from the Judge Agent."""
    BUY = "BUY"
    HOLD = "HOLD"
    PASS = "PASS"
    SELL = "SELL"


class ConvictionScore(BaseModel):
    """
    Dual-channel output from a research sub-agent.
    
    Quantitative payload (score) is used for deterministic ensemble weighting.
    Qualitative payload (rationale) is passed to the Judge for nuance evaluation.
    """
    agent_id: str = Field(..., description="Source agent identifier")
    ticker: str = Field(..., description="Asset symbol")
    score: float = Field(
        ..., ge=-1.0, le=1.0,
        description="Conviction score: -1.0 (strong bear) to 1.0 (strong bull)",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence in the score (0 = uncertain, 1 = certain)",
    )
    rationale: str = Field(
        ..., max_length=500,
        description="Qualitative rationale (max 100 words)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        return v.upper().strip()


class DebateArgument(BaseModel):
    """
    Structured output from Bull/Bear debate agents.

    Enforces argument length limits and provides a trackable conviction
    score that feeds into the prediction tracking system.
    """
    agent_id: str = Field(..., description="Source agent identifier")
    ticker: str = Field(..., description="Asset under debate")
    argument: str = Field(
        ..., max_length=600,
        description="The agent's bull/bear thesis (max 150 words)",
    )
    conviction_score: float = Field(
        ..., ge=0.0, le=10.0,
        description="Conviction in this thesis (0 = no conviction, 10 = maximum)",
    )
    key_data_points: list[str] = Field(
        default_factory=list,
        description="Top 3 data points supporting the argument",
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Confidence in prediction accuracy (0 = uncertain, 1 = certain)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        return v.upper().strip()


class DebateState(BaseModel):
    """
    State flowing through the Bull/Bear debate workflow.
    
    Both agents receive identical aggregated data and argue opposing
    viewpoints in a single-turn debate (no back-and-forth to save tokens).
    """
    ticker: str = Field(..., description="Asset under debate")
    aggregated_data: dict = Field(
        default_factory=dict,
        description="Combined research from all sub-agents",
    )
    bull_argument: str = Field(
        default="", description="Bull persona's thesis (max 150 words)"
    )
    bull_score: float = Field(
        default=0.0, ge=0.0, le=10.0,
        description="Bull conviction (0-10)",
    )
    bear_argument: str = Field(
        default="", description="Bear persona's thesis (max 150 words)"
    )
    bear_score: float = Field(
        default=0.0, ge=0.0, le=10.0,
        description="Bear conviction (0-10)",
    )
    debate_complete: bool = Field(
        default=False, description="Whether both sides have argued"
    )

    @computed_field
    @property
    def net_conviction(self) -> float:
        """Net conviction = bull - bear. Positive = bullish."""
        return self.bull_score - self.bear_score

    @computed_field
    @property
    def conviction_divergence(self) -> float:
        """Absolute divergence between bull and bear scores."""
        return abs(self.bull_score - self.bear_score)


class ExecutionOrder(BaseModel):
    """
    Strict Pydantic output from the Judge Agent.
    
    This is the ONLY schema that can reach the Alpaca execution layer.
    If the LLM fails to produce a valid instance, the system defaults to PASS.
    """
    ticker: str = Field(..., description="Asset symbol")
    action: ExecutionAction = Field(..., description="Execution decision")
    confidence_score: float = Field(
        ..., ge=0.0, le=10.0, description="Overall conviction"
    )
    fractional_quantity: float = Field(
        default=0.0, ge=0.0, description="Exact fractional shares to buy/sell"
    )
    allocated_capital: float = Field(
        default=0.0, ge=0.0, description="Total dollar amount allocated"
    )
    stop_loss_price: Optional[float] = Field(
        default=None, description="Hard stop loss price"
    )
    take_profit_price: Optional[float] = Field(
        default=None, description="Take profit target"
    )
    reasoning: str = Field(
        ..., max_length=200, description="Brief one-sentence justification"
    )
    client_order_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Idempotent order ID",
    )

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v: str) -> str:
        return v.upper().strip()


class MarketRegime(BaseModel):
    """
    Current market regime classification.
    
    Determined by deterministic Python (VIX, macro data),
    NOT by the LLM.
    """
    regime: RegimeType = Field(..., description="Current market regime")
    vix_level: float = Field(default=0.0, ge=0, description="Current VIX level")
    fed_funds_rate: float = Field(default=0.0, description="Current Fed funds rate")
    sp500_trend: str = Field(default="neutral", description="S&P 500 trend direction")
    description: str = Field(default="", description="Human-readable regime summary")
    position_size_modifier: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Position sizing multiplier (0 = no trades, 1 = full size)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class AggregatedResearch(BaseModel):
    """
    Combined research output from all parallel sub-agents.
    
    The Python aggregator calculates the weighted conviction score
    using transparent trust weights from the database.
    """
    ticker: str = Field(..., description="Asset analyzed")
    fundamental_score: Optional[ConvictionScore] = Field(
        default=None, description="Fundamental analyst output"
    )
    technical_score: Optional[ConvictionScore] = Field(
        default=None, description="Technical analyst output"
    )
    sentiment_score: Optional[ConvictionScore] = Field(
        default=None, description="Sentiment analyst output"
    )
    macro_score: Optional[ConvictionScore] = Field(
        default=None, description="Macro analyst output"
    )
    agent_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Trust-weighted ensemble weights per agent",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @computed_field
    @property
    def weighted_conviction(self) -> float:
        """
        Trust-weighted average conviction score.
        
        Calculated deterministically by the Python aggregator,
        NOT by any LLM.
        """
        scores = []
        weights = []

        for score_field, agent_key in [
            (self.fundamental_score, "fundamental"),
            (self.technical_score, "technical"),
            (self.sentiment_score, "sentiment"),
            (self.macro_score, "macro"),
        ]:
            if score_field is not None:
                w = self.agent_weights.get(agent_key, 1.0)
                scores.append(score_field.score * w)
                weights.append(w)

        if not weights:
            return 0.0
        return sum(scores) / sum(weights)
