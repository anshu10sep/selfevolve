# 🔬 Analyst Agents — Full Audit

> Covers: Fundamental Analyst, Technical Analyst, Sentiment Analyst, Macro Analyst

---

## Agent Summary Table

| Attribute | Fundamental | Technical | Sentiment | Macro |
|-----------|:-:|:-:|:-:|:-:|
| **Class** | `FundamentalAnalystAgent` | `TechnicalAnalystAgent` | `SentimentAnalystAgent` | `MacroAnalystAgent` |
| **File** | `analyst_agents.py` | `analyst_agents.py` | `analyst_agents.py` | `analyst_agents.py` |
| **Role** | `FUNDAMENTAL_ANALYST` | `TECHNICAL_ANALYST` | `SENTIMENT_ANALYST` | `MACRO_ANALYST` |
| **Type** | `ANALYST` | `ANALYST` | `ANALYST` | `ANALYST` |
| **Output Schema** | `ConvictionScore` | `ConvictionScore` | `ConvictionScore` | Free-form dict |
| **In SCORABLE_ROLES** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Has Pydantic Output** | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |

---

## Shared Architecture

All four analysts follow the same pattern:
1. Receive data as method arguments (NOT self-fetched)
2. Build a message string with data embedded
3. Call `self.invoke(message, output_schema=ConvictionScore)`
4. Return a `ConvictionScore` with score, confidence, rationale
5. On failure, return neutral defaults (score=0.0, confidence=0.0)

### ConvictionScore Output Schema
```python
class ConvictionScore(BaseModel):
    agent_id: str
    ticker: str
    score: float      # -1.0 to 1.0
    confidence: float  # 0 to 1
    rationale: str     # max 100 words
```

---

## Skills Audit — Per Agent

### Fundamental Analyst Skills (`skills/fundamental_analyst/`)

| File | Function | Status |
|------|----------|--------|
| `analyze_financial_statements.py` | `analyze_financial_statements(symbol, type, period)` | 🔴 **STUB** — Returns hardcoded ratios |
| `evaluate_company_news.py` | Evaluate company news | 🔴 **STUB** |
| `assess_economic_indicators.py` | Assess economic indicators | 🔴 **STUB** |
| `skills.py` | (aggregator) | Exists |
| `financial_skills.py` | (aggregator) | Exists |
| `goals.md` | Agent goals | ✅ Present |

**Critical Gap**: `analyze_financial_statements()` returns hardcoded `{"revenue_growth": 0.15, "net_income_margin": 0.20}`. Not connected to any real financial data source.

### Technical Analyst Skills (`skills/technical_analyst/`)

| File | Function | Status |
|------|----------|--------|
| `indicator_analysis.py` | `indicator_analysis(price_data, volume_data, type)` | 🔴 **STUB** — RSI simulated as `65 if up else 35` |
| `predict_price_movements.py` | Predict price movements | 🔴 **STUB** |
| `chart_pattern_recognition.py` | Recognize chart patterns | 🔴 **STUB** |
| `indicator_skills.py` | (aggregator) | Exists |
| `skills.py` | (aggregator) | Exists |
| `goals.md` | Agent goals | ✅ Present |

**Critical Gap**: RSI calculation is `65 if price_data[-1] > price_data[0] else 35`. Real RSI requires 14-period average gain/loss computation using `pandas_ta` or similar.

### Sentiment Analyst Skills (`skills/sentiment_analyst/`)

| File | Function | Status |
|------|----------|--------|
| `analyze_news_articles.py` | Analyze news articles | 🔴 **STUB** |
| `monitor_social_media.py` | Monitor social media | 🔴 **STUB** |
| `gauge_market_mood.py` | Gauge market mood | 🔴 **STUB** |
| `goals.md` | Agent goals | ✅ Present |

**Critical Gap**: No real news API integration. No social media scraping. No NLP pipeline.

### Macro Analyst Skills (`skills/macro_analyst/`)

| File | Function | Status |
|------|----------|--------|
| `analyze_global_economy.py` | Analyze global economy | 🔴 **STUB** |
| `forecast_interest_rates.py` | Forecast interest rates | 🔴 **STUB** |
| `assess_geopolitical_risks.py` | Assess geopolitical risks | 🔴 **STUB** |
| `goals.md` | Agent goals | ✅ Present |

**Critical Gap**: No FRED API, no economic data pipeline, no yield curve data.

---

## Inter-Agent Communication

| Communication Path | Method | Status |
|-------------------|--------|--------|
| Analysts → Debate (Bull/Bear) | Via `trading_dag.py` orchestration | ✅ Working |
| Analysts ← Market Data | Data passed as function arguments | 🟡 Passive (no pull) |
| Analysts → Meta-Review | Predictions tracked in DB | ✅ Via prediction_tracker |
| Analysts ↔ Other Analysts | None | 🔴 **Missing** |
| Analysts → Event Bus | Not subscribed | 🔴 **Missing** |

## Evolution / Learning Mechanisms

| Mechanism | Status | Notes |
|-----------|--------|-------|
| Brier Score Tracking | ✅ Active | All 4 in `SCORABLE_ROLES` |
| Trust Weight Updates | ✅ Active | Decay/boost based on Brier |
| Post-Mortem Generation | ✅ Active | Via Meta-Review Agent |
| Strategic Nuance Evolution | ✅ Active | Prompt mutation pipeline |
| Shadow Crew A/B Testing | ✅ Active | Statistical promotion |
| Domain Isolation | ✅ Active | Pydantic validates no cross-domain terms |

**These 4 agents have the BEST evolution support in the system.** The gap is in their tools, not their learning.

---

## Grounding Check

| Project Principle | FA | TA | SA | MA |
|-------------------|:-:|:-:|:-:|:-:|
| No LLM arithmetic | ✅ | ✅ | ✅ | ✅ |
| Immutable Identity Core | ✅ | ✅ | ✅ | ✅ |
| Structured output (Pydantic) | ✅ | ✅ | ✅ | ❌ Free-form |
| Domain isolation enforced | ✅ | ✅ | ✅ | ✅ |
| Cost tracking | ✅ | ✅ | ✅ | ✅ |
| Trust weight aware | ✅ | ✅ | ✅ | ✅ |
