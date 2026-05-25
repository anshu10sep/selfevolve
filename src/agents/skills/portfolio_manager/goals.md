# Portfolio Manager — Learning Goals

## Current Focus (v1)
- [ ] Calibrate SHARPE_WEIGHT vs RECENCY_WEIGHT vs REGIME_WEIGHT
- [ ] Tune kill switch thresholds (max drawdown, consecutive losses)
- [ ] Test different cash reserve percentages (15%, 20%, 25%)
- [ ] Validate regime detection accuracy

## Strategy Allocation Notes
- Start with equal allocation until performance data accumulates
- Minimum 20 trades per strategy before performance-based rebalancing
- Review allocation weekly, adjust monthly

## Risk Framework
- Portfolio max drawdown: 15% (absolute hard stop)
- Per-strategy max drawdown: 10% (auto-kill)
- Cash reserve: 20% minimum at all times
- Maximum 30% in any single strategy

## Regime Playbook
| Regime | Action |
|--------|--------|
| BULL | Overweight Momentum, Overnight; Underweight Mean Reversion |
| SIDEWAYS | Overweight Mean Reversion, VWAP, Pairs; Underweight Momentum |
| HIGH_VOL | Overweight Gap Fill, Mean Reversion; Reduce all position sizes |
| PANIC | 100% cash — no exceptions |
