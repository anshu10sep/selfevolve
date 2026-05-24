# Implementation Details: MVP Backtesting (Phase 1)

## Overview
Phase 1 (Backtesting) ensures the structural and mathematical soundness of the quantitative system. However, LLM backtesting is fraught with lookahead bias and massive API costs. We strictly separate deterministic code validation from LLM forward-walking.

---

## 1. Banish LLM Historical Backtesting

### The "Lookahead Bias" Problem
LLMs trained up to 2025 inherently know the market events of 2024. Feeding them historical data from 2024 to "backtest" their predictive power is fundamentally flawed and generates fraudulent Sharpe ratios. Furthermore, executing millions of API calls in a loop destroys the $100 budget.

### Implementation
- **Deterministic Component Testing Only**: We strictly isolate backtesting to the **Python Execution Layer** (rules, indicators, risk bounds). We use `VectorBT` or `Backtrader` to validate mathematical parameters without touching the LLM.
- **Forward-Paper-Testing Only**: The LLM Intelligence Layer is validated 100% via real-time, live forward-walking in Phase 2. Zero synthetic history is used for the LLM.

> [!WARNING]
> Do not attempt to backtest CrewAI orchestration over historical time-series data. It is a mathematical fallacy due to model training cutoffs.

---

## 2. Pessimistic Fill Routing

### The "Liquidity Illusion" Problem
Simple execution simulators assume perfectly timed limit order fills. In penny stock trading, assuming a stop-loss perfectly triggers at $10 during a gap-down will catastrophically underestimate risk.

### Implementation
- **Aggressively Pessimistic Simulator**:
  - **Gap Rule**: Fills during overnight gaps are explicitly calculated at the Open price of the gap candle, not the limit price.
  - **Liquidity Penalty**: Trades on assets with `<$5M` daily volume automatically suffer a 2% fill price penalty to simulate queueing and slippage.

```python
def calculate_synthetic_fill(order_type: str, limit_price: float, candle_open: float, candle_low: float, daily_volume: float) -> float:
    """Calculates a pessimistic fill price."""
    # Handle Gap Downs on Sell Stops
    if order_type == 'SELL_STOP' and candle_open < limit_price:
        fill_price = candle_open
    else:
        fill_price = limit_price
        
    # Apply Liquidity Penalty
    if daily_volume < 5_000_000:
        fill_price *= 0.98 # 2% slippage penalty
        
    return fill_price
```

---

## 3. Advanced Evolution Metrics

### The "Sharpe Ratio Manipulation" Problem
Systems easily manipulate Sharpe ratios by taking tiny profits and never closing massive losers. Overfitting to a single market regime (e.g., a 30-day bull run) creates a false sense of security.

### Implementation
- **Sortino & Calmar Ratios**: Replace Sharpe with the Sortino Ratio (penalizes only downside volatility) and the Calmar Ratio (Return vs. Max Drawdown). This mathematically prevents "hide the loss" strategies.
- **Cross-Regime Validation**: Deterministic parameters must be tested across 3 distinct synthetic regimes:
  1. **Bull Run** (e.g., 2021)
  2. **Bear Crash** (e.g., 2022)
  3. **Sideways Chop** (e.g., mid-2023)
  
Evolution is only approved if positive Expected Value (EV) is proven across the aggregate of all three environments.
