# ⚖️ Judge Agent (Risk Manager) — Full Audit & Gaps

## Agent Identity

| Attribute | Value |
|-----------|-------|
| **Class** | `JudgeAgent` (extends `BaseAgent`) |
| **File** | `src/agents/judge_agent.py` (158 lines) |
| **Role** | `AgentRole.JUDGE` |
| **Type** | `AgentType.SPECIALIST` |
| **LLM Tier** | Premium (by architecture spec) |
| **In SCORABLE_ROLES** | ✅ Yes |

---

## Core Responsibilities

The Judge is the **final, non-negotiable gateway** before trade execution:
1. Synthesize Bull vs Bear debate scores
2. Apply Macro Regime filter (PANIC → always PASS)
3. Calculate risk-adjusted position sizing (max 2% = $2.00)
4. Output strictly validated `ExecutionOrder` (Pydantic enforced)

---

## Methods Analysis

| Method | Type | Description | Production Ready? |
|--------|------|-------------|:-:|
| `evaluate()` | Hybrid | Hard rules + LLM evaluation | ✅ **Best in system** |
| `_safe_default()` | Code | Returns PASS on failure | ✅ Yes |

### `evaluate()` — Deep Dive

This is the **most production-ready method** in the entire system:

1. **Hard Rules (Non-LLM)** — Executes BEFORE LLM:
   - PANIC regime → instant PASS
   - Net conviction < 2.0 → instant PASS
2. **LLM Analysis** — Only reached if hard rules pass:
   - Reviews debate state, portfolio cash, current price, stop loss
   - Must output Pydantic `ExecutionOrder`
3. **Fail-Safe** — On ANY error → defaults to PASS (capital preservation)

### Output Schema (Pydantic Enforced)
```python
class ExecutionOrder(BaseModel):
    ticker: str
    action: ExecutionAction  # BUY, SELL, PASS
    confidence_score: float  # 0.0 to 10.0
    reasoning: str
    allocated_pct: Optional[float]  # Position size as % of portfolio
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
```

---

## Skills Audit (`skills/judge/`)

| File | Function | Status |
|------|----------|--------|
| `make_final_decision.py` | Make final trading decision | 🔴 **STUB** |
| `evaluate_proposals.py` | Evaluate trade proposals | 🔴 **STUB** |
| `resolve_conflicts.py` | Resolve bull/bear conflicts | 🔴 **STUB** |
| `goals.md` | Goals | ✅ Present |

**Gap**: Skills exist but are stubs AND are not used by the agent. The Judge's actual logic is all in `evaluate()` directly.

---

## Evolution / Learning

| Mechanism | Status | Notes |
|-----------|--------|-------|
| Brier Score Tracking | ✅ Active | In SCORABLE_ROLES |
| Trust Weight Updates | ✅ Active | Decay/boost |
| Post-Mortem Review | ✅ Active | Meta-Review evaluates |
| Prompt Evolution | ✅ Active | Shadow testing pipeline |

---

## 🔴 Gaps

### Gap JU-1: Skills Not Wired (🟡 MEDIUM)
The Judge has 3 skill files but doesn't use them. The real logic is hardcoded in `evaluate()`. This is actually less bad than other agents because the hardcoded logic IS production-quality. But the LLM should be able to call deterministic risk tools.

### Gap JU-2: No Position Sizing Tool Integration (🔴 HIGH)
The `execution/position_sizing.py` module has real position sizing calculations, but the Judge doesn't call it. Instead, it asks the LLM to output percentages. This contradicts the "no LLM arithmetic" principle.

**Current (Wrong)**:
```python
# LLM outputs allocated_pct → then some external code converts to dollars
```

**Should Be**:
```python
# Judge calls deterministic position_sizing.calculate() tool
# Tool returns exact share count and dollar amount
# Judge includes these in ExecutionOrder
```

### Gap JU-3: No Connection to Circuit Breaker (🟡 MEDIUM)
The `execution/circuit_breaker.py` has real circuit breaker logic but is not checked by the Judge. The Judge should query the circuit breaker state before allowing any BUY.

### Gap JU-4: No Settlement Awareness (🟡 MEDIUM)
The `execution/settlement_tracker.py` tracks T+2 settlement but the Judge doesn't check it. This risks Good Faith Violations (GFV) on a cash account.

### Gap JU-5: No Event Bus Publishing (🟢 LOW)
When the Judge makes a decision, it should publish `JUDGE_DECISION_MADE` to the Event Bus for the Journaling Agent and dashboard.

### Gap JU-6: No Audit Trail of Rejected Trades (🟡 MEDIUM)
When the Judge PASSes, there's no structured logging of WHY. The Journaling Agent should receive the full decision context.

---

## ✅ Strengths

1. **Best production-quality agent** — real hard rules, fail-safe defaults
2. **Pydantic-enforced output** — LLM can't hallucinate invalid orders
3. **PASS-by-default** — capital preservation is paramount
4. **Evolution support** — in SCORABLE_ROLES, gets Brier score tracking
5. **Proper separation** — deterministic rules run BEFORE LLM, not after
