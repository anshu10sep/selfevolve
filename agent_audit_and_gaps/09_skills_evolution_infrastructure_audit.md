# 🛠️ Skills Infrastructure & Evolution Pipeline — Audit & Gaps

---

## Part 1: Skills Infrastructure

### Dual SkillRegistry Problem (🔴 HIGH)

There are **TWO competing SkillRegistry implementations** that are incompatible:

#### Registry #1: `skills/registry.py`
```python
class SkillRegistry:
    _skills: Dict[str, Callable] = {}  # Global flat registry
    
    @classmethod
    def register(cls, func):
        name = f"{func.__module__}.{func.__name__}"
        cls._skills[name] = func
```
- Registers by fully qualified name
- No agent association
- Never called anywhere

#### Registry #2: `skills/validator.py`
```python
class SkillRegistry:
    _skills: Dict[str, Dict[str, Callable]] = {}  # Per-agent registry
    
    @classmethod
    def register(cls, agent_name, name, func):
        cls._skills[agent_name][name] = func
```
- Registers per agent
- Used by `@skill` decorator
- Some skills use it (e.g., `compliance_check.py` uses `@skill`)

#### But the `@skill` decorator is WRONG:
```python
@skill  # <-- Missing agent_name argument!
def verify_trade_compliance(trade_details, compliance_rules):
```
The decorator requires `@skill("agent_name")` but some files call `@skill` without arguments, which would crash.

### Skill Quality Audit

| Category | Count | Real Implementations | Stubs |
|----------|:-----:|:-------------------:|:-----:|
| **Jarvis skills** | 10 | ✅ 6 real | 4 stubs |
| **Analyst skills** | 12 | ❌ 0 | 12 stubs |
| **Debate skills** | 8 | ❌ 0 | 8 stubs |
| **Judge skills** | 3 | ❌ 0 | 3 stubs |
| **C-Suite skills** | 25+ | ❌ 0 | 25+ stubs |
| **Strategy skills** | 4 | ✅ 4 real | 0 stubs |
| **Crypto skills** | 6 | ❌ 0 | 6 stubs |
| **PR Reviewer** | 4 | ❓ Unknown | ❓ |
| **TOTAL** | ~72 | ~10 | ~62 |

**Only ~14% of skills have real implementations.**

### Skill Validator (`validate_all.py`)

The `validate_all.py` script exists to validate all skills but:
- It only checks structural requirements (docstrings, type hints, return types)
- It does NOT validate that skills produce correct outputs
- It does NOT check if skills are wired to agents

### Missing from Skills Infrastructure:
1. **No tool-calling bridge**: Skills → LangChain tools → LLM bind_tools
2. **No skill versioning**: No way to track which version of a skill an agent is using
3. **No skill testing framework**: No automated tests for individual skills
4. **No skill evolution**: Skills are static code — not evolving
5. **No skill discovery API**: Agents can't dynamically discover available tools
6. **No skill metrics**: No tracking of skill usage, success rates, latency

---

