# ⚔️ Debate Agents (Bull & Bear) — Full Audit

## Agent Summary

| Attribute | Bull Agent | Bear Agent |
|-----------|:-:|:-:|
| **Class** | `BullAgent` | `BearAgent` |
| **File** | `debate_agents.py` (108 lines) | `debate_agents.py` |
| **Role** | `AgentRole.BULL` | `AgentRole.BEAR` |
| **Type** | `AgentType.SPECIALIST` | `AgentType.SPECIALIST` |
| **Output Schema** | ❌ Free-form dict | ❌ Free-form dict |
| **In SCORABLE_ROLES** | ❌ No | ❌ No |

---

## Architecture

Both agents follow a simple invoke-and-return pattern:
1. Receive aggregated research data from all 4 analysts
2. Build opposing argument (3 bullet points, max 150 words)
3. Output a conviction score (0-10) and argument text
4. Run in **parallel** during the debate phase
5. Outputs feed into the Judge Agent for final decision

### Intended Flow
```
Analyst Scores → Aggregation → Bull/Bear PARALLEL debate → Judge evaluates → ExecutionOrder
```

---

## Skills Audit

### Bull Agent Skills (`skills/bull/`)

| File | Function | Status |
|------|----------|--------|
| `identify_bullish_signals.py` | Find bullish signals | 🔴 **STUB** |
| `long_position_analysis.py` | Analyze long positions | 🔴 **STUB** |
| `long_skills.py` | Aggregator | 🔴 **STUB** |
| `growth_potential_assessment.py` | Assess growth | 🔴 **STUB** |
| `goals.md` | Goals | ✅ Present |

### Bear Agent Skills (`skills/bear/`)

| File | Function | Status |
|------|----------|--------|
| `identify_bearish_signals.py` | Find bearish signals | 🔴 **STUB** |
| `short_position_analysis.py` | Analyze short positions | 🔴 **STUB** |
| `short_skills.py` | Aggregator | 🔴 **STUB** |
| `risk_assessment.py` | Assess risk | 🔴 **STUB** |
| `goals.md` | Goals | ✅ Present |

---

## Methods Analysis

| Method | Agent | Type | Description | Production Ready? |
|--------|-------|------|-------------|:-:|
| `argue(ticker, aggregated_data)` | Bull | LLM | Build bull case | 🟡 LLM-only, no tools |
| `argue(ticker, aggregated_data)` | Bear | LLM | Build bear case | 🟡 LLM-only, no tools |
| `_safe_default(error)` | Both | Code | Neutral score on failure | ✅ Yes |

## Inter-Agent Communication

| Path | Method | Status |
|------|--------|--------|
| Analysts → Bull/Bear | Via `trading_dag.py` (data passed) | ✅ Working |
| Bull/Bear → Judge | Via `debate_workflow.py` (outputs aggregated) | ✅ Working |
| Bull ↔ Bear | None (parallel, no interaction) | By Design |
| Bull/Bear → Event Bus | Not connected | 🔴 Missing |
| Bull/Bear → Meta-Review | Not tracked | 🔴 Missing |

## Evolution / Learning

| Mechanism | Status | Notes |
|-----------|--------|-------|
| Brier Score Tracking | 🔴 Not tracked | NOT in SCORABLE_ROLES |
| Trust Weight Updates | 🔴 Not tracked | No decay/boost |
| Post-Mortem Review | 🔴 Never reviewed | Meta-Review doesn't evaluate them |
| Strategic Nuance Evolution | 🔴 Never evolves | No prompt mutation |
| Domain Isolation | ✅ Enforced by Identity Core | Prompts stay in domain |

---

## 🔴 Gaps

### Gap D-1: Not in SCORABLE_ROLES — No Evolution (🔴 CRITICAL)
Bull and Bear agents are excluded from the entire evolution pipeline. Their prompts **never improve**. They are the same quality as day 1 forever. This violates the core thesis of self-evolution.

### Gap D-2: No Pydantic Output Schema (🟡 MEDIUM)
Both agents return free-form dicts instead of Pydantic-validated structured output. The `argue()` method should use:
```python
class DebateArgument(BaseModel):
    argument: str          # max 150 words
    conviction_score: float  # 0 to 10
    key_data_points: list[str]  # What data supported the argument
```

### Gap D-3: Skills Not Wired (🔴 HIGH)
Both have skill directories with 4+ skill files but NONE are used. The LLM can't call `identify_bullish_signals()` or `risk_assessment()` during debate.

### Gap D-4: No Prediction Tracking (🟡 MEDIUM)
Their bull_score/bear_score outputs are never recorded as predictions in the `prediction_tracker`. This means:
- No Brier score computation possible
- No way to evaluate if Bull is consistently over-optimistic
- No way to tell if Bear is consistently too cautious

### Gap D-5: No Historical Pattern Learning (🟡 MEDIUM)
In production, the debate agents should learn from past debates. If the Bull argued "breakout pattern" 10 times and was wrong 8 times, it should adjust. Currently no feedback loop exists.

---

## ✅ Strengths
1. Clean, focused architecture — each agent has a single clear purpose
2. Strict word limits in identity core (150 words, 3 bullets) prevent token waste
3. Run in parallel → efficient
4. Safe defaults on failure → system doesn't crash
