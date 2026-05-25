# 💼 Portfolio Manager — Full Audit & Gaps

## Agent Identity

| Attribute | Value |
|-----------|-------|
| **Class** | `PortfolioManager` (extends `BaseAgent`) |
| **File** | `src/agents/portfolio_manager.py` (401 lines) |
| **Role** | `AgentRole.AUDITOR` (⚠️ Wrong role — should be PORTFOLIO_MANAGER) |
| **Type** | `AgentType.MANAGER` |
| **LLM Usage** | Minimal (commentary only, allocation is deterministic) |

---

## Core Architecture

The Portfolio Manager is a **deterministic capital allocator**. This is one of the strongest implementations in the system because:
- Capital allocation uses **pure math** (no LLM)
- The LLM is ONLY used for commentary generation (reports for Jarvis)
- Has real risk limits, kill switches, and regime-based allocation

### Allocation Formula
```
Weight(i) = (sharpe_w × risk_adj_return) + (recency_w × recent_perf) 
           + (regime_w × regime_fit) - (dd_penalty × current_drawdown)
```

### Risk Limits (Hardcoded Constants)
- `MIN_CASH_RESERVE_PCT = 0.20` (always 20% cash)
- `MAX_SINGLE_STRATEGY_PCT = 0.30` (no strategy > 30%)
- `MAX_DRAWDOWN_KILL_PCT = 10.0` (kill at 10% drawdown)
- `MAX_CONSECUTIVE_LOSSES = 8` (kill after 8 losses)

---

## Methods Analysis

| Method | Type | Description | Production Ready? |
|--------|------|-------------|:-:|
| `register_strategy()` | Code | Register a strategy agent | ✅ Yes |
| `calculate_allocations()` | **Deterministic** | Core allocation engine | ✅ **Excellent** |
| `_calculate_strategy_score()` | **Deterministic** | Composite scoring | ✅ **Excellent** |
| `_kill_strategy()` | Code | Shut down strategy | ✅ Yes |
| `revive_strategy()` | Code | Reactivate strategy | ✅ Yes |
| `update_equity()` | Code | Update total equity | ✅ Yes |
| `get_portfolio_state()` | Code | Full state report | ✅ Yes |
| `generate_allocation_commentary()` | LLM | Strategic commentary | 🟡 LLM-only |
| `set_regime()` | Code | Update market regime | ✅ Yes |

---

## Skills Audit (`skills/portfolio_manager/`)

| File | Status |
|------|--------|
| `goals.md` | ✅ Present |
| (no skill .py files) | 🔴 **No skills at all** |

---

## Inter-Agent Communication

| Path | Method | Status |
|------|--------|--------|
| PM ← Strategies | `register_strategy()` and performance tracking | ✅ Working |
| PM → Strategies | `strategy.set_allocation(capital)` | ✅ Working |
| PM → Jarvis | Via `get_portfolio_state()` (called by main.py) | ✅ Working |
| PM ← Macro Analyst | Via `set_regime()` (called by trading_dag) | ✅ Working |
| PM → Event Bus | Not connected | 🔴 Missing |

## Evolution / Learning

| Mechanism | Status |
|-----------|--------|
| Brier Score | ❌ Not a SCORABLE_ROLE |
| Trust Weights | ❌ Not tracked |
| Performance Learning | 🟡 Tracks strategy performance (StrategyPerformanceTracker) |
| Allocation History | ✅ Records all allocation decisions |

---

## 🔴 Gaps

### Gap PM-1: Wrong AgentRole (🟡 MEDIUM)
Uses `AgentRole.AUDITOR` instead of a dedicated `AgentRole.PORTFOLIO_MANAGER`. This causes confusion and potential conflicts with the actual Auditor Agent.

### Gap PM-2: No Skills Directory (🟡 MEDIUM)
Has a `skills/portfolio_manager/` directory with only `goals.md`. No real tools. Should have:
- `rebalance_portfolio()` — Trigger rebalance
- `compute_var()` — Value at Risk calculation
- `correlation_matrix()` — Strategy correlation analysis
- `drawdown_report()` — Historical drawdown analysis

### Gap PM-3: Not in Evolution Pipeline (🟡 MEDIUM)
PM's allocation decisions are never evaluated for quality. Should track:
- Did the allocation match the regime correctly?
- Did capital flow to winning strategies?
- Were kill decisions correct?

### Gap PM-4: No Event Bus Integration (🟢 LOW)
Should publish `ALLOCATION_CHANGED`, `STRATEGY_KILLED`, `REBALANCE_EXECUTED` events.

### Gap PM-5: No Persistence of Allocation History (🟡 MEDIUM)
Allocation history is stored in-memory (`_allocation_history`). Should persist to PostgreSQL via `persistence/db.py`.

---

## ✅ Strengths

1. **Truly deterministic** — No LLM makes capital decisions
2. **Strong risk controls** — Kill switches, concentration limits, cash reserve
3. **Regime-aware** — Adjusts allocations based on market regime
4. **Well-integrated with strategies** — Direct `set_allocation()` calls
5. **PANIC mode** — 100% cash on PANIC regime
