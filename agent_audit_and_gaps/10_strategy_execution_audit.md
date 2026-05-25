# 📈 Strategy Agents — Full Audit & Gaps

---

## Strategy Architecture Overview

The system has a robust strategy framework built on `StrategyAgent` (base class from `strategy_base.py`, 30K lines). This is the **most mature subsystem** alongside the evolution pipeline.

### Strategy Agents Implemented

| Strategy | File | Lines | Status |
|----------|------|:-----:|--------|
| **Base Framework** | `strategy_base.py` | 30,124 | ✅ Production-ready |
| **Strategy Evolution** | `strategy_evolution.py` | 15,057 | ✅ Production-ready |
| **Strategy Tracker** | `strategy_tracker.py` | 15,380 | ✅ Production-ready |
| **Daily Researcher** | `daily_researcher.py` | 19,504 | ✅ Production-ready |
| Momentum | `momentum_strategy.py` | 7,434 | ✅ Real implementation |
| Mean Reversion | `mean_reversion_strategy.py` | 9,381 | ✅ Real implementation |
| Breakout | `breakout_strategy.py` | 8,973 | ✅ Real implementation |
| Gap Fill | `gap_fill_strategy.py` | 8,893 | ✅ Real implementation |
| VWAP | `vwap_strategy.py` | 8,418 | ✅ Real implementation |
| Overnight Hold | `overnight_hold_strategy.py` | 9,714 | ✅ Real implementation |
| Pairs Trading | `pairs_strategy.py` | 11,402 | ✅ Real implementation |
| Crypto Momentum | `crypto_momentum_strategy.py` | 9,027 | ✅ Real implementation |
| Crypto Mean Reversion | `crypto_mean_reversion_strategy.py` | 9,395 | ✅ Real implementation |
| Crypto Scalper | `crypto_scalper_strategy.py` | 10,287 | ✅ Real implementation |

### Strategy Skill Directories (All Have Only goals.md)

| Skill Dir | Files | Status |
|-----------|-------|--------|
| `skills/breakout_strategy/` | `goals.md` only | ⚠️ No skill Python files |
| `skills/gap_fill_strategy/` | `goals.md` only | ⚠️ No skill Python files |
| `skills/mean_reversion_strategy/` | `goals.md` only | ⚠️ No skill Python files |
| `skills/momentum_strategy/` | `goals.md` only | ⚠️ No skill Python files |
| `skills/overnight_strategy/` | `goals.md` only | ⚠️ No skill Python files |
| `skills/pairs_strategy/` | `goals.md` only | ⚠️ No skill Python files |
| `skills/vwap_strategy/` | `goals.md` only | ⚠️ No skill Python files |

**Note**: The strategies don't need skills in the same way other agents do — their logic IS the strategy code itself. But they could benefit from auxiliary tools.

---

## Strategy Learning Skills ✅

The `skills/strategy_learning/` directory has **real, production-quality tools**:

| File | Purpose | Status |
|------|---------|--------|
| `strategy_learning.py` | Parameter fitness evaluation, evolution proposals, statistical tests | ✅ Real |
| `strategy_ledger.py` | Evolution event logging for strategies | ✅ Real |
| `regime_detection.py` | Market regime classification | ✅ Real |

These are used by the `StrategyResearcherAgent` — one of the few properly connected tool chains.

---

## Execution Layer Audit

| Component | File | Lines | Status |
|-----------|------|:-----:|--------|
| **Guardrails** | `execution/guardrails.py` | 10,548 | ✅ Production-ready |
| **Circuit Breaker** | `execution/circuit_breaker.py` | 8,372 | ✅ Production-ready |
| **Position Sizing** | `execution/position_sizing.py` | 8,057 | ✅ Production-ready |
| **Settlement Tracker** | `execution/settlement_tracker.py` | 5,302 | ✅ Production-ready |
| **Tranche Manager** | `execution/tranche_manager.py` | 6,057 | ✅ Production-ready |
| **Alpaca Client** | `broker/alpaca_client.py` | 9,902 | ✅ Production-ready |

### Execution Layer Gaps

| Gap | Severity | Description |
|-----|:--------:|-------------|
| EX-1 | 🟡 Medium | Circuit breaker not checked by Judge Agent |
| EX-2 | 🟡 Medium | Settlement tracker not queried before trades |
| EX-3 | 🟡 Medium | Position sizing not called as a tool by Judge |
| EX-4 | 🟢 Low | Tranche manager not integrated with Portfolio Manager |

---

## Research Layer Audit

| Component | File | Lines | Status |
|-----------|------|:-----:|--------|
| **Backtester** | `research/backtester.py` | 7,773 | ✅ Real implementation |
| **Screener** | `research/screener.py` | 4,535 | ✅ Real implementation |
| **Backtest Harness** | `research/strategy_backtest_harness.py` | 18,315 | ✅ Production-ready |

### Research Layer Gaps

| Gap | Severity | Description |
|-----|:--------:|-------------|
| RS-1 | 🟡 Medium | Backtester not accessible as a tool to any agent |
| RS-2 | 🟡 Medium | Screener not connected to analyst agents |
| RS-3 | 🟡 Medium | Strategy Researcher can't auto-trigger backtests |

---

## Crypto Skills

| Directory | Files | Status |
|-----------|-------|--------|
| `skills/crypto_analyst/` | 4 Python files | 🔴 Stubs |
| `skills/crypto_sentiment/` | 3 Python files | 🔴 Stubs |
| `skills/cto_crypto/` | 3 Python files | 🔴 Stubs |

**Crypto agents have stub skills** like the equities analysts.

---

## 🔴 Strategy System Gaps

### Gap ST-1: Strategy Skills Dirs Are Empty (🟢 LOW)
All 7 strategy skill directories only have `goals.md`. But this is low severity because the strategy logic IS the strategy code.

### Gap ST-2: No Tool Bridge to Execution Layer (🟡 MEDIUM)
Strategies can't directly call `position_sizing.calculate()` or `circuit_breaker.check()` as LLM tools. These are called procedurally by the DAG.

### Gap ST-3: Strategies Don't Subscribe to Events (🟡 MEDIUM)
Strategies don't receive market events from the Event Bus. They rely on being called by the orchestration DAG.

### Gap ST-4: Crypto Strategies Lack Data Integration (🟡 MEDIUM)
`integrations/crypto_data.py` (7.5K lines) exists but crypto strategies' skills are stubs.

---

## ✅ Strategy System Strengths

1. **Most mature subsystem** — 30K+ line strategy framework
2. **10 real strategy implementations** — not stubs
3. **Real backtesting** — 18K line backtest harness
4. **Real evolution** — parameter fitness, statistical significance, shadow testing
5. **Regime-aware** — strategies declare market regime affinities
6. **Real performance tracking** — win rates, Sharpe ratios, drawdowns
7. **Real execution layer** — guardrails, circuit breakers, position sizing
