# Momentum Strategy — Learning Goals

## Current Focus (v1)
- [ ] Optimize entry_threshold for current market regime
- [ ] Test different lookback_period values (3, 5, 8, 10 days)
- [ ] Evaluate trailing stop vs fixed stop performance

## Learned Rules (max 3)
1. *No rules yet — strategy is in initial learning phase*

## Performance Targets
- Win Rate: > 50%
- Sharpe Ratio: > 0.5
- Max Drawdown: < 10%
- Profit Factor: > 1.2

## Regime Notes
- BULL: This is our best regime — increase allocation
- SIDEWAYS: Reduce position sizes, tighten stops
- BEAR: Consider pausing — momentum works against us in downtrends
