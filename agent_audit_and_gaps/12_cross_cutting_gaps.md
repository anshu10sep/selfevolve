# 🔗 Cross-Cutting Gaps — Systemic Issues Across All Agents

> These are issues that affect multiple agents simultaneously and require architectural fixes.

---

## Gap X-1: No Tool-Calling Loop in BaseAgent (🔴 P0 — CRITICAL)

### Problem
`BaseAgent.invoke()` sends messages to an LLM and returns the response. There is NO mechanism for the LLM to **call tools** during its reasoning. This means:
- Skills exist on disk but are invisible to agents
- The LLM can't fetch real data during analysis
- The LLM can't call deterministic calculators
- Every agent is just a "prompt in, text out" wrapper

### Impact
**All 17+ agents** are affected. Without tool-calling, agents cannot:
- Use their registered skills
- Access real-time data
- Call deterministic computation services
- Interact with the database, broker API, or external services

### Current Architecture
```python
# BaseAgent.invoke() — current
messages = [SystemMessage(prompt), HumanMessage(user_msg)]
response = await self.llm.ainvoke(messages)
return {"content": response.content}  # Just text
```

### Required Architecture
```python
# BaseAgent.invoke() — required
messages = [SystemMessage(prompt), HumanMessage(user_msg)]
llm_with_tools = self.llm.bind_tools(self._tools)  # Skills as tools
response = await llm_with_tools.ainvoke(messages)

# Tool-calling loop
while response.tool_calls:
    for tc in response.tool_calls:
        result = self._execute_tool(tc)
        messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    response = await llm_with_tools.ainvoke(messages)
```

### Remediation Effort: ~8 hours

---

## Gap X-2: Dual SkillRegistry (🟡 P1 — HIGH)

### Problem
Two competing `SkillRegistry` classes exist:

| File | Key Style | Usage |
|------|-----------|-------|
| `skills/registry.py` | `module.function_name` → function | Never used |
| `skills/validator.py` | `agent_name` → `{func_name: function}` | Used by `@skill` decorator |

### Impact
- Skills registered in one aren't visible in the other
- `@skill` decorator sometimes called incorrectly (missing agent_name)
- No single source of truth for available skills

### Remediation
1. Delete `skills/registry.py`
2. Use `skills/validator.py`'s `SkillRegistry` as the single authority
3. Fix all `@skill` decorator calls to include agent_name
4. Add `list_skills(agent_name)` method

---

## Gap X-3: 12 Agents Have No Evolution (🔴 P1 — CRITICAL)

### Problem
`SCORABLE_ROLES` only includes 5 roles:
```python
SCORABLE_ROLES = [
    "FUNDAMENTAL_ANALYST",
    "TECHNICAL_ANALYST", 
    "SENTIMENT_ANALYST",
    "MACRO_ANALYST",
    "JUDGE",
]
```

### Missing Agents (12+)
| Agent | Should Evolve? | What Would Be Tracked? |
|-------|:-:|------|
| Jarvis (Master) | ✅ Yes | Quality of strategic decisions, code evolution success rate |
| Bull Agent | ✅ Yes | Calibration of bull_score vs actual price movement |
| Bear Agent | ✅ Yes | Calibration of bear_score vs actual price movement |
| Portfolio Manager | ✅ Yes | Allocation quality, regime-matching accuracy |
| Strategy Researcher | ✅ Yes | Quality of strategy proposals, backtest hit rate |
| Auditor | ✅ Yes | False positive/negative rate on compliance checks |
| QA Agent | ✅ Yes | Bug detection accuracy, false alarm rate |
| Meta-Review | ✅ Yes | Quality of post-mortems, prompt evolution success rate |
| CTO | 🟡 Maybe | System health prediction accuracy |
| CSO | 🟡 Maybe | Threat detection accuracy |
| Developer | 🟡 Maybe | Fix success rate |
| Journaling | ❌ No | Documentation quality is subjective |
| Product | ❌ No | Feature impact is too delayed to measure |
| Model Orchestrator | ✅ Yes | Model selection accuracy |

### Remediation
1. Define "prediction" for each agent type (not all have ticker predictions)
2. Create role-appropriate Brier score equivalents
3. Add to `SCORABLE_ROLES` gradually
4. Start with Bull, Bear, Portfolio Manager (clearest predictions)

