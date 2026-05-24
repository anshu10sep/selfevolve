"""
SelfEvolve System Settings

Centralized configuration loaded from environment variables via Pydantic Settings.
All API keys, infrastructure URLs, and risk parameters are managed here.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment."""
    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class AccountType(str, Enum):
    """Brokerage account type."""
    CASH = "CASH"
    MARGIN = "MARGIN"


class Settings(BaseSettings):
    """
    Global application settings loaded from environment variables.
    
    All sensitive values (API keys) are loaded from .env file.
    Risk parameters have safe defaults that can be overridden.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Alpaca Broker ──────────────────────────────────────────────
    alpaca_api_key: str = Field(default="", description="Alpaca API key")
    alpaca_secret_key: str = Field(default="", description="Alpaca secret key")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca API base URL (paper or live)",
    )
    alpaca_data_url: str = Field(
        default="https://data.alpaca.markets",
        description="Alpaca market data URL",
    )

    # ── LLM Providers ─────────────────────────────────────────────
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    # Future: add when ready for multi-model optimization
    openai_api_key: str = Field(default="", description="OpenAI API key (Phase 2+)")
    anthropic_api_key: str = Field(default="", description="Anthropic API key (Phase 2+)")

    # ── Efficient Tier Model ──────────────────────────────────────
    efficient_model: str = Field(
        default="gemini-2.5-flash",
        description="Cost-efficient model for triage/parsing tasks",
    )
    # ── Premium Tier Model ────────────────────────────────────────
    premium_model: str = Field(
        default="gemini-2.5-pro",
        description="Premium model for debate/judge/evolution tasks",
    )

    # ── Communication ─────────────────────────────────────────────
    telegram_bot_token: str = Field(default="", description="Telegram bot token for HITL")
    telegram_chat_id: str = Field(default="", description="Telegram chat ID for alerts")

    # ── Infrastructure ────────────────────────────────────────────
    postgres_url: str = Field(
        default="postgresql+asyncpg://selfevolve:selfevolve@postgres:5432/selfevolve",
        description="Async PostgreSQL connection URL",
    )
    postgres_sync_url: str = Field(
        default="postgresql://selfevolve:selfevolve@postgres:5432/selfevolve",
        description="Sync PostgreSQL connection URL (for migrations)",
    )
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL",
    )
    qdrant_url: str = Field(
        default="http://qdrant:6333",
        description="Qdrant vector database URL",
    )

    # ── Risk Management ───────────────────────────────────────────
    max_daily_api_budget: float = Field(
        default=1.00,
        description="Maximum daily LLM API spend in USD",
    )
    max_risk_per_trade_pct: float = Field(
        default=2.0,
        description="Maximum risk per trade as percentage of portfolio",
    )
    max_daily_drawdown_pct: float = Field(
        default=5.0,
        description="Maximum daily drawdown percentage before HCF",
    )
    initial_capital: float = Field(
        default=100.00,
        description="Starting capital in USD",
    )
    account_type: AccountType = Field(
        default=AccountType.CASH,
        description="Brokerage account type (CASH only for Phase 1-2)",
    )

    # ── System ────────────────────────────────────────────────────
    environment: Environment = Field(
        default=Environment.PAPER,
        description="Deployment environment",
    )
    log_level: str = Field(default="INFO", description="Logging level")
    dashboard_port: int = Field(default=8000, description="Dashboard API port")
    webhook_port: int = Field(default=8001, description="Webhook listener port")

    # ── Validators ────────────────────────────────────────────────
    @field_validator("account_type")
    @classmethod
    def enforce_cash_account(cls, v: AccountType) -> AccountType:
        """Phase 1-2: Only CASH accounts are permitted."""
        if v == AccountType.MARGIN:
            raise ValueError(
                "MARGIN accounts are disabled in Phase 1-2. "
                "Use CASH account to avoid PDT rules."
            )
        return v

    @field_validator("max_risk_per_trade_pct")
    @classmethod
    def validate_risk_pct(cls, v: float) -> float:
        """Risk per trade must be between 0.5% and 5%."""
        if not 0.5 <= v <= 5.0:
            raise ValueError(f"Risk per trade must be 0.5-5.0%, got {v}%")
        return v

    @field_validator("max_daily_drawdown_pct")
    @classmethod
    def validate_drawdown_pct(cls, v: float) -> float:
        """Daily drawdown limit must be between 2% and 15%."""
        if not 2.0 <= v <= 15.0:
            raise ValueError(f"Daily drawdown must be 2-15%, got {v}%")
        return v

    # ── Computed Properties ───────────────────────────────────────
    @computed_field
    @property
    def max_risk_per_trade_usd(self) -> float:
        """Maximum dollar risk per trade."""
        return self.initial_capital * (self.max_risk_per_trade_pct / 100.0)

    @computed_field
    @property
    def max_daily_drawdown_usd(self) -> float:
        """Maximum daily drawdown in USD."""
        return self.initial_capital * (self.max_daily_drawdown_pct / 100.0)

    @computed_field
    @property
    def is_paper(self) -> bool:
        """Whether we're in paper trading mode."""
        return self.environment == Environment.PAPER

    @computed_field
    @property
    def is_live(self) -> bool:
        """Whether we're in live trading mode."""
        return self.environment == Environment.LIVE


# Singleton settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
