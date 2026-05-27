# 11 — Current Bugs & Gaps

## Critical Bugs (System is Inert)

### BUG-1: Prediction Resolution Never Happens (🔴 CRITICAL)
**Status**: Root cause identified, fix designed
**Impact**: Evolution loop runs on zero signal — nothing evolves

**Root Cause Chain**:
1. `PredictionResolver._resolve_stock_predictions()` queries `get_unresolved_trade_ids()` — returns trade_ids with NULL `actual_outcome`
2. For each unresolved trade, it checks if the ticker is still in Alpaca positions
3. If ticker is gone → calls `_determine_profitability(trade_id, ticker)` which looks up `Trade.id == trade_id`
4. **BUT**: The `trade_id` in `prediction_records` is the `client_order_id` (e.g., `se_AAPL_20260527_1430_abc123`), while `Trade.id` may be the Alpaca UUID. **ID mismatch → lookup always returns None.**
5. Fallback `_check_alpaca_order(trade_id)` tries to get the order by client_order_id — may work but only for simple orders (not bracket orders)
6. Result: predictions stay unresolved forever

**Files**:
- `evolution/prediction_resolver.py` lines 196-226
- `persistence/db.py` — Trade model vs PredictionRecord.trade_id

### BUG-2: Strategy Predictions Have No Resolution Path (🟠 HIGH)
**Impact**: Strategy agent Brier scores never computed

Strategy signal aggregator creates predictions with synthetic trade_ids:
```python
trade_id = f"strat_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M')}"
```
These don't correspond to any Alpaca order, so the resolver can never match them to a real trade outcome.

**File**: `orchestration/strategy_signal_aggregator.py` line 223

### BUG-3: agent_predictions Often Empty (🟡 MEDIUM)
**Impact**: Predictions are recorded as single "SYSTEM_ANALYST" instead of per-analyst

The recording code (main.py line 948-954) extracts analyst predictions from `result.get(f"{role}_score", {})`. But this only works when the full DAG runs (market_open phase). For crypto trades, position reviews, and intraday scans, `agent_predictions` is empty, so only a single SYSTEM_ANALYST prediction is recorded.

This means we never get per-analyst Brier data for FUNDAMENTAL_ANALYST, TECHNICAL_ANALYST, etc.

---

## Recently Fixed Bugs (✅)

### BUG-4: Readiness Always 0% ✅ FIXED
**Fix**: Changed `auditor.run_audit()` → `auditor.full_audit()` and `audit.get("readiness_score", 0)` → `audit.readiness_score`
**Files**: `main.py` lines 1628-1629 and 2058-2059

### BUG-5: SystemAuditor Scanned Wrong Directory ✅ FIXED
**Fix**: Removed double `src/` path append in `full_audit()`
**File**: `agents/skills/jarvis/system_audit.py` line 67

### BUG-6: "Strategies tested: 5" Misleading ✅ FIXED
**Fix**: Changed label to "Backtested: 5 tickers × 2 strategies" with winner breakdown
**File**: `main.py` line 1672

### BUG-7: Evolution Schedule Misaligned ✅ FIXED
**Fix**: Changed `CronTrigger(hour='1,7,13,19')` to `CronTrigger(hour='3,11,17,21')`
**File**: `main.py` line 707

---

## Architectural Gaps

### GAP-1: No Brier Decomposition
The system computes overall Brier but doesn't decompose into reliability, resolution, and uncertainty. Without this, post-mortems can't distinguish between miscalibration and lack of informativeness.

### GAP-2: No Regime-Conditioned Trust
Trust weights are regime-agnostic. A BULL agent naturally underperforms in bear markets, but its trust decays regardless, crippling it when the bull market returns.

### GAP-3: No Drift Detection
No automated mechanism to detect when an agent or strategy's performance degrades unexpectedly. The system relies on 6-hourly evolution cycles to catch problems.

### GAP-4: No Kelly Position Sizing
Position sizes are fixed (ATR-based) regardless of prediction confidence or agent calibration quality.

### GAP-5: Trust Weights Don't Feed Back to Trading
The Judge's scoring formula may not incorporate analyst trust weights, making the trust system decorative rather than functional.

### GAP-6: Single-Candidate Prompt Evolution
Only one prompt mutation is generated per underperformer per cycle. Professional systems test multiple candidates in parallel.

### GAP-7: No Calibration Monitoring
No real-time check for agent overconfidence. The system waits for evolution cycles instead of catching calibration drift immediately.

### GAP-8: Cold-Start Chicken-and-Egg
Requires ≥5 resolved predictions to compute Brier. With 0 resolutions, we never get started. Need Bayesian priors or bootstrapped initial scores.

### GAP-9: Backtest Limited to 2 Strategies × 5 Tickers
11 strategy agents exist but only 2 are backtested. Dynamic ticker selection not implemented.

### GAP-10: No Walk-Forward Optimization
Single-window backtesting prone to overfitting. No train/test split, no out-of-sample validation.
