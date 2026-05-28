# 04 — Trust Weight System

## Purpose

Trust weights determine how much each agent's opinion matters in ensemble decisions. They are the **mechanical teeth** of the evolution system — when an agent underperforms, its trust drops, reducing its influence on trading decisions.

## Current Implementation

### Trust Decay (reflexion.py, TrustDecayManager)

```python
# Decay: weight *= 0.95^consecutive_failures
decayed = current_weight * (0.95 ** consecutive_failures)
new_weight = max(0.1, decayed)  # Floor at 0.1

# Boost: weight *= 1.05 (capped at 1.0)
boosted = current_weight * 1.05
new_weight = min(1.0, boosted)
```

### Trust Update Logic (trust_updater.py)

```python
if brier < old_brier:          # Improved → boost
    new_trust = boost(old_trust)
elif brier > 0.35:             # Poor → decay
    new_trust = decay(old_trust, consecutive_failures)
else:                          # Stable → no change
    new_trust = old_trust
```

### Scorable Agents (21 total)

| Scoring Method | Agents |
|---------------|--------|
| **Brier Score** (11) | FUNDAMENTAL_ANALYST, TECHNICAL_ANALYST, SENTIMENT_ANALYST, MACRO_ANALYST, JUDGE, BULL, BEAR, PORTFOLIO_MANAGER, STRATEGY_RESEARCHER, MASTER, CRYPTO_ANALYST |
| **Operational** (10) | CTO, CSO, CRO, CEO, QA, PRODUCT, META_REVIEW, DEVELOPER, AUDITOR, PERFORMANCE_ANALYST |

## Problems with Current System

### 1. Asymmetric Decay/Boost
Decay: `0.95^n` → aggressive (10 failures = 0.60)
Boost: `1.05^1` → slow (10 successes = 0.63 → never recovers to 1.0 from 0.6)

An agent that has one bad week takes **months** to recover, even if it's performing perfectly afterward. This creates a "trust graveyard" where agents get stuck near the floor.

**Fix**: Use exponential moving average (EMA) instead:
```python
# EMA approach: responds equally to improvement and degradation
alpha = 0.1  # Learning rate
new_trust = alpha * performance_score + (1 - alpha) * old_trust
```

### 2. No Regime-Awareness
A BULL agent should naturally underperform in bear markets — that's expected, not a bug. But the current system decays its trust regardless of market context. When the market turns bullish again, the BULL agent's trust is too low to contribute meaningfully.

**Fix**: Regime-conditioned trust:
```python
regime = detect_current_regime()  # BULL, BEAR, SIDEWAYS, VOLATILE
trust_key = f"{agent_role}:{regime}"  # Separate trust per regime
```

### 3. No Confidence-Weighted Updates
If an agent makes 10 predictions at 51% confidence and gets 5 right, that's perfectly calibrated (Brier ≈ 0.25). But the system treats this the same as an agent that makes 10 predictions at 90% confidence and gets 5 right (Brier ≈ 0.41). The second agent is far more dangerous because it's overconfident.

**Fix**: Weight Brier updates by prediction confidence:
```python
weighted_brier = sum(
    conf * (pred - outcome) ** 2
    for pred, outcome, conf in zip(preds, outcomes, confidences)
) / sum(confidences)
```

### 4. Trust Doesn't Feed Back to Trading
Trust weights are computed but may not be used in the actual trading DAG. The `StrategySignalAggregator` uses `strategy.trust_weight`, but the main analyst DAG may not weight analyst scores by their trust.

**Fix**: Ensure the Judge's scoring formula uses trust weights:
```python
# In the Judge's prompt:
weighted_score = sum(
    analyst.score * analyst.trust_weight
    for analyst in analysts
) / sum(a.trust_weight for a in analysts)
```

## Proposed: Bayesian Trust System

Replace simple decay/boost with a Bayesian approach:

### Thompson Sampling for Agent Selection

Instead of fixed trust weights, model each agent as a Beta distribution:

```python
# Each agent has Beta(alpha, beta) prior
# alpha = successful predictions, beta = failed predictions
agent_priors = {
    "FUNDAMENTAL_ANALYST": {"alpha": 1, "beta": 1},  # Uniform prior
    "TECHNICAL_ANALYST": {"alpha": 1, "beta": 1},
    ...
}

def update_trust(agent, outcome):
    if outcome == 1:  # Correct prediction
        agent_priors[agent]["alpha"] += 1
    else:
        agent_priors[agent]["beta"] += 1

def get_trust_weight(agent):
    # Thompson sampling: draw from posterior
    return np.random.beta(
        agent_priors[agent]["alpha"],
        agent_priors[agent]["beta"]
    )

def get_expected_trust(agent):
    # Mean of posterior (for deterministic use)
    a = agent_priors[agent]["alpha"]
    b = agent_priors[agent]["beta"]
    return a / (a + b)
```

### Advantages of Bayesian Approach
1. **Natural cold-start handling**: Uniform prior (alpha=1, beta=1) = 0.5 trust until data arrives
2. **Uncertainty quantification**: New agents have wide confidence intervals
3. **Automatic exploration**: Thompson sampling naturally explores underrepresented agents
4. **No manual tuning**: No decay_rate, boost_factor, or min_weight parameters
5. **Regime-resilient**: Recent data weighted more via windowed priors

### ELO-Based Alternative

For competitive agent ranking:
```python
K = 32  # ELO K-factor
def update_elo(agent_rating, opponent_rating, actual_score):
    expected = 1 / (1 + 10 ** ((opponent_rating - agent_rating) / 400))
    new_rating = agent_rating + K * (actual_score - expected)
    return new_rating
```

ELO is useful when agents compete (BULL vs BEAR) but less natural for independent prediction scoring.

## Recommended Approach

**Phase 1** (immediate): Fix decay/boost asymmetry with EMA, add regime conditioning
**Phase 2** (next sprint): Implement Beta-Bayesian trust with Thompson sampling
**Phase 3** (future): Add confidence-weighted updates and multi-scale windows
