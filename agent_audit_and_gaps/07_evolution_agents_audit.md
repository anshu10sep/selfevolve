# 🧬 Meta-Review Agent & Strategy Researcher — Audit & Gaps

> These are the two "evolution engine" agents — the Meta-Review drives prompt evolution, the Strategy Researcher drives strategy evolution.

---

## Part 1: Meta-Review Agent

### Agent Identity

| Attribute | Value |
|-----------|-------|
| **Class** | `MetaReviewAgent` (extends `BaseAgent`) |
| **File** | `src/agents/meta_review_agent.py` (244 lines) |
| **Role** | `AgentRole.META_REVIEW` |
| **Type** | `AgentType.SPECIALIST` |

### Core Responsibilities
1. Post-mortem analysis of trades (evaluating DECISION QUALITY, not outcomes)
2. Proposing Strategic_Nuance updates for underperforming agents
3. Rule consolidation (max 3 rules per agent)
4. Domain isolation validation via Pydantic `AgentUpdate`

### Methods Analysis

| Method | Type | Description | Production Ready? |
|--------|------|-------------|:-:|
| `generate_post_mortem()` | LLM | Linguistic analysis of agent performance | ✅ Yes |
| `propose_prompt_update()` | LLM | Propose Strategic_Nuance changes | ✅ Yes |
| `consolidate_rules()` | LLM | Merge rules to stay within max-3 limit | ✅ Yes |
| `validate_proposed_nuance()` | **Deterministic** | Pydantic domain isolation check | ✅ **Excellent** |

### Skills Audit (`skills/meta_review/`)

| File | Function | Status |
|------|----------|--------|
| `review_agent_performance.py` | Review agent performance | 🔴 **STUB** |
| `evaluate_strategy_effectiveness.py` | Evaluate strategies | 🔴 **STUB** |
| `propose_improvements.py` | Propose improvements | 🔴 **STUB** |
| `goals.md` | Goals | ✅ Present |

### Evolution Support
The Meta-Review IS the evolution engine — it's called by `EvolutionRunner` to:
1. Generate post-mortems for underperforming agents
2. Propose prompt mutations
3. Validate domain isolation

### Gaps

| Gap | Severity | Description |
|-----|:--------:|-------------|
| MR-1 | 🟡 Medium | Skills not wired — duplicate logic |
| MR-2 | 🟡 Medium | No vector store integration for rule retrieval |
| MR-3 | 🟢 Low | Not in SCORABLE_ROLES — own performance not tracked |
| MR-4 | 🟡 Medium | `consolidate_rules()` doesn't verify new rules <= MAX_RULES_PER_AGENT |

#### Gap MR-2 Detail: Missing Vector Store Integration
The architecture spec says rules should be stored as vectors in Qdrant and retrieved via RAG. Currently, rules are just text strings. The `memory/vector_store.py` exists but is not connected to the Meta-Review Agent.

**Expected Flow** (from architecture spec):
1. New rule generated → stored as vector in Qdrant
2. Before agent invocation → retrieve 3 most relevant rules via cosine similarity
3. Rules injected into Strategic_Nuance

**Current Flow**:
1. New rule generated → stored as text in `prompt_versions` DB table
2. Active prompt text replaces Strategic_Nuance entirely
3. No semantic relevance filtering

### Strengths
1. **Core of the self-evolution thesis** — this is working correctly
2. **Domain isolation validation** — Pydantic catches cross-domain contamination
3. **Rule consolidation** — prevents prompt saturation (max 3 rules)
4. **Brier-driven, not outcome-driven** — evaluates decision quality

---

## Part 2: Strategy Researcher Agent

### Agent Identity

| Attribute | Value |
|-----------|-------|
| **Class** | `StrategyResearcherAgent` (extends `BaseAgent`) |
| **File** | `src/agents/strategy_researcher.py` (377 lines) |
| **Role** | `AgentRole.META_REVIEW` (⚠️ Wrong — shares role with Meta-Review) |
| **Type** | `AgentType.SPECIALIST` |

### Core Responsibilities
1. Daily performance review of all strategies
2. Identify underperformers and analyze WHY
3. Propose parameter experiments (ONE at a time)
4. Evaluate shadow-to-live promotion via statistical significance
5. Brainstorm new strategy ideas via LLM