---

## Gap X-4: No Agent-to-Agent Direct Messaging (🟡 P2 — MEDIUM)

### Problem
Agents only communicate through orchestration DAGs. There is no mechanism for:
- Auditor to alert Judge about a compliance issue
- QA to flag an anomaly to Jarvis
- CTO to warn all agents about system degradation
- Strategy Researcher to share findings with Portfolio Manager

### Impact
Agents operate in silos. The "self-evolving company" metaphor breaks down because team members can't talk to each other.

### Proposed Solution
Use the Event Bus `AGENT_EVENTS` channel:
```python
class AgentMessage(BaseModel):
    from_role: str
    to_role: str  # or "ALL" for broadcast
    message_type: str  # "ALERT", "REQUEST", "RESPONSE", "INFO"
    content: str
    data: Optional[dict]
    priority: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
```

---

## Gap X-5: No Agent Health Protocol (🟡 P2 — MEDIUM)

### Problem
Each agent has `get_health()` but there's no standardized health check protocol. No agent proactively monitors other agents' health.

### Required State
- CTO Agent should run periodic health checks on all agents
- Health data should publish to `HEALTH_EVENTS` channel
- Dashboard should display real-time agent health grid
- Jarvis should receive alerts when agents are unhealthy

---

## Gap X-6: No Structured Error Taxonomy (🟢 P3 — LOW)

### Problem
All agents use generic error handling:
```python
return {"content": f"Agent encountered an error: {error}", "status": "error"}
```

No classification of error types (transient network, LLM rate limit, data unavailable, logic error).

### Required State
```python
class AgentError(BaseModel):
    error_type: str  # "NETWORK", "RATE_LIMIT", "DATA_MISSING", "LOGIC", "UNKNOWN"
    severity: str    # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    retryable: bool
    message: str
    agent_role: str
```

---

## Gap X-7: No Agent Lifecycle Management (🟡 P2 — MEDIUM)

### Problem
Agents are instantiated in `main.py` and live forever. There's no:
- Agent startup validation (check skills loaded, health OK)
- Graceful shutdown protocol
- Agent replacement (hot-swap a failed agent)
- Agent version tracking (which code version is this agent running?)

### Required State
```python
class AgentLifecycle:
    async def startup(self, agent: BaseAgent):
        """Validate skills, run health check, register with event bus."""
    
    async def shutdown(self, agent: BaseAgent):
        """Deregister, flush metrics, save state."""
    
    async def replace(self, old: BaseAgent, new: BaseAgent):
        """Hot-swap an agent without downtime."""
```

---

## Gap X-8: Missing Data Pipeline for Analysts (🟡 P1 — HIGH)

### Problem
Analysts receive data as function arguments from the orchestration DAG. They can't pull their own data. The `integrations/market_data.py` and `integrations/market_data_daemon.py` exist but aren't connected to analysts.

### Required State
- Market data daemon publishes to Event Bus
- Analysts subscribe to `MARKET_EVENTS`
- Or: analysts have data-fetching tools they can call

### Existing Infrastructure (Unused by Analysts)
| Component | File | Purpose | Connected? |
|-----------|------|---------|:-:|
| `market_data.py` | `integrations/` | Alpaca market data | ❌ |
| `market_data_daemon.py` | `integrations/` | Continuous data streaming | ❌ |
| `crypto_data.py` | `integrations/` | Crypto market data | ❌ |
| `alpaca_client.py` | `broker/` | Broker API client | ❌ to analysts |

---

## Summary Priority

| Priority | Gap | Impact |
|:--------:|-----|--------|
| **P0** | X-1: Tool-calling loop | Unlocks ALL agent skills |
| **P1** | X-3: Evolution for all agents | Self-evolution thesis |
| **P1** | X-8: Data pipeline for analysts | Real trading capability |
| **P1** | X-2: Dual SkillRegistry | Clean infrastructure |
| **P2** | X-4: Agent messaging | Team collaboration |
| **P2** | X-5: Health protocol | Operational reliability |
| **P2** | X-7: Lifecycle management | Production stability |
| **P3** | X-6: Error taxonomy | Debugging efficiency |
