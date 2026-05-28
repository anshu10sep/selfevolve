# 07 — Market Regime Detection

## Why Regime Matters

A momentum strategy that works in a trending market will fail in a choppy market. The evolution system must:
1. **Detect** the current regime
2. **Condition** strategy selection on regime
3. **Score** agents relative to their expected performance in the current regime

## Current Implementation

**File**: `agents/skills/strategy_learning/regime_detection.py`

The system uses a basic regime classifier:
```python
def detect_market_regime(closes, highs, lows, volumes):
    # Computes trend direction, volatility, and volume profile
    # Returns: TRENDING_UP, TRENDING_DOWN, RANGE_BOUND, HIGH_VOLATILITY
```

This is used in `evolution_runner.py` to provide context to post-mortem analysis but is NOT used for:
- Strategy selection
- Trust weight conditioning
- Backtest filtering

## Regime Classification Methods

### 1. Moving Average Regime (Simple, Current)
```python
sma_20 = mean(closes[-20:])
sma_50 = mean(closes[-50:])
if sma_20 > sma_50 * 1.02:
    regime = "BULL"
elif sma_20 < sma_50 * 0.98:
    regime = "BEAR"
else:
    regime = "SIDEWAYS"
```

### 2. Volatility Regime (ATR-based)
```python
atr = average_true_range(highs, lows, closes, period=14)
atr_percentile = percentile_rank(atr, historical_atr_values)
if atr_percentile > 80:
    vol_regime = "HIGH_VOL"
elif atr_percentile < 20:
    vol_regime = "LOW_VOL"
else:
    vol_regime = "NORMAL_VOL"
```

### 3. Hidden Markov Model (Professional)
```python
from hmmlearn import hmm

# Train HMM on returns
model = hmm.GaussianHMM(n_components=3, covariance_type="full")
model.fit(returns.reshape(-1, 1))

# Predict current regime
current_state = model.predict(recent_returns.reshape(-1, 1))[-1]
# States map to: 0=Low-Vol, 1=Bull, 2=Crisis
```

### 4. Combined Regime (Recommended)

```python
@dataclass
class MarketRegime:
    trend: str           # BULL, BEAR, SIDEWAYS
    volatility: str      # HIGH, NORMAL, LOW
    momentum: str        # STRONG, WEAK, NEGATIVE
    volume_profile: str  # ACCUMULATION, DISTRIBUTION, NEUTRAL
    confidence: float    # 0.0 - 1.0

    @property
    def composite_label(self):
        return f"{self.trend}_{self.volatility}"
        # e.g., "BULL_LOW" = perfect for momentum
        #        "BEAR_HIGH" = perfect for mean reversion shorts
```

## Regime-Aware Evolution

### Strategy Selection
```python
REGIME_STRATEGY_MAP = {
    "BULL_LOW": ["momentum", "breakout", "overnight_hold"],
    "BULL_HIGH": ["momentum", "vwap"],
    "BEAR_LOW": ["mean_reversion", "pairs"],
    "BEAR_HIGH": ["mean_reversion", "crypto_scalper"],
    "SIDEWAYS_LOW": ["pairs", "mean_reversion"],
    "SIDEWAYS_HIGH": ["vwap", "gap_fill"],
}

def select_strategies(regime: MarketRegime):
    """Activate only strategies suited for current regime."""
    key = regime.composite_label
    active = REGIME_STRATEGY_MAP.get(key, list(ALL_STRATEGIES.keys()))
    return {name: strat for name, strat in ALL_STRATEGIES.items() if name in active}
```

### Regime-Conditioned Trust
```python
# Store separate trust weights per regime
# agent_scores table: add regime column
# e.g., FUNDAMENTAL_ANALYST has trust 0.85 in BULL but 0.45 in BEAR

def get_regime_trust(agent_role, current_regime):
    """Get trust weight specific to current regime."""
    regime_trust = get_agent_score(agent_role, regime=current_regime.trend)
    if regime_trust:
        return regime_trust
    # Fallback to regime-agnostic trust
    return get_agent_score(agent_role)
```

### Regime-Tagged Predictions
```python
# Add regime to prediction records
class PredictionRecord:
    ...
    market_regime = Column(String(20))  # NEW: regime at prediction time

# During Brier computation, filter by matching regime:
def get_regime_brier(agent_role, current_regime):
    preds = get_predictions(
        agent_role=agent_role,
        market_regime=current_regime,
        resolved_only=True,
    )
    return brier_score(preds)
```

## Regime Transition Detection

Alert when the market regime changes — this is when strategies are most likely to fail:

```python
class RegimeMonitor:
    def __init__(self):
        self.previous_regime = None
        self.regime_start = None

    async def check_transition(self):
        current = detect_current_regime()
        if current.trend != self.previous_regime:
            duration = now() - self.regime_start
            await send_alert(
                f"🔄 Regime Change Detected\n"
                f"From: {self.previous_regime}\n"
                f"To: {current.trend}\n"
                f"Duration of previous: {duration}\n"
                f"Action: Reviewing strategy weights..."
            )
            self.previous_regime = current.trend
            self.regime_start = now()

            # Trigger immediate trust rebalance
            await rebalance_strategy_weights(current)
```