## Part 2: Evolution Pipeline

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    EVOLUTION PIPELINE                        │
│                                                             │
│  EvolutionRunner (evolution_runner.py)                       │
│  ├── Step 1: Trust Updates (trust_updater.py)               │
│  │   ├── Fetch predictions (prediction_tracker.py)          │
│  │   ├── Compute Brier scores (reflexion.py)                │
│  │   └── Decay/boost trust weights → DB                     │
│  ├── Step 2: Identify underperformers                       │
│  ├── Step 3: Generate post-mortems (meta_review_agent.py)   │
│  ├── Step 4: Propose prompt mutations                       │
│  ├── Step 5: Validate domain isolation (Pydantic)           │
│  ├── Step 6: Store candidate → Shadow Crew                  │
│  └── Step 7: Evaluate Shadow tests (statistical)            │
│                                                             │
│  SelfEvolutionEngine (self_evolution.py)                     │
│  ├── Check GitHub PRs for approvals                         │
│  ├── Auto-merge approved PRs                                │
│  ├── Git pull latest code                                   │
│  └── Graceful self-restart via systemd                      │
└─────────────────────────────────────────────────────────────┘
```

### Evolution Components Audit

| Component | File | Lines | Status |
|-----------|------|:-----:|--------|
| `BrierScoreEngine` | `reflexion.py` | 83 | ✅ Production-ready |
| `MarketContextReplay` | `reflexion.py` | 25 | ✅ Production-ready |
| `PromptEvolution` | `reflexion.py` | 92 | ✅ Production-ready (Welch's t-test) |
| `TrustDecayManager` | `reflexion.py` | 45 | ✅ Production-ready |
| `trust_updater` | `trust_updater.py` | 237 | ✅ Production-ready |
| `EvolutionRunner` | `evolution_runner.py` | 542 | ✅ Production-ready |
| `SelfEvolutionEngine` | `self_evolution.py` | 347 | ✅ Production-ready |
| `prediction_tracker` | `prediction_tracker.py` | ~140 | ✅ Production-ready |
| `BugScanner` | `bug_scanner.py` | 13K | ✅ Production-ready |
| `BugWorker` | `bug_worker.py` | 15.5K | ✅ Production-ready |
| `EngineerAgent` | `engineer_agent.py` | 9.7K | ✅ Production-ready |
| `HotReloader` | `hot_reloader.py` | 5.6K | ✅ Production-ready |
| `ProcessMonitor` | `process_monitor.py` | 13K | ✅ Production-ready |
| `SelfHealer` | `self_healer.py` | 9.8K | ✅ Production-ready |
| `AgentSpawner` | `agent_spawner.py` | 8.6K | ✅ Production-ready |
| `TPMTracker` | `tpm_tracker.py` | 9.1K | ✅ Production-ready |

### 🟢 Evolution Pipeline Strengths
The evolution infrastructure is the **strongest part of the system**:
- Real Brier score computation with scipy
- Real statistical significance testing (p < 0.05)
- Domain isolation via Pydantic validators
- Shadow Crew A/B testing pipeline
- Auto-merge → git pull → self-restart loop
- Bug scanning, code fixes, PR reviews, hot reloading

---

## Evolution Pipeline Gaps

### Gap EV-1: Only 5 Agents Evolve (🔴 CRITICAL)
`SCORABLE_ROLES` only includes: Fundamental, Technical, Sentiment, Macro, Judge.

**Missing from evolution**: Jarvis, Bull, Bear, Portfolio Manager, Strategy Researcher, Auditor, CSO, CTO, Developer, Journaling, Product, QA, Model Orchestrator.

**12+ agents NEVER evolve.**

### Gap EV-2: No Vector Store for Rule Retrieval (🟡 MEDIUM)
Architecture spec says rules should be stored in Qdrant and retrieved via RAG. The `memory/vector_store.py` exists (6.6K lines) but is NOT connected to the evolution pipeline.

### Gap EV-3: Skills Don't Evolve (🟡 MEDIUM)
Only Strategic_Nuance (system prompt suffix) evolves. The actual Python skill code is static. For true self-evolution, skill parameters should also be tunable:
- RSI period: 14 → 20 (if backtests show improvement)
- Stop loss percentage: 2% → 1.5% (if loss analysis supports it)

### Gap EV-4: No Cross-Agent Learning (🟡 MEDIUM)
Agents don't learn from EACH OTHER's successes/failures. If the Technical Analyst discovers that a certain pattern works, the Bull Agent should learn this too.

### Gap EV-5: Evolution Cycle Not Scheduled (🟢 LOW)
The `evolution_runner.run_full_cycle()` is defined but its scheduling depends on `main.py` calling it. Should be on a cron-like schedule independent of the main loop.

### Gap EV-6: No Evolution Dashboard Integration (🟢 LOW)
Evolution events are logged to DB and Telegram, but the dashboard doesn't show:
- Brier score trends over time
- Trust weight trajectory per agent
- Prompt version history
- Shadow test results

---

## Part 3: Inter-Agent Communication

### Event Bus Status

| Channel | Publishers | Subscribers | Status |
|---------|-----------|-------------|--------|
| `MARKET_EVENTS` | market_data_daemon | trading_dag | ✅ Working |
| `TRADE_EVENTS` | execution layer | None directly | 🟡 Partial |
| `AGENT_EVENTS` | None | None | 🔴 Unused |
| `EVOLUTION_EVENTS` | evolution_runner | None | 🔴 Publish-only |
| `ALERT_EVENTS` | alerting | Telegram bot | ✅ Working |
| `HEALTH_EVENTS` | health_publisher | dashboard | ✅ Working |
| `HITL_EVENTS` | hitl_gateway | Telegram bot | ✅ Working |

### Missing Communication Patterns

1. **Agent → Agent direct messaging**: No mechanism exists
2. **Analyst → Bull/Bear data sharing**: Done via DAG, not direct
3. **QA → All agents validation**: QA can't proactively validate
4. **Auditor → Judge compliance gates**: Auditor can't block Judge
5. **CTO → All agents health monitoring**: No health check protocol
6. **Journaling → Event Bus subscription**: Should auto-document trades

### Proposed Agent Communication Architecture

```python
# Add to BaseAgent
class BaseAgent(ABC):
    async def send_message(self, target_role: AgentRole, message: str, data: dict = None):
        """Send a message to another agent via Event Bus."""
        await self._event_bus.publish(
            EventChannels.AGENT_EVENTS,
            Event(
                event_type="AGENT_MESSAGE",
                data={
                    "from": self.role.value,
                    "to": target_role.value,
                    "message": message,
                    "data": data or {},
                },
                source=self.name,
            ),
        )
    
    async def _handle_incoming_message(self, event: dict):
        """Handle messages from other agents."""
        if event["data"]["to"] == self.role.value:
            await self._process_agent_message(event["data"])
```
