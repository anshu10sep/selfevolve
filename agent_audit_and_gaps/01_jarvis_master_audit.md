# 🤖 Jarvis (Master Agent / CEO) — Full Audit

## Agent Identity

| Attribute | Value |
|-----------|-------|
| **Class** | `Jarvis` (extends `BaseAgent`) |
| **File** | `src/agents/master_agent.py` (309 lines) |
| **Role** | `AgentRole.MASTER` |
| **Type** | `AgentType.EXECUTIVE` |
| **LLM Tier** | Premium |
| **Skills Directory** | `src/agents/skills/jarvis/` |

## Core Responsibilities (from Identity Core)

1. **Owner Interface** — Generate comprehensive briefings when owner asks "what's happening?"
2. **Agent Oversight** — Monitor all sub-agents, trust weights, Brier scores
3. **Strategic Direction** — Set high-level trading directives based on market regime
4. **Code Evolution** — Write new agent code, create skills, generate tests, open PRs via GitHub
5. **System Audit** — Scan codebase for gaps, missing tests, improvement opportunities
6. **Evolution Planning** — Plan multi-day evolution cycles, prioritize tasks
7. **Risk Escalation** — Escalate critical issues to human owner via HITL

## Skills Inventory

### ✅ CodeGenerator (`skills/jarvis/code_generation.py`)
- **Status**: REAL IMPLEMENTATION (249 lines)
- `generate_code(prompt)` — Calls OpenAI API to generate code (with retry logic)
- `generate_agent_file(role, name, identity_core)` — Creates new agent Python files from template
- `generate_test_file(module_path)` — Creates basic test files for agents
- **Tools Used**: OpenAI API (direct `requests` call, NOT LangChain)
- **Gap**: Uses raw OpenAI API instead of the system's `llm_factory.py` — inconsistent
- **Gap**: Generated agents are minimal stubs (single `execute_task(**kwargs)` method)

### ✅ SystemAuditor (`skills/jarvis/system_audit.py`)
- **Status**: REAL IMPLEMENTATION
- Scans codebase for files, lines, test coverage
- Generates audit reports with readiness scores
- **Gap**: Not verified in detail

### ✅ AgentPlanner (`skills/jarvis/agent_planning.py`)
- **Status**: REAL IMPLEMENTATION
- Plans evolution cycles, prioritizes tasks
- Generates roadmap markdown
- **Gap**: Not verified in detail

### ✅ GitHubOps (`skills/jarvis/github_ops.py`)
- **Status**: REAL IMPLEMENTATION
- Creates branches, commits, opens PRs via GitHub API
- `evolution_commit_and_pr()` — Full PR workflow
- **Gap**: Not verified in detail

### Additional Files in skills/jarvis/:
- `code_scanner.py` — Scans code for issues
- `service_manager.py` — Manages services
- `error_handler.py` — Error handling
- `update_onboarding_docs.py` — Documentation updates
- `log_analyzer.py` — Log analysis
- `goals.md` — Mission and goals

## Methods Analysis

| Method | Type | Description | Production Ready? |
|--------|------|-------------|:-:|
| `generate_owner_report()` | LLM | Comprehensive owner briefing | ✅ Yes |
| `process_owner_message()` | LLM | Direct owner interaction | ✅ Yes |
| `run_evolution_cycle()` | Hybrid | Audit → Plan → Strategy | ✅ Yes |
| `create_new_agent()` | Tool | Generate agent + test + skills dir | ✅ Yes |
| `commit_evolution()` | Tool | Git commit + PR via GitHub API | ✅ Yes |
| `evaluate_agent_performance()` | LLM | Review agents, recommend actions | 🟡 LLM-only |
| `get_available_skills()` | Tool | Discover skills from filesystem | ✅ Yes |

## Inter-Agent Communication

- **Inbound**: Called by `main.py` orchestration and Telegram bot
- **Outbound**: Calls `SystemAuditor`, `AgentPlanner`, `GitHubOps`, `CodeGenerator`
- **Event Bus**: Not directly subscribed; publishes evolution events indirectly via evolution engine
- **Gap**: Does not directly communicate with sub-agents (CTO, CSO, etc.) — only through manual orchestration

## Evolution / Learning Mechanism

| Mechanism | Status |
|-----------|--------|
| Trust weight tracking | 🟡 Has `trust_weight` in base but not in SCORABLE_ROLES |
| Brier score evaluation | 🔴 Not a SCORABLE_ROLE — not evaluated |
| Strategic Nuance updates | ✅ Has `update_strategic_nuance()` from BaseAgent |
| Self-evolution via code | ✅ Writes code, opens PRs, system auto-merges |

## Grounding Check

| Project Principle | Grounded? | Notes |
|-------------------|:-:|-------|
| No LLM arithmetic | ✅ | Delegates to deterministic Python |
| Immutable Identity Core | ✅ | Core prompt is a string constant |
| Structured output enforcement | 🟡 | Not always using Pydantic schemas |
| Cost tracking | ✅ | Via BaseAgent._track_cost() |
| Trust weight awareness | 🟡 | Has weight but not scored |

---

## 🔴 Gaps Identified

### Gap J-1: Not in SCORABLE_ROLES (Critical)
Jarvis is not included in the trust weight evaluation pipeline. As the CEO, its decision quality should also be tracked via Brier scores or an equivalent metric.

### Gap J-2: CodeGenerator Uses Raw OpenAI API (Medium)
`CodeGenerator` makes direct `requests.post()` calls to OpenAI instead of using the system's `LLMFactory`. This creates inconsistency and bypasses the model orchestrator's A/B testing.

### Gap J-3: Generated Agents Are Minimal Stubs (High)
When Jarvis creates new agents via `generate_agent_file()`, they get a single generic `execute_task(**kwargs)` method. This is why the C-Suite agents (Auditor, CSO, CTO, etc.) are all stubs.

### Gap J-4: No Direct Sub-Agent Communication (Medium)
Jarvis doesn't have a mechanism to directly query or instruct sub-agents. It relies on the orchestration DAGs. Adding an `ask_agent()` tool would allow dynamic delegation.

### Gap J-5: Skills Not Wired to LLM Tool-Calling (High)
Jarvis has 4 skill classes instantiated but they are called via direct Python method calls, not through LLM function-calling. The LLM should be able to autonomously discover and invoke these tools.

### Gap J-6: No Retry/Fallback for Owner Reports (Low)
If the LLM fails during `generate_owner_report()`, it returns a generic error. Should have a deterministic fallback that generates a basic report from raw data.

---

## ✅ Strengths

1. **Most complete agent in the system** — has real tools, real business logic
2. **Self-evolution loop is functional** — audit → plan → code → PR → merge → restart
3. **Well-structured identity core** — clear responsibilities, constraints, communication style
4. **Cost tracking built in** via BaseAgent
5. **GitHub integration is production-quality** — real API calls with error handling
