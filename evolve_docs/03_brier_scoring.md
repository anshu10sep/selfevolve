# 03 — Brier Scoring & Calibration

## What Is a Brier Score?

The Brier Score is a **proper scoring rule** that measures the accuracy of probabilistic predictions. It's the mean squared error between predicted probabilities and actual binary outcomes.

```
BS = (1/N) × Σ(predicted_probability - actual_outcome)²
```

| Score | Meaning |
|-------|---------|
| 0.000 | Perfect calibration (impossible in trading) |
| 0.100 | Excellent — well-calibrated agent |
| 0.200 | Good — better than random |
| 0.250 | Baseline — random guessing at 50% |
| 0.350 | Poor — worse than random |
| 1.000 | Perfectly wrong |

## Current Implementation

**File**: `evolution/reflexion.py`, `BrierScoreEngine`

```python
@staticmethod
def calculate(predictions: list[float], outcomes: list[int]) -> float:
    if not predictions or len(predictions) != len(outcomes):
        return 0.5  # Baseline
    n = len(predictions)
    brier = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / n
    return round(brier, 4)
```

**Current Config** (constants.py):
- `BRIER_WINDOW_SIZE = 30` — rolling window of last 30 trades
- Thresholds: `GOOD < 0.20`, `BASELINE = 0.25`, `POOR > 0.35`

## Problems with Current Implementation

### 1. Cold-Start Problem
The system requires ≥5 resolved predictions before computing Brier (trust_updater.py line 149). But with 0 resolved predictions, we never get started. This creates a **chicken-and-egg problem**: no scores → no evolution → no improvement → no confidence to trade → no predictions.

**Fix**: Use **Bayesian priors** instead of hard minimums:
```python
# Instead of requiring 5 predictions:
if len(predictions) < 5:
    return {"updated": False, "reason": "Insufficient data"}

# Use a prior that decays:
prior_weight = max(0, (5 - len(predictions)) / 5)  # 1.0 at 0 preds, 0.0 at 5+
prior_brier = 0.25  # Assume baseline until proven otherwise
actual_brier = calculate(predictions, outcomes)
blended_brier = prior_weight * prior_brier + (1 - prior_weight) * actual_brier
```

### 2. No Brier Decomposition
The current implementation only computes the overall score. Professional systems decompose Brier into three components:

```
Brier = Reliability - Resolution + Uncertainty
```

- **Reliability**: How well-calibrated are probabilities? (lower = better)
- **Resolution**: How much do predictions differ from the base rate? (higher = better)
- **Uncertainty**: Inherent randomness of the domain (not controllable)

This tells you whether an agent is **miscalibrated** (reliability issue) or **uninformative** (resolution issue) — they need different fixes.

### 3. No Calibration Curves
We should track and visualize per-agent calibration curves:
- Bin predictions by probability range (0-10%, 10-20%, ..., 90-100%)
- Compare expected frequency vs actual frequency
- Agents above the diagonal are overconfident; below are underconfident

### 4. Single Window Size
Using a fixed 30-trade window misses temporal patterns:
- Short window (10): Catches recent regime changes but noisy
- Medium window (30): Balanced
- Long window (100): Stable but slow to react

**Best Practice**: Multi-scale Brier with weighted average:
```python
brier_10 = calculate(last_10_preds, last_10_outcomes)
brier_30 = calculate(last_30_preds, last_30_outcomes)
brier_100 = calculate(last_100_preds, last_100_outcomes)
combined = 0.5 * brier_10 + 0.3 * brier_30 + 0.2 * brier_100
```

## Proposed Improvements

### Enhanced Brier Engine

```python
class BrierScoreEngine:
    @staticmethod
    def calculate_decomposed(predictions, outcomes):
        """Return full Brier decomposition."""
        brier = mean_squared_error(predictions, outcomes)

        # Bin predictions for calibration analysis
        bins = np.linspace(0, 1, 11)
        bin_indices = np.digitize(predictions, bins) - 1

        reliability = 0.0
        resolution = 0.0
        base_rate = np.mean(outcomes)

        for b in range(len(bins) - 1):
            mask = bin_indices == b
            n_b = np.sum(mask)
            if n_b == 0:
                continue
            avg_pred = np.mean(predictions[mask])
            avg_outcome = np.mean(outcomes[mask])
            reliability += n_b * (avg_pred - avg_outcome) ** 2
            resolution += n_b * (avg_outcome - base_rate) ** 2

        n = len(predictions)
        reliability /= n
        resolution /= n
        uncertainty = base_rate * (1 - base_rate)

        return {
            "brier_score": round(brier, 4),
            "reliability": round(reliability, 4),
            "resolution": round(resolution, 4),
            "uncertainty": round(uncertainty, 4),
            "calibration_error": round(reliability, 4),
            "sharpness": round(resolution, 4),
        }

    @staticmethod
    def multi_scale_brier(predictions, outcomes, windows=[10, 30, 100]):
        """Compute Brier at multiple time scales."""
        scores = {}
        for w in windows:
            if len(predictions) >= w:
                scores[f"brier_{w}"] = BrierScoreEngine.calculate(
                    predictions[-w:], outcomes[-w:]
                )
        return scores
```

### Log-Loss Alternative

For agents that make high-confidence predictions, Log Loss (cross-entropy) is more discriminating than Brier:

```
LogLoss = -(1/N) × Σ[y·log(p) + (1-y)·log(1-p)]
```

Log Loss **heavily penalizes confident wrong predictions** (e.g., predicting 0.95 when outcome is 0), making it better for identifying overconfident agents.

### Calibration Check at Recording Time

Don't wait for evolution cycles. Check calibration continuously:

```python
async def check_running_calibration(agent_role: str):
    """Alert if agent shows systematic miscalibration."""
    preds = get_recent_predictions(agent_role, limit=20)
    if len(preds) < 10:
        return

    # Quick calibration check
    high_conf = [p for p in preds if p["predicted_probability"] > 0.7]
    if high_conf:
        actual_win_rate = sum(1 for p in high_conf if p["actual_outcome"] == 1) / len(high_conf)
        if actual_win_rate < 0.5:
            # Agent is severely overconfident
            alert(f"⚠️ {agent_role} overconfidence detected: "
                  f"predicts >70% but wins only {actual_win_rate:.0%}")
```
