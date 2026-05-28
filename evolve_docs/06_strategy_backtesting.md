# 06 — Strategy Backtesting

## Current System

**File**: `research/backtester.py`

Two strategies are hardcoded:
1. **Momentum**: Buy when 5-day return > 2%, hold for 5 days
2. **Mean Reversion (RSI)**: Buy when RSI < 30, sell when RSI > 70

The continuous evolution cycle backtests 5 hardcoded tickers (`AAPL, NVDA, MSFT, TSLA, GOOGL`) and reports which strategy "wins" on each ticker.

## Problems

### 1. Only 2 Strategies Tested
The system has **11 strategy agents** (momentum, mean_reversion, breakout, gap_fill, vwap, overnight_hold, pairs, crypto_momentum, crypto_mean_reversion, crypto_scalper, daily_researcher) but only backtests 2 of them.

### 2. Fixed Parameters
Strategy parameters are hardcoded in the backtester. Real evolution should test parameter variations:
- Momentum lookback: 20, 40, 60, 120 days
- RSI period: 7, 14, 21
- Entry threshold: 1%, 2%, 3%

### 3. No Walk-Forward Optimization
All backtests use the same lookback window. This causes **overfitting** — a strategy that looks great on the last 60 days may have been terrible the month before.

### 4. No Transaction Costs
Backtests don't account for spreads, commissions, or slippage. This inflates apparent returns, especially for high-frequency strategies.

### 5. No Regime Context
The same backtest runs regardless of market conditions. A momentum strategy should be tested against *similar regime periods*, not arbitrary calendar windows.

## Best Practices: Walk-Forward Optimization

### The Gold Standard

```
|← Train (252 days) →|← Test (63 days) →|
                     |← Train (252 days) →|← Test (63 days) →|
                                          |← Train (252 days) →|← Test (63 days) →|
```

- **Train window**: Optimize parameters on historical data
- **Test window**: Validate on UNSEEN data (never used for optimization)
- **Roll forward**: Shift both windows by the test period length
- **Combine**: Performance is measured ONLY on test windows

```python
class WalkForwardBacktester:
    def __init__(self, train_days=252, test_days=63, step_days=63):
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days

    async def walk_forward(self, strategy, ticker, total_days=756):
        """Run walk-forward optimization."""
        bars = await self.market_data.get_bars(ticker, limit=total_days)
        results = []

        start = 0
        while start + self.train_days + self.test_days <= len(bars):
            train = bars[start : start + self.train_days]
            test = bars[start + self.train_days : start + self.train_days + self.test_days]

            # Optimize parameters on train set
            best_params = self.optimize_params(strategy, train)

            # Evaluate on test set with optimized params
            test_result = self.evaluate(strategy, test, best_params)
            results.append(test_result)

            start += self.step_days

        return self.aggregate_results(results)
```

### Regime-Aware Backtesting

```python
async def regime_backtest(self, strategy, ticker):
    """Test strategy performance per regime."""
    bars = await self.get_extended_bars(ticker, days=500)
    regime_results = {}

    for regime in ["BULL", "BEAR", "SIDEWAYS", "VOLATILE"]:
        regime_bars = self.filter_by_regime(bars, regime)
        if len(regime_bars) > 20:
            result = self.evaluate(strategy, regime_bars)
            regime_results[regime] = result

    return regime_results
```

### Realistic Execution Modeling

```python
def apply_execution_costs(self, trades, slippage_bps=5, commission_per_trade=0):
    """Apply realistic execution costs to backtest trades."""
    for trade in trades:
        # Slippage: assume entry/exit are worse by slippage_bps
        trade["entry_price"] *= (1 + slippage_bps / 10000)
        trade["exit_price"] *= (1 - slippage_bps / 10000)
        trade["commission"] = commission_per_trade * 2  # Buy + sell
        trade["pnl"] -= trade["commission"]
        trade["pnl_pct"] = (trade["exit_price"] - trade["entry_price"]) / trade["entry_price"] * 100
    return trades
```

## Proposed Backtester v2

### Dynamic Ticker Selection
Replace hardcoded list with the system's actual watchlist + recent trade tickers:

```python
async def get_backtest_tickers(self):
    """Dynamically select tickers for backtesting."""
    tickers = set()

    # From DEFAULT_WATCHLIST (constants.py)
    from config.constants import DEFAULT_WATCHLIST
    tickers.update(DEFAULT_WATCHLIST[:10])

    # From recent trades
    recent = get_recent_trades(limit=20)
    tickers.update(t["ticker"] for t in recent)

    # From today's screener candidates
    candidates = system_state.get("today_candidates", [])
    tickers.update(c["ticker"] for c in candidates[:5])

    return list(tickers)[:15]  # Cap at 15 for latency
```

### Test All Registered Strategies

```python
async def backtest_all_strategies(self, ticker):
    """Run all registered strategy agents through backtesting."""
    from agents.strategies.strategy_evolution import strategy_evolution_engine
    results = {}

    for name, strategy in strategy_evolution_engine._strategies.items():
        try:
            result = await strategy.backtest(
                ticker=ticker,
                bars=bars,
                lookback_days=60,
            )
            results[name] = result
        except Exception as e:
            results[name] = {"error": str(e)}

    return results
```

### Multi-Metric Evaluation

Don't just use Sharpe. Evaluate strategies on:

| Metric | Description | Threshold |
|--------|-------------|-----------|
| Sharpe Ratio | Risk-adjusted return | > 0.5 |
| Sortino Ratio | Downside-only risk | > 0.7 |
| Max Drawdown | Worst peak-to-trough | < 15% |
| Win Rate | % profitable trades | > 45% |
| Profit Factor | Gross profit / gross loss | > 1.3 |
| Calmar Ratio | Annual return / max drawdown | > 0.5 |
| Trades per Month | Activity level | 2-20 |

A strategy must pass **ALL** thresholds to be considered production-ready.
