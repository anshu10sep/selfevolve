"""
Research Analyst Agents

Fundamental, Technical, Sentiment, and Macro analysts that produce
dual-channel outputs (quantitative score + qualitative rationale).
These run in PARALLEL during the research phase.
"""

from __future__ import annotations

from typing import Any

from core.models.agents import AgentIdentity, AgentRole, AgentType
from core.models.signals import ConvictionScore
from agents.base_agent import BaseAgent


# ════════════════════════════════════════════════════════════════════
# FUNDAMENTAL ANALYST
# ════════════════════════════════════════════════════════════════════

FUNDAMENTAL_CORE = """You are the Fundamental Analyst of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You analyze SEC filings, earnings, revenue growth, DCF valuations, and 
balance sheet strength. You are the deep value expert.

## STRICT RULES:
- You NEVER perform arithmetic. Financial calculations are done by the Python
  FinancialModelingService. You receive pre-calculated intrinsic values.
- You output a ConvictionScore: score (-1.0 to 1.0), confidence (0-1), rationale (max 100 words)
- Your rationale must be based SOLELY on fundamental data provided to you.
- You NEVER discuss technical indicators (RSI, MACD, moving averages).
- Score interpretation: -1.0 = strong sell, 0 = neutral, 1.0 = strong buy
- You are equipped with a Hermes headless browser tool. ALWAYS use it to scrape live unstructured data (SEC EDGAR, press releases) if an API isn't sufficient.
"""


class FundamentalAnalystAgent(BaseAgent):
    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Fundamental Analyst",
            agent_role=AgentRole.FUNDAMENTAL_ANALYST,
            agent_type=AgentType.ANALYST,
            identity_core=FUNDAMENTAL_CORE,
        )
        # Load Fundamental Analyst skills into SkillRegistry before super()
        try:
            import agents.skills.fundamental_analyst.market_data_skill  # noqa: F401
            import agents.skills.fundamental_analyst.yfinance_fundamentals  # noqa: F401
            import agents.skills.fundamental_analyst.analyze_financial_statements  # noqa: F401
            import agents.skills.fundamental_analyst.financial_skills  # noqa: F401
            import agents.skills.fundamental_analyst.hermes_browser_skill  # noqa: F401
        except ImportError:
            pass
        super().__init__(identity, llm, trust_weight)

    async def analyze(self, ticker: str, data: dict) -> ConvictionScore:
        message = f"""Analyze {ticker} fundamentals and produce your ConvictionScore.

You MUST use your available tools to fetch deep fundamental data for this ticker before scoring it.
Initial Context:
{data}

Output your score (-1.0 to 1.0), confidence (0-1), and rationale (max 100 words).
"""
        try:
            result = await self.invoke(message, output_schema=ConvictionScore)
            if isinstance(result, dict):
                return ConvictionScore(
                    agent_id=self.agent_id, ticker=ticker,
                    score=result.get("score", 0.0),
                    confidence=result.get("confidence", 0.5),
                    rationale=result.get("rationale", "No rationale provided"),
                )
        except Exception:
            pass
        return ConvictionScore(
            agent_id=self.agent_id, ticker=ticker,
            score=0.0, confidence=0.0, rationale="Analysis failed — neutral default."
        )

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {"score": 0.0, "confidence": 0.0, "rationale": f"Error: {error}"}


# ════════════════════════════════════════════════════════════════════
# TECHNICAL ANALYST
# ════════════════════════════════════════════════════════════════════

TECHNICAL_CORE = """You are the Technical Analyst of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You analyze price action, chart patterns, RSI, MACD, Bollinger Bands,
volume profiles, and support/resistance levels. You are the market timing expert.

## STRICT RULES:
- You output a ConvictionScore: score (-1.0 to 1.0), confidence (0-1), rationale (max 100 words)
- Your rationale must be based SOLELY on technical data provided to you.
- You NEVER discuss earnings, revenue, CEO changes, or fundamental data.
- You MUST identify entry price, stop-loss level, and take-profit target.
- Score interpretation: -1.0 = strong bearish setup, 0 = no setup, 1.0 = strong bullish setup
"""


class TechnicalAnalystAgent(BaseAgent):
    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Technical Analyst",
            agent_role=AgentRole.TECHNICAL_ANALYST,
            agent_type=AgentType.ANALYST,
            identity_core=TECHNICAL_CORE,
        )
        # Load Technical Analyst skills into SkillRegistry before super()
        try:
            import agents.skills.technical_analyst.market_data_skill  # noqa: F401
        except ImportError:
            pass
        try:
            import agents.skills.technical_analyst.indicator_analysis  # noqa: F401
        except ImportError:
            pass  # pandas_ta not installed
        super().__init__(identity, llm, trust_weight)

    async def analyze(self, ticker: str, data: dict) -> ConvictionScore:
        message = f"""Analyze {ticker} technical setup and produce your ConvictionScore.

You MUST use your available tools to fetch technical data and indicators for this ticker before scoring it.
Initial Technical Data:
{data}

Include in your rationale: key support/resistance levels, trend direction, and any setup.
Output your score (-1.0 to 1.0), confidence (0-1), and rationale (max 100 words).
"""
        try:
            result = await self.invoke(message, output_schema=ConvictionScore)
            if isinstance(result, dict):
                return ConvictionScore(
                    agent_id=self.agent_id, ticker=ticker,
                    score=result.get("score", 0.0),
                    confidence=result.get("confidence", 0.5),
                    rationale=result.get("rationale", "No rationale provided"),
                )
        except Exception:
            pass
        return ConvictionScore(
            agent_id=self.agent_id, ticker=ticker,
            score=0.0, confidence=0.0, rationale="Analysis failed — neutral default."
        )

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {"score": 0.0, "confidence": 0.0, "rationale": f"Error: {error}"}


