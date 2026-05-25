# 🔴 Analyst Agents — Gaps & Remediation Plan

## Gap Summary

| Gap ID | Severity | Description | Effort |
|--------|:--------:|-------------|:------:|
| A-1 | 🔴 Critical | Skills are stubs — no real data fetching | Large |
| A-2 | 🔴 Critical | Skills not wired to agent's LLM tool-calling | Large |
| A-3 | 🟡 Medium | Macro Analyst lacks Pydantic output schema | Small |
| A-4 | 🟡 Medium | No self-data-pull capability | Medium |
| A-5 | 🟡 Medium | No cross-analyst communication | Medium |
| A-6 | 🟢 Low | No Event Bus integration | Small |
| A-7 | 🟡 Medium | No real-time data streaming | Medium |

---

## Gap A-1: Skills Are Stubs — No Real Data Fetching (🔴 CRITICAL)

### Current State
Every skill file in the analyst directories returns **hardcoded fake data**:

```python
# skills/fundamental_analyst/analyze_financial_statements.py
def analyze_financial_statements(company_symbol, statement_type, fiscal_period):
    if statement_type == "income_statement":
        return {"revenue_growth": 0.15, "net_income_margin": 0.20}  # HARDCODED
```

```python
# skills/technical_analyst/indicator_analysis.py
def indicator_analysis(price_data, volume_data, indicator_type):
    if indicator_type == "RSI":
        rsi_value = 65 if price_data[-1] > price_data[0] else 35  # FAKE RSI
```

### Required State (Production)
Each analyst needs **real tools** that fetch and compute real data:

#### Fundamental Analyst — Required Real Tools:
1. `fetch_financial_statements(ticker, period)` → Calls Financial Modeling Prep API or Alpaca fundamentals
2. `compute_dcf_valuation(ticker, growth_rate, discount_rate)` → Deterministic DCF model
3. `fetch_earnings_history(ticker)` → Real earnings data from API
4. `compute_pe_ratio(ticker)` → Real P/E from live price + earnings
5. `screen_value_stocks(criteria)` → Uses `src/research/screener.py`

#### Technical Analyst — Required Real Tools:
1. `compute_rsi(ticker, period=14)` → Uses `pandas_ta` with real OHLCV from Alpaca
2. `compute_macd(ticker)` → Uses `pandas_ta`
3. `compute_bollinger_bands(ticker)` → Uses `pandas_ta`
4. `identify_support_resistance(ticker)` → Pivot point calculation
5. `get_volume_profile(ticker)` → Volume analysis from Alpaca bars

#### Sentiment Analyst — Required Real Tools:
1. `fetch_news_headlines(ticker)` → Alpaca News API (already available via `alpaca_client.py`)
2. `analyze_news_sentiment(headlines)` → NLP sentiment (can use LLM or `textblob`)
3. `fetch_social_sentiment(ticker)` → Social media API or scraping
4. `get_institutional_flow(ticker)` → Unusual options activity

#### Macro Analyst — Required Real Tools:
1. `fetch_fred_data(series_ids)` → FRED API for economic indicators
2. `get_yield_curve()` → Treasury yield data
3. `get_vix_level()` → Fear/greed index from market data
4. `get_fed_calendar()` → FOMC meeting dates and expectations

### Remediation
- Implement each tool as a real function with API calls
- Add error handling and caching (rate limit protection)
- Wire through the `SkillRegistry` with `@skill` decorator
- Add unit tests for each tool

---

## Gap A-2: Skills Not Wired to Agent LLM Tool-Calling (🔴 CRITICAL)

### Current State
The `BaseAgent.invoke()` method builds `[SystemMessage, HumanMessage]` and calls `llm.ainvoke()`. There is NO mechanism for the LLM to **discover** available tools or **call** them during reasoning.

The skills exist on the filesystem but are **never loaded** at agent initialization and **never registered** as LangChain tools.

### Required State
Each analyst agent should:
1. At `__init__`, load its skills from the `SkillRegistry`
2. Convert each skill to a LangChain `@tool` definition
3. Use `bind_tools()` on the LLM
4. Implement a tool-calling loop in `invoke()` where the LLM can request tool execution

### Proposed Architecture
```python
class BaseAgent(ABC):
    def __init__(self, identity, llm, trust_weight=1.0):
        self.llm = llm
        self._tools = self._load_skills()
        if self._tools:
            self.llm = llm.bind_tools(self._tools)
    
    def _load_skills(self):
        """Load skills from registry for this agent's role."""
        from agents.skills.validator import SkillRegistry
        skills = SkillRegistry.get_skills(self.name)
        return [convert_to_langchain_tool(s) for s in skills.values()]
    
    async def invoke(self, user_message, context=None, output_schema=None):
        # ... existing message building ...
        # ADD: Tool-calling loop
        response = await self.llm.ainvoke(messages)
        while response.tool_calls:
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call)
                messages.append(ToolMessage(content=result, tool_call_id=tool_call["id"]))
            response = await self.llm.ainvoke(messages)
```

---

## Gap A-3: Macro Analyst Lacks Pydantic Output Schema (🟡 MEDIUM)

### Current State
Fundamental, Technical, and Sentiment analysts all use `output_schema=ConvictionScore` for structured output. The Macro Analyst uses free-form dict:

```python
# MacroAnalystAgent.analyze()
result = await self.invoke(message)  # No output_schema!
return result  # Unstructured
```

### Required State
Create a `MacroConvictionScore` Pydantic model:
```python
class MacroConvictionScore(BaseModel):
    score: float  # -1.0 to 1.0
    confidence: float  # 0 to 1
    rationale: str
    position_size_modifier: float  # 0.0 to 1.0 (unique to Macro)
```

---

## Gap A-4: No Self-Data-Pull Capability (🟡 MEDIUM)

### Current State
Analysts receive all data as arguments: `analyzer.analyze(ticker, data)`. They cannot independently request additional data or refresh stale data.

### Required State
Each analyst should have a **data-fetching tool** registered as an LLM tool so the LLM can ask for more data during analysis:
- "I need the last 30 days of RSI data" → triggers `compute_rsi(ticker, period=30)`
- "What were last quarter's earnings?" → triggers `fetch_earnings(ticker, 'Q4')`

---

## Gap A-5: No Cross-Analyst Communication (🟡 MEDIUM)

### Current State
Analysts never talk to each other. The architecture spec says they run in **parallel** and their outputs are aggregated by the orchestration DAG.

### Proposed Enhancement
Add an optional **second-pass consensus** where analysts can see each other's ConvictionScores and adjust their confidence:
- If all analysts agree (all scores same sign), boost confidence
- If analysts disagree significantly, flag for additional debate

---

## Gap A-6: No Event Bus Integration (🟢 LOW)

### Current State
Analysts don't subscribe to or publish on the Event Bus. Market data comes via function arguments.

### Proposed Enhancement
- Subscribe to `MARKET_EVENTS` channel for real-time signals
- Publish `ANALYST_SCORE_COMPUTED` events after each analysis
- This enables real-time dashboard updates and logging

---

## Gap A-7: No Real-Time Data Streaming (🟡 MEDIUM)

### Current State
All data is point-in-time snapshots passed as arguments. No streaming capability.

### Required State
Integration with Alpaca's WebSocket data stream for real-time OHLCV and quote data. The `market_data_daemon.py` in `integrations/` suggests this was planned but not wired to analysts.
