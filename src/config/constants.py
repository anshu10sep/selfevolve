"""
SelfEvolve System Constants

Immutable operational parameters that define the system's behavioral boundaries.
These values are NOT configurable at runtime — they represent hard safety limits
and architectural decisions.
"""

from __future__ import annotations

# ════════════════════════════════════════════════════════════════════
# MARKET HOURS (Eastern Time)
# ════════════════════════════════════════════════════════════════════
MARKET_OPEN_ET = "09:30"
MARKET_CLOSE_ET = "16:00"
PRE_MARKET_WARMUP_ET = "08:00"
POST_MARKET_EVOLUTION_ET = "16:30"

# ════════════════════════════════════════════════════════════════════
# SETTLEMENT & REGULATORY
# ════════════════════════════════════════════════════════════════════
T1_SETTLEMENT_DAYS = 1  # T+1 settlement for US equities
MAX_GFV_STRIKES = 2  # Maximum intentional Good Faith Violations per rolling period
GFV_ROLLING_MONTHS = 12  # Rolling window for GFV tracking
GFV_CATASTROPHIC_LOSS_THRESHOLD_PCT = 10.0  # Loss threshold to allow intentional GFV

# ════════════════════════════════════════════════════════════════════
# CAPITAL TRANCHING
# ════════════════════════════════════════════════════════════════════
DEFAULT_TRANCHE_COUNT = 10
DEFAULT_TRANCHE_SIZES = [10.0] * DEFAULT_TRANCHE_COUNT  # 10 x $10 = $100
MIN_TRANCHE_SIZE_USD = 1.00  # Alpaca minimum notional order
MAX_POSITION_PCT = 20.0  # Maximum single position as % of portfolio
TRANCHE_SCALE_THRESHOLDS = {
    200: 0.08,   # Above $200: 8% per tranche
    500: 0.05,   # Above $500: 5% per tranche
}

# ════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER & HEALTH
# ════════════════════════════════════════════════════════════════════
HEARTBEAT_INTERVAL_SEC = 1
HEARTBEAT_STALE_THRESHOLD_SEC = 3.0
CIRCUIT_BREAKER_MAX_EXCEPTIONS = 3
CIRCUIT_BREAKER_WINDOW_SEC = 60
MAX_RESTART_RETRIES = 3  # Supervisord restart limit

# ════════════════════════════════════════════════════════════════════
# EVOLUTION & REFLEXION
# ════════════════════════════════════════════════════════════════════
MAX_RULES_PER_AGENT = 3  # Maximum linguistic lessons retrieved per agent
BRIER_WINDOW_SIZE = 30  # Rolling trade window for Brier score calculation
SHADOW_MIN_TRADES = 20  # Minimum trades before A/B test evaluation
EVOLUTION_P_VALUE_THRESHOLD = 0.05  # Statistical significance for prompt promotion
SHARPE_DELTA_THRESHOLD = 0.25  # Minimum Sharpe improvement for strategy promotion
TRUST_DECAY_RATE = 0.95  # Trust weight decay per consecutive failure
MIN_TRUST_WEIGHT = 0.1  # Minimum agent trust weight before retirement

# ════════════════════════════════════════════════════════════════════
# MODEL TIERING (Gemini-first, Phase 1)
# ════════════════════════════════════════════════════════════════════
EFFICIENT_TIER_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash-lite"]
PREMIUM_TIER_MODELS = ["gemini-2.5-pro", "gemini-2.5-flash"]
CONFIDENCE_ESCALATION_THRESHOLD = 0.85  # Below this, escalate to premium model
VIX_BUDGET_DOUBLE_THRESHOLD = 25.0  # VIX level that doubles API budget

# ════════════════════════════════════════════════════════════════════
# DEBATE WORKFLOW
# ════════════════════════════════════════════════════════════════════
DEBATE_MAX_ARGUMENT_WORDS = 150
DEBATE_SCORE_RANGE = (0.0, 10.0)
JUDGE_MIN_CONFIDENCE_FOR_EXECUTION = 6.0  # Below this → PASS
HITL_CONFIDENCE_DIVERGENCE_THRESHOLD = 0.60  # Below this → human approval needed

