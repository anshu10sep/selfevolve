# 12 — Implementation Roadmap

## Phase 0: Unblock the Loop (1-2 days) 🚨
**Goal**: Make the evolution loop produce *any* signal

### P0.1: Fix Prediction Resolution (BUG-1)
**Files to modify**: `evolution/prediction_resolver.py`, `persistence/db.py`

1. Fix trade_id matching in `_determine_profitability()`:
   - Query by `client_order_id` column (not primary key `id`)
   - Add `client_order_id` lookup to the Trade model query
   - Fall back to ticker+timestamp fuzzy matching if exact match fails

2. Add `on_trade_closed()` integration:
   - Ensure `TradeEventPublisher.on_trade_closed()` is called from all trade close paths
   - Verify trade_id consistency between recording and resolution

3. Add staleness expiry:
   - Predictions older than 30 days with no resolution → mark as `EXPIRED`
   - Prevents infinite accumulation of unresolvable predictions

### P0.2: Fix Strategy Prediction Resolution (BUG-2)
**Files to modify**: `orchestration/strategy_signal_aggregator.py`, `evolution/prediction_resolver.py`

1. Add time-horizon resolution for `strat_` predictions:
   - After 5 trading days, check if the predicted direction was correct
   - Resolve based on price movement from prediction time to current

2. Store entry price in prediction metadata for later comparison

### P0.3: Ensure Per-Agent Predictions (BUG-3)
**Files to modify**: `main.py` (all `on_order_submitted` call sites)

1. Audit all 5 trade submission paths in main.py
2. Ensure `agent_predictions` dict is populated from available analyst scores
3. For crypto/intraday trades without full DAG, record at minimum the Judge's confidence as a prediction for the JUDGE role

### P0.4: Add Cold-Start Bootstrap
**Files to modify**: `evolution/trust_updater.py`

1. Replace hard minimum (5 predictions) with Bayesian prior blending
2. Allow trust updates with even 1 resolved prediction (weighted by prior)

**Verification**: After P0, run for 24 hours and confirm:
- [ ] `get_unresolved_trade_ids()` returns entries
- [ ] After trades close, `resolved_count > 0` in resolver logs
- [ ] `trust_weights_updated` shows `updated > 0`
- [ ] Evolution Report shows non-zero trust updates

---

## Phase 1: Close the Loop (3-5 days)
**Goal**: Full evolution cycle runs end-to-end

### P1.1: Fix Trust Decay/Boost Asymmetry
**File**: `evolution/reflexion.py`

Replace exponential decay/boost with EMA:
```python
alpha = 0.1
new_trust = alpha * performance_score + (1 - alpha) * old_trust
```

### P1.2: Trust Weights Feed Back to Trading
**Files**: `main.py`, `orchestration/trading_dag.py`

Ensure the Judge's scoring uses trust-weighted analyst scores:
```python
weighted_score = sum(score * trust for score, trust in analyst_data) / total_trust
```

### P1.3: Multi-Scale Brier
**File**: `evolution/reflexion.py`

Add 10/30/100 trade window Brier with weighted average.

### P1.4: Enhanced Evolution Report
**File**: `main.py`

Include in Telegram reports:
- Brier score per agent
- Trust weight changes
- Prediction resolution stats
- Top/bottom performing agents

**Verification**: After P1:
- [ ] Trust weights visibly change between cycles
- [ ] At least one agent shows trust decay or boost
- [ ] Telegram reports show per-agent Brier scores

---

## Phase 2: Intelligence Layer (1-2 weeks)
**Goal**: Evolution makes the system measurably better

### P2.1: Brier Decomposition
Add reliability/resolution/uncertainty breakdown to post-mortem analysis.

### P2.2: Regime-Conditioned Trust
Add `market_regime` column to prediction_records and agent_scores tables. Compute regime-specific Brier scores.

### P2.3: Drift Detection
Implement ADWIN detector per agent. Alert on drift, trigger immediate evolution.

### P2.4: Multi-Candidate Prompt Evolution
Generate 3 candidates per underperformer using different mutation strategies.

### P2.5: Walk-Forward Backtesting
Replace single-window with rolling train/test split. Add transaction cost modeling.

### P2.6: Dynamic Ticker Selection
Replace hardcoded `["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL"]` with dynamic selection from watchlist + recent trades.

---

## Phase 3: Optimization (2-4 weeks)
**Goal**: Advanced features for production-grade evolution

### P3.1: Bayesian Trust (Thompson Sampling)
Replace EMA trust with Beta-Bayesian posterior + Thompson sampling for agent selection.

### P3.2: Kelly Position Sizing
Integrate Brier-calibrated probabilities into fractional Kelly position sizing.

### P3.3: Sequential Testing (SPRT)
Replace fixed-horizon Welch's t-test with sequential probability ratio test for faster prompt promotion.

### P3.4: Strategy Regime Routing
Auto-activate/deactivate strategies based on detected market regime.

### P3.5: Calibration Dashboard
Real-time calibration curves per agent, accessible via dashboard API.

### P3.6: Cross-Agent Learning
Top-performing agent rules shared as candidates for similar underperforming agents.

---

## Priority Matrix

| Task | Impact | Effort | Priority |
|------|--------|--------|----------|
| Fix prediction resolution | 🔴 Critical | Medium | **P0 — NOW** |
| Fix strategy prediction resolution | 🟠 High | Low | **P0 — NOW** |
| Per-agent prediction recording | 🟡 Medium | Low | **P0 — NOW** |
| Cold-start bootstrap | 🟡 Medium | Low | **P0 — NOW** |
| Trust decay asymmetry | 🟠 High | Low | P1 |
| Trust→trading feedback | 🟠 High | Medium | P1 |
| Multi-scale Brier | 🟡 Medium | Low | P1 |
| Regime-conditioned trust | 🟠 High | Medium | P2 |
| Drift detection | 🟡 Medium | Medium | P2 |
| Walk-forward backtesting | 🟡 Medium | High | P2 |
| Bayesian trust | 🟡 Medium | High | P3 |
| Kelly sizing | 🟡 Medium | Medium | P3 |
| Sequential testing | 🟢 Nice-to-have | Medium | P3 |

---

## Success Metrics

After completing Phase 0-1, we should see:
- **≥5 resolved predictions per agent** within 1 week
- **Brier scores computed** for at least 5 agents
- **Trust weights changing** between evolution cycles
- **At least 1 prompt candidate** created by evolution
- **At least 1 post-mortem** generated for an underperformer

After Phase 2:
- **Regime-aware trust** with visible per-regime scoring
- **Drift detection** catches at least 1 regime change
- **Walk-forward backtest** results differ from simple backtest by >10%
- **Multiple prompt candidates** generated per cycle