### Methods Analysis

| Method | Type | Description | Production Ready? |
|--------|------|-------------|:-:|
| `run_daily_research()` | Hybrid | Performance review + LLM commentary | ✅ Yes |
| `run_weekly_analysis()` | Hybrid | Deep analysis + parameter experiments | ✅ Yes |
| `evaluate_shadow_strategy()` | **Deterministic** | Statistical significance testing | ✅ **Excellent** |
| `_analyze_strategy_correlations()` | **Deterministic** | Diversification check | ✅ Yes |
| `_generate_research_commentary()` | LLM | Research notes | 🟡 LLM-only |
| `_brainstorm_strategies()` | LLM | New strategy ideas | 🟡 LLM-only |

### Real Tool Integrations ✅
- Uses `StrategyPerformanceTracker` for real performance data
- Uses `strategy_ledger` for evolution event logging
- Uses `evaluate_parameter_fitness()` — deterministic fitness evaluation
- Uses `propose_parameter_evolution()` — parameter mutation proposals
- Uses `statistical_significance_test()` — Welch's t-test for promotion

### Gaps

| Gap | Severity | Description |
|-----|:--------:|-------------|
| SR-1 | 🟡 Medium | Wrong AgentRole — shares `META_REVIEW` with Meta-Review Agent |
| SR-2 | 🟡 Medium | `_brainstorm_strategies()` returns raw LLM text, not structured |
| SR-3 | 🟡 Medium | No Event Bus integration for publishing research findings |
| SR-4 | 🟢 Low | Not in SCORABLE_ROLES — own research quality not tracked |
| SR-5 | 🟡 Medium | No integration with backtester for automated hypothesis testing |

#### Gap SR-1: Wrong AgentRole
`StrategyResearcherAgent` uses `AgentRole.META_REVIEW` which is the same role as the Meta-Review Agent. This causes potential conflicts in:
- Trust weight tracking (both would share the same role key)
- Prediction tracking
- Evolution pipeline

Should have its own `AgentRole.STRATEGY_RESEARCHER`.

#### Gap SR-5: No Backtester Integration
The `research/strategy_backtest_harness.py` (18K lines!) has a full backtesting framework, but the Strategy Researcher doesn't call it. The LLM proposes strategies but can't validate them via backtest.

### Strengths
1. **Real statistical tools** — uses scipy for significance testing
2. **Scientific method** — one change at a time, minimum 30 trades
3. **Shadow testing pipeline** — proper A/B testing before promotion
4. **Strategy correlation analysis** — checks diversification
5. **Well-integrated** — uses strategy_learning skills and performance tracker

---

## Part 3: Model Orchestrator

### Agent Identity

| Attribute | Value |
|-----------|-------|
| **Class** | `ModelOrchestrator` (NOT a BaseAgent subclass) |
| **File** | `src/agents/model_orchestrator.py` (123 lines) |
| **Singleton** | `orchestrator` global instance |

### Architecture
- Routes LLM selection per agent role
- A/B tests different models (exploration vs exploitation)
- Tracks win rates, costs, latency per model per role

### Methods

| Method | Type | Description | Production Ready? |
|--------|------|-------------|:-:|
| `get_optimal_model_for_agent()` | Deterministic | Select best model | 🟡 Basic |
| `record_execution_result()` | Code | Track model performance | 🟡 In-memory only |

### Gaps

| Gap | Severity | Description |
|-----|:--------:|-------------|
| MO-1 | 🔴 High | In-memory only — state lost on restart |
| MO-2 | 🟡 Medium | Not a BaseAgent — no identity, no skills, no evolution |
| MO-3 | 🟡 Medium | Not integrated into BaseAgent.invoke() — models are hardcoded per agent |
| MO-4 | 🟡 Medium | No Event Bus integration |
| MO-5 | 🟢 Low | Simple random exploration — could use Thompson Sampling |

#### Gap MO-1: In-Memory Only
All metrics are stored in `_metrics_cache` dict. On restart, ALL A/B test data is lost. Must persist to PostgreSQL.

#### Gap MO-3: Not Integrated Into BaseAgent
The `ModelOrchestrator` exists but `BaseAgent.__init__()` takes a pre-constructed `llm` parameter. The orchestrator should be called inside BaseAgent to dynamically select the model.