# ════════════════════════════════════════════════════════════════════
# POSITION SIZING
# ════════════════════════════════════════════════════════════════════
ATR_PERIOD = 14  # 14-day Average True Range
TARGET_RISK_PCT_PER_ATR = 1.0  # 1% portfolio risk per 1-ATR move
SLIPPAGE_PENALTY_LOW_VOLUME = 0.02  # 2% slippage for low-volume assets
LOW_VOLUME_THRESHOLD = 5_000_000  # Daily dollar volume below this = low liquidity

# ════════════════════════════════════════════════════════════════════
# HITL SETTINGS
# ════════════════════════════════════════════════════════════════════
HITL_TIMEOUT_SECONDS = 60  # Max wait for human approval
HITL_PRICE_DRIFT_TOLERANCE_PCT = 0.1  # Max price drift for re-hydration approval
HITL_REJECTION_REASONS = [
    "Macro Risk",
    "Technical Disagreement",
    "News Event",
    "Insufficient Confidence",
    "Other",
]

# ════════════════════════════════════════════════════════════════════
# OBSERVABILITY
# ════════════════════════════════════════════════════════════════════
SEMANTIC_AUDIT_SAMPLE_RATE = 0.05  # 5% random sampling of Judge outputs
LEDGER_DRIFT_HALT_THRESHOLD_PCT = 1.0  # Halt if ledger drifts > 1% of equity
COST_TRACKING_MODELS = {
    # Gemini models (primary)
    "gemini-2.0-flash": {"prompt": 0.00010, "completion": 0.00040},       # per 1K tokens
    "gemini-2.0-flash-lite": {"prompt": 0.00005, "completion": 0.00020},
    "gemini-2.5-pro": {"prompt": 0.00125, "completion": 0.01000},
    "gemini-2.5-flash": {"prompt": 0.00015, "completion": 0.00060},
    # OpenAI models (Phase 2+)
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    # Anthropic models (Phase 2+)
    "claude-3-5-haiku-latest": {"prompt": 0.00025, "completion": 0.00125},
    "claude-sonnet-4-20250514": {"prompt": 0.003, "completion": 0.015},
}

# ════════════════════════════════════════════════════════════════════
# DEFAULT WATCHLIST (Curated for $100 micro-capital)
# High-liquidity, fractional-friendly tickers with strong volume
# ════════════════════════════════════════════════════════════════════
DEFAULT_WATCHLIST = [
    # Mega-cap tech (liquid, well-analyzed, tight spreads)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META",
    # Broad market ETFs (regime tracking)
    "SPY", "QQQ", "IWM",
    # Sector ETFs (rotation plays)
    "XLF", "XLE", "XLK", "XLV",
    # Volatility ETFs (hedge instruments)
    "UVXY",
    # High-volume mid-caps (momentum candidates)
    "AMD", "TSLA", "PLTR", "SOFI", "COIN",
]

# ════════════════════════════════════════════════════════════════════
# PAPER → PRODUCTION READINESS
# ════════════════════════════════════════════════════════════════════
PAPER_TRADE_TARGET_DAYS = 14  # Target: 2 weeks paper before prod
PROD_READINESS_MIN_TRADES = 30  # Minimum trades before prod eligible
PROD_READINESS_MIN_WIN_RATE = 0.50  # ≥50% win rate required
PROD_READINESS_MAX_DRAWDOWN = 0.10  # <10% max drawdown required
PROD_READINESS_MIN_SHARPE = 0.5  # Sharpe ≥ 0.5 required

# ════════════════════════════════════════════════════════════════════
# DATA INGESTION
# ════════════════════════════════════════════════════════════════════
VOLUME_SPIKE_MULTIPLIER = 5.0  # Trigger analysis when volume > 5x avg
REDIS_HOT_STATE_TTL_SEC = 86400  # 24 hours
END_OF_DAY_FLUSH_ET = "16:15"  # Flush Redis → Postgres
