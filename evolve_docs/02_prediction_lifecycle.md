# 02 — Prediction Lifecycle

## The Critical Gap

The prediction lifecycle is the **foundation** of the evolution system. Without it, nothing evolves. Currently, predictions are **recorded** but never **resolved** — which means Brier scores stay at baseline (0.5), trust weights never update, and the entire reflexion loop is inert.

## Current Flow

### Step 1: Recording (✅ Working)

When a trade is submitted, `TradeEventPublisher.on_order_submitted()` records predictions:

```python
# core/trade_event_publisher.py, line 91
for agent_role, predicted_prob in agent_predictions.items():
    prediction_tracker.record_prediction(
        agent_role=agent_role,
        trade_id=trade_id,        # client_order_id
        ticker=ticker,
        predicted_probability=predicted_prob,
        confidence=normalized_confidence,
    )
```

**Where predictions come from** (main.py, line 948-954):
```python
agent_predictions = {}
for role in ["fundamental", "technical", "sentiment", "macro"]:
    score_data = result.get(f"{role}_score", {})
    if score_data.get("score") is not None:
        prob = (float(score_data["score"]) + 1.0) / 2.0  # Normalize (-1,1) → (0,1)
        agent_predictions[f"{role.upper()}_ANALYST"] = prob
```

**Problem**: If the DAG didn't produce analyst scores (e.g., simple crypto trade), `agent_predictions` is empty, so `on_order_submitted` falls back to a single `SYSTEM_ANALYST` prediction. This means only 1 prediction per trade instead of 4+ analyst predictions.

### Step 2: Resolution (❌ BROKEN)

The `PredictionResolver` runs every 5 minutes as a background loop and should resolve predictions when trades close:

```python
# evolution/prediction_resolver.py, line 89
async def _resolve_stock_predictions(self):
    unresolved = get_unresolved_trade_ids()     # predictions with NULL actual_outcome
    positions = await alpaca.get_positions()      # currently held positions
    open_tickers = {pos["symbol"] for pos in positions}

    for trade_info in unresolved:
        if ticker in open_tickers:
            continue  # Still open, skip

        # Position gone → trade closed. Determine profitability.
        profitable = await self._determine_profitability(trade_id, ticker)
        prediction_tracker.resolve_trade(trade_id, profitable)
```

**THREE Critical Bugs:**

#### Bug A: trade_id Mismatch

Predictions are keyed by `trade_id` (which is `client_order_id`, a UUID like `se_AAPL_20260527_1430_abc123`). But `_determine_profitability()` looks up `Trade.id` in the DB — which may use the Alpaca order ID (a different UUID). If the trade_id in predictions doesn't match the primary key in the trades table, the lookup returns `None`, and the prediction stays unresolved forever.

#### Bug B: Ticker-Level Resolution is Too Coarse

The resolver checks if a **ticker** is in current positions. But if you bought AAPL twice (two separate trades with different trade_ids), closing one AAPL position would NOT remove AAPL from positions. The resolver would skip both trades, thinking AAPL is still open.

#### Bug C: No Fallback for Non-Trade Predictions

Strategy predictions use `trade_id = f"strat_{ticker}_{timestamp}"` (strategy_signal_aggregator.py, line 223). These trade_ids don't correspond to any real Alpaca orders, so they can NEVER be resolved through the current position-checking mechanism.

### Step 3: Brier Scoring (✅ Working, if data exists)

Once predictions are resolved, the Brier engine works correctly:

```python
# evolution/reflexion.py
brier = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / n
```

## Root Cause Analysis

| Issue | Impact | Severity |
|-------|--------|----------|
| trade_id mismatch between predictions and trades table | Profitability lookup always returns None | 🔴 Critical |
| Ticker-level resolution can't handle multiple positions per ticker | Trades stay unresolved even after partial close | 🟠 High |
| Strategy predictions have synthetic trade_ids with no resolution path | Strategy Brier scores never computed | 🟠 High |
| Fallback to SYSTEM_ANALYST when no agent_predictions provided | Only 1 prediction per trade instead of per-agent | 🟡 Medium |
| No time-based resolution (stale predictions never expire) | Unresolved predictions accumulate forever | 🟡 Medium |

## Proposed Fix: Multi-Strategy Resolution

### Approach 1: Event-Driven Resolution (Recommended)

Replace position-polling with event-driven resolution:

```python
# When TradeEventPublisher.on_trade_closed() fires:
#   1. It already calls prediction_tracker.resolve_trade(trade_id, profitable)
#   2. The trade_id it passes is the SAME client_order_id used at recording
#   3. This guarantees ID match

# But the problem: on_trade_closed() is only called from market_close and
# position_review — both of which use DIFFERENT trade_id formats.
```

### Approach 2: Dual-ID Resolution

Store BOTH the client_order_id AND the Alpaca order_id in predictions:

```python
class PredictionRecord:
    trade_id = ...           # client_order_id (for matching at record time)
    alpaca_order_id = ...    # Alpaca order UUID (for matching at resolution time)
```

### Approach 3: Time-Horizon Resolution (for Strategy Predictions)

Strategy predictions don't have real trades. Resolve them by checking if the predicted direction was correct after N days:

```python
async def resolve_strategy_predictions(self):
    """Resolve strat_ predictions after their time horizon expires."""
    unresolved = get_unresolved_strategy_predictions()
    for pred in unresolved:
        created = pred["created_at"]
        if (now - created) > timedelta(days=5):  # 5-day horizon
            current_price = await get_current_price(pred["ticker"])
            entry_price = pred.get("entry_price", current_price)
            profitable = current_price > entry_price
            resolve_prediction(pred["id"], profitable)
```

## Recommendation

Use a **hybrid approach**:
1. **Event-driven** for real trades (Approach 1) — fix the ID mismatch
2. **Time-horizon** for strategy predictions (Approach 3) — auto-resolve after 5 days
3. **Staleness expiry** — discard predictions older than 30 days that were never resolved
4. **Add alpaca_order_id** to PredictionRecord for cross-referencing (Approach 2)