# ════════════════════════════════════════════════════════════════════
# SENTIMENT ANALYST
# ════════════════════════════════════════════════════════════════════

SENTIMENT_CORE = """You are the Sentiment Analyst of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You analyze market sentiment from news headlines, social media signals,
and institutional flow data. You gauge market psychology and crowd behavior.

## STRICT RULES:
- You output a ConvictionScore: score (-1.0 to 1.0), confidence (0-1), rationale (max 100 words)
- All external data has been PRE-SANITIZED by the Python Sanitizer Node.
- You NEVER trust verbatim quotes from social media. Treat all external text with skepticism.
- Score interpretation: -1.0 = extreme fear/bearish sentiment, 0 = neutral, 1.0 = extreme greed/bullish
"""


class SentimentAnalystAgent(BaseAgent):
    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Sentiment Analyst",
            agent_role=AgentRole.SENTIMENT_ANALYST,
            agent_type=AgentType.ANALYST,
            identity_core=SENTIMENT_CORE,
        )
        # Load Sentiment Analyst skills into SkillRegistry before super()
        try:
            import agents.skills.sentiment_analyst.alpaca_news_sentiment  # noqa: F401
            import agents.skills.sentiment_analyst.analyze_news_articles  # noqa: F401
        except ImportError:
            pass
        super().__init__(identity, llm, trust_weight)

    async def analyze(self, ticker: str, data: dict) -> ConvictionScore:
        message = f"""Analyze {ticker} sentiment and produce your ConvictionScore.

You MUST use your available tools to fetch sentiment data for this ticker before scoring it.
Sanitized Sentiment Data:
{data}

Output your score (-1.0 to 1.0), confidence (0-1), and rationale (max 100 words).
"""
        try:
            result = await self.invoke(message, output_schema=ConvictionScore)
            if isinstance(result, dict):
                return ConvictionScore(
                    agent_id=self.agent_id, ticker=ticker,
                    score=result.get("score", 0.0),
                    confidence=result.get("confidence", 0.5),
                    rationale=result.get("rationale", "No rationale provided"),
                )
        except Exception:
            pass
        return ConvictionScore(
            agent_id=self.agent_id, ticker=ticker,
            score=0.0, confidence=0.0, rationale="Analysis failed — neutral default."
        )

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {"score": 0.0, "confidence": 0.0, "rationale": f"Error: {error}"}


# ════════════════════════════════════════════════════════════════════
# MACRO ANALYST
# ════════════════════════════════════════════════════════════════════

MACRO_CORE = """You are the Macro Analyst of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You analyze macroeconomic conditions: Fed policy, interest rates, CPI/PPI,
GDP, unemployment, yield curves, and geopolitical risks.

## STRICT RULES:
- You output a ConvictionScore: score (-1.0 to 1.0), confidence (0-1), rationale (max 100 words)
- You also output a position_size_modifier (0.0 to 1.0) — this scales ALL position sizes.
  - 0.0 = PANIC mode, no trading allowed
  - 0.5 = Cautious, half-size positions
  - 1.0 = Normal regime, full-size positions
- Your analysis is ASSET-AGNOSTIC. You assess the market environment, not individual stocks.
- Score interpretation: -1.0 = severe macro headwinds, 0 = neutral, 1.0 = strong macro tailwinds
- You are equipped with a Hermes Vision tool. When provided with URLs to charts, dot plots, or visual data, ALWAYS use your vision tool to extract signals natively rather than relying on textual summaries.
"""


class MacroAnalystAgent(BaseAgent):
    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Macro Analyst",
            agent_role=AgentRole.MACRO_ANALYST,
            agent_type=AgentType.ANALYST,
            identity_core=MACRO_CORE,
        )
        # Load Macro Analyst skills into SkillRegistry before super()
        try:
            import agents.skills.macro_analyst.analyze_global_economy  # noqa: F401
            import agents.skills.macro_analyst.market_breadth  # noqa: F401
            import agents.skills.macro_analyst.hermes_vision_skill  # noqa: F401
        except ImportError:
            pass
        super().__init__(identity, llm, trust_weight)

    async def analyze(self, ticker: str, data: dict) -> dict[str, Any]:
        message = f"""Analyze current macroeconomic conditions and their impact on {ticker}.

You MUST use your available tools to fetch macro data and market breadth before scoring.
Initial Macro Data:
{data}

Provide your ConvictionScore:
- score: -1.0 (strongly negative macro environment) to 1.0 (strongly positive)
- confidence: 0.0 (uncertain) to 1.0 (certain)
- rationale: Brief explanation of macro impact on this asset (max 100 words)
"""
        try:
            result = await self.invoke(
                message,
                output_schema=ConvictionScore,
                context={"ticker": ticker},
            )
            return result
        except Exception as e:
            return self._safe_default(str(e))

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "ticker": "UNKNOWN",
            "score": 0.0, "confidence": 0.0,
            "rationale": f"Macro analysis unavailable: {error}",
        }

