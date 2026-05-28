# 09 — Position Sizing with Kelly Criterion

## The Connection: Brier → Kelly → Position Size

The Brier score system produces calibrated probabilities. The Kelly criterion uses those probabilities to compute optimal position sizes. This creates a direct feedback loop:

```
Better Calibration → Better Position Sizing → Better Returns → Higher Trust
```

## Kelly Criterion Formula

```
f* = (b × p - q) / b
```

Where:
- `f*` = fraction of capital to risk
- `p` = probability of winning (from calibrated agent)
- `q` = probability of losing (1 - p)
- `b` = net odds (reward/risk ratio, e.g., take_profit / stop_loss)

## Why Calibration Matters Enormously

| Predicted P | Actual P | Full Kelly | Outcome |
|-------------|----------|------------|---------|
| 0.70 | 0.70 | 26.7% | ✅ Optimal |
| 0.70 | 0.55 | 26.7% but edge is only 7.5% | ❌ Over-leveraged |
| 0.70 | 0.45 | 26.7% but NO edge | 💀 Guaranteed ruin |

An overconfident agent (Brier > 0.25) will cause the Kelly formula to suggest dangerously large positions.

## Current System

The system uses ATR-based position sizing (constants.py):
```python
ATR_PERIOD = 14
TARGET_RISK_PCT_PER_ATR = 1.0  # 1% risk per 1-ATR move
MAX_POSITION_PCT = 20.0        # Cap at 20% of portfolio
```

This is regime-aware (volatility adjusts ATR) but **ignores agent calibration**. It's the same position size whether the system is 55% confident or 95% confident.

## Proposed: Brier-Calibrated Kelly Sizing

### Step 1: Get Calibrated Probability

```python
def get_calibrated_probability(raw_probability, agent_brier):
    """Shrink raw probability toward 0.5 based on agent's calibration."""
    if agent_brier >= 0.25:
        # Agent is no better than random — don't trust the probability
        return 0.5

    # Shrinkage factor: how much to trust the agent's probability
    # Perfect agent (brier=0): full trust
    # Random agent (brier=0.25): zero trust
    trust = max(0, 1 - agent_brier / 0.25)

    # Shrink toward 50%
    calibrated = 0.5 + trust * (raw_probability - 0.5)
    return calibrated
```

### Step 2: Compute Kelly Fraction

```python
def kelly_fraction(calibrated_prob, reward_risk_ratio):
    """Compute Kelly fraction from calibrated probability and R:R."""
    p = calibrated_prob
    q = 1 - p
    b = reward_risk_ratio

    kelly = (b * p - q) / b
    return max(0, kelly)  # Never go negative (= no trade)
```

### Step 3: Apply Fractional Kelly

```python
def compute_position_size(
    portfolio_value: float,
    calibrated_prob: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    kelly_fraction_mult: float = 0.25,  # Quarter Kelly
    max_position_pct: float = 0.20,
) -> float:
    """Compute position size using fractional Kelly with calibration."""

    reward_risk = take_profit_pct / stop_loss_pct if stop_loss_pct > 0 else 2.0
    f_star = kelly_fraction(calibrated_prob, reward_risk)

    # Apply fractional Kelly (25% of full Kelly)
    f_adjusted = f_star * kelly_fraction_mult

    # Cap at max position size
    f_capped = min(f_adjusted, max_position_pct)

    position_value = portfolio_value * f_capped
    return round(position_value, 2)
```

### Example Scenarios

| Scenario | Calibrated P | R:R | Full Kelly | Quarter Kelly | Position ($100 portfolio) |
|----------|-------------|-----|------------|---------------|--------------------------|
| High confidence, good R:R | 0.75 | 2:1 | 37.5% | 9.4% | $9.40 |
| Medium confidence, good R:R | 0.60 | 2:1 | 20.0% | 5.0% | $5.00 |
| Low confidence, poor R:R | 0.52 | 1.5:1 | 1.3% | 0.3% | $0.33 |
| No edge (uncalibrated agent) | 0.50 | 2:1 | 0% | 0% | $0.00 (no trade) |
| Negative edge | 0.45 | 1:1 | -10% | 0% | $0.00 (no trade) |

## Integration with Current System

### Replace Fixed Tranche Sizing

Current (constants.py):
```python
DEFAULT_TRANCHE_COUNT = 10
DEFAULT_TRANCHE_SIZES = [10.0] * 10  # Fixed $10 per tranche
```

Proposed:
```python
def compute_tranche_size(
    portfolio_value: float,
    consensus_probability: float,
    consensus_brier: float,
    stop_loss_pct: float,
    take_profit_pct: float,
):
    """Dynamic tranche sizing based on calibration quality."""

    # Calibrate the probability using the ensemble's Brier score
    calibrated_p = get_calibrated_probability(consensus_probability, consensus_brier)

    # Compute Kelly-optimal size
    kelly_size = compute_position_size(
        portfolio_value=portfolio_value,
        calibrated_prob=calibrated_p,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        kelly_fraction_mult=0.25,  # Conservative
    )

    # Floor at minimum tradeable amount
    return max(MIN_TRANCHE_SIZE_USD, kelly_size)
```

### Ensemble Brier for Consensus

When multiple agents contribute to a trade, use the weighted Brier:

```python
def ensemble_brier(agent_briers: dict[str, float], agent_weights: dict[str, float]):
    """Compute trust-weighted ensemble Brier score."""
    total_weight = sum(agent_weights.values())
    if total_weight == 0:
        return 0.25  # Baseline

    weighted_brier = sum(
        agent_briers.get(role, 0.25) * weight
        for role, weight in agent_weights.items()
    ) / total_weight

    return weighted_brier
```

## Safety Guardrails

1. **Never use Full Kelly** — always use ≤25% (Quarter Kelly)
2. **Cap maximum position** — regardless of Kelly, never exceed `MAX_POSITION_PCT`
3. **Require minimum calibration** — if ensemble Brier > 0.30, reduce to minimum tranche
4. **Correlation penalty** — if holding correlated positions, reduce Kelly fraction
5. **Volatility override** — in high-vol regimes, halve the Kelly fraction
