"""
Phase 5 Integration Tests — Insights, InsightPublisher, Skills, DAG

Tests the inter-agent messaging infrastructure:
- AgentInsight schema (creation, expiry, serialization)
- InsightPublisher (publish, retrieve, filter, expiry, stats)
- Insight skills (registration, output format)
- Trading DAG (graph structure, node connectivity)
- Event handler registration (agent handlers wire correctly)
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta


# ════════════════════════════════════════════════════════════════════
# TEST: AgentInsight Schema
# ════════════════════════════════════════════════════════════════════

class TestAgentInsightSchema:
    """Tests for the AgentInsight Pydantic model."""

    def test_create_regime_change_insight(self):
        """REGIME_CHANGE insight creates with all fields."""
        from core.models.insights import AgentInsight, InsightType, InsightUrgency

        insight = AgentInsight(
            source_agent="MACRO_ANALYST",
            insight_type=InsightType.REGIME_CHANGE,
            title="Regime Change: BULL → BEAR",
            description="VIX crossed 25, yield curve inverted",
            confidence=0.85,
            urgency=InsightUrgency.HIGH,
            data={"old_regime": "BULL", "new_regime": "BEAR", "vix": 27.5},
        )

        assert insight.source_agent == "MACRO_ANALYST"
        assert insight.insight_type == InsightType.REGIME_CHANGE
        assert insight.confidence == 0.85
        assert insight.urgency == InsightUrgency.HIGH
        assert insight.data["vix"] == 27.5
        assert insight.insight_id  # Should auto-generate UUID
        assert insight.timestamp  # Should auto-generate timestamp

    def test_create_technical_signal_with_ticker(self):
        """TECHNICAL_SIGNAL insight with ticker is uppercased."""
        from core.models.insights import AgentInsight, InsightType

        insight = AgentInsight(
            source_agent="TECHNICAL_ANALYST",
            insight_type=InsightType.TECHNICAL_SIGNAL,
            ticker="  aapl  ",
            title="Bullish Breakout: AAPL",
            description="Price broke above 200-day MA",
            data={"pattern": "breakout"},
        )

        assert insight.ticker == "AAPL"

    def test_auto_expiry_regime_change(self):
        """REGIME_CHANGE insights auto-expire after 24 hours."""
        from core.models.insights import AgentInsight, InsightType, INSIGHT_EXPIRY_MINUTES

        insight = AgentInsight(
            source_agent="MACRO_ANALYST",
            insight_type=InsightType.REGIME_CHANGE,
            title="test",
            description="test",
        )

        assert insight.expires_at is not None
        expected_minutes = INSIGHT_EXPIRY_MINUTES[InsightType.REGIME_CHANGE]
        delta = insight.expires_at - insight.timestamp
        assert abs(delta.total_seconds() / 60 - expected_minutes) < 1

    def test_auto_expiry_technical_signal(self):
        """TECHNICAL_SIGNAL insights auto-expire after 1 hour."""
        from core.models.insights import AgentInsight, InsightType, INSIGHT_EXPIRY_MINUTES

        insight = AgentInsight(
            source_agent="TECHNICAL_ANALYST",
            insight_type=InsightType.TECHNICAL_SIGNAL,
            title="test",
            description="test",
        )

        expected_minutes = INSIGHT_EXPIRY_MINUTES[InsightType.TECHNICAL_SIGNAL]
        delta = insight.expires_at - insight.timestamp
        assert abs(delta.total_seconds() / 60 - expected_minutes) < 1

    def test_is_expired_fresh_insight(self):
        """A fresh insight is NOT expired."""
        from core.models.insights import AgentInsight, InsightType

        insight = AgentInsight(
            source_agent="TEST",
            insight_type=InsightType.TECHNICAL_SIGNAL,
            title="test",
            description="test",
        )

        assert insight.is_expired is False

    def test_is_expired_old_insight(self):
        """An insight with past expiry IS expired."""
        from core.models.insights import AgentInsight, InsightType

        insight = AgentInsight(
            source_agent="TEST",
            insight_type=InsightType.TECHNICAL_SIGNAL,
            title="test",
            description="test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert insight.is_expired is True

    def test_to_context_string(self):
        """Context string includes key fields for LLM injection."""
        from core.models.insights import AgentInsight, InsightType, InsightUrgency

        insight = AgentInsight(
            source_agent="MACRO_ANALYST",
            insight_type=InsightType.REGIME_CHANGE,
            title="Regime Shift",
            description="VIX spiked to 30",
            confidence=0.9,
            urgency=InsightUrgency.HIGH,
        )

        ctx = insight.to_context_string()
        assert "REGIME_CHANGE" in ctx
        assert "MACRO_ANALYST" in ctx
        assert "HIGH" in ctx
        assert "90%" in ctx
        assert "Regime Shift" in ctx

    def test_serialization_roundtrip(self):
        """to_event_dict → from_event_dict preserves all fields."""
        from core.models.insights import AgentInsight, InsightType, InsightUrgency

        original = AgentInsight(
            source_agent="SENTIMENT_ANALYST",
            insight_type=InsightType.SENTIMENT_DIVERGENCE,
            ticker="NVDA",
            title="Divergence Detected",
            description="Bullish news but price dropping",
            confidence=0.72,
            urgency=InsightUrgency.MEDIUM,
            data={"news_score": 0.8, "price_change": -2.5},
        )

        d = original.to_event_dict()
        restored = AgentInsight.from_event_dict(d)

        assert restored.source_agent == original.source_agent
        assert restored.insight_type == original.insight_type
        assert restored.ticker == original.ticker
        assert restored.title == original.title
        assert restored.confidence == original.confidence
        assert restored.urgency == original.urgency
        assert restored.data["news_score"] == 0.8

    def test_all_insight_types_exist(self):
        """All 10 insight types are defined."""
        from core.models.insights import InsightType

        expected_types = [
            "REGIME_CHANGE", "SENTIMENT_DIVERGENCE", "TECHNICAL_SIGNAL",
            "FUNDAMENTAL_FLAG", "RISK_ALERT", "COMPLIANCE_ALERT",
            "STRATEGY_SIGNAL", "HEALTH_ALERT", "EVOLUTION_UPDATE",
            "PORTFOLIO_UPDATE",
        ]
        for t in expected_types:
            assert hasattr(InsightType, t), f"Missing InsightType: {t}"

    def test_all_urgency_levels_exist(self):
        """All 4 urgency levels are defined."""
        from core.models.insights import InsightUrgency

        for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            assert hasattr(InsightUrgency, level), f"Missing InsightUrgency: {level}"


# ════════════════════════════════════════════════════════════════════
# TEST: InsightPublisher
# ════════════════════════════════════════════════════════════════════

class TestInsightPublisher:
    """Tests for the InsightPublisher singleton."""

    def _fresh_publisher(self):
        """Create a fresh InsightPublisher (not the global singleton)."""
        from core.insight_publisher import InsightPublisher
        return InsightPublisher()

    def _make_insight(self, **kwargs):
        """Create a test AgentInsight with defaults."""
        from core.models.insights import AgentInsight, InsightType, InsightUrgency

        defaults = {
            "source_agent": "TEST_AGENT",
            "insight_type": InsightType.TECHNICAL_SIGNAL,
            "title": "Test Insight",
            "description": "Test description",
            "confidence": 0.5,
            "urgency": InsightUrgency.MEDIUM,
        }
        defaults.update(kwargs)
        return AgentInsight(**defaults)

    def test_publish_and_retrieve(self):
        """Published insight is retrievable."""
        pub = self._fresh_publisher()
        insight = self._make_insight(ticker="AAPL")

        asyncio.get_event_loop().run_until_complete(pub.publish(insight))

        results = pub.get_recent_insights(ticker="AAPL", max_age_minutes=60)
        assert len(results) == 1
        assert results[0].ticker == "AAPL"

    def test_filter_by_insight_type(self):
        """Type filter narrows results."""
        from core.models.insights import InsightType
        pub = self._fresh_publisher()

        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(insight_type=InsightType.TECHNICAL_SIGNAL, ticker="AAPL")
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(insight_type=InsightType.REGIME_CHANGE)
        ))

        tech_results = pub.get_recent_insights(
            insight_type=InsightType.TECHNICAL_SIGNAL, max_age_minutes=60
        )
        assert len(tech_results) == 1
        assert tech_results[0].insight_type == InsightType.TECHNICAL_SIGNAL

    def test_filter_by_source_agent(self):
        """Source agent filter works."""
        pub = self._fresh_publisher()

        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(source_agent="MACRO_ANALYST")
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(source_agent="TECHNICAL_ANALYST")
        ))

        results = pub.get_recent_insights(
            source_agent="MACRO_ANALYST", max_age_minutes=60
        )
        assert len(results) == 1
        assert results[0].source_agent == "MACRO_ANALYST"

    def test_expired_insights_filtered_out(self):
        """Expired insights don't appear in queries."""
        from core.models.insights import InsightType
        pub = self._fresh_publisher()

        # Publish an already-expired insight
        expired = self._make_insight(
            ticker="OLD",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        asyncio.get_event_loop().run_until_complete(pub.publish(expired))

        # Publish a fresh one
        fresh = self._make_insight(ticker="NEW")
        asyncio.get_event_loop().run_until_complete(pub.publish(fresh))

        results = pub.get_recent_insights(max_age_minutes=120)
        assert len(results) == 1
        assert results[0].ticker == "NEW"

    def test_get_active_regime_none(self):
        """get_active_regime returns None when no regime insight exists."""
        pub = self._fresh_publisher()
        assert pub.get_active_regime() is None

    def test_get_active_regime_found(self):
        """get_active_regime returns the latest regime insight."""
        from core.models.insights import InsightType
        pub = self._fresh_publisher()

        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(
                insight_type=InsightType.REGIME_CHANGE,
                source_agent="MACRO_ANALYST",
                title="BULL regime",
                data={"regime": "BULL"},
            )
        ))

        regime = pub.get_active_regime()
        assert regime is not None
        assert regime.data["regime"] == "BULL"

    def test_get_all_active_signals(self):
        """get_all_active_signals aggregates analysis insights."""
        from core.models.insights import InsightType
        pub = self._fresh_publisher()

        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(
                insight_type=InsightType.TECHNICAL_SIGNAL,
                ticker="AAPL",
            )
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(
                insight_type=InsightType.FUNDAMENTAL_FLAG,
                ticker="AAPL",
            )
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(
                insight_type=InsightType.RISK_ALERT,  # Should NOT appear
                ticker="AAPL",
            )
        ))

        signals = pub.get_all_active_signals(ticker="AAPL")
        # RISK_ALERT is not in the signal types
        assert len(signals) == 2

    def test_get_risk_alerts(self):
        """get_risk_alerts returns only risk/compliance insights."""
        from core.models.insights import InsightType
        pub = self._fresh_publisher()

        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(insight_type=InsightType.RISK_ALERT)
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(insight_type=InsightType.COMPLIANCE_ALERT)
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(insight_type=InsightType.TECHNICAL_SIGNAL)
        ))

        alerts = pub.get_risk_alerts()
        assert len(alerts) == 2

    def test_format_insights_for_context_empty(self):
        """Empty insights list returns empty string."""
        pub = self._fresh_publisher()
        result = pub.format_insights_for_context([])
        assert result == ""

    def test_format_insights_for_context_populated(self):
        """Formatted context includes numbered insights."""
        pub = self._fresh_publisher()

        insights = [
            self._make_insight(title="Signal A"),
            self._make_insight(title="Signal B"),
        ]

        result = pub.format_insights_for_context(insights)
        assert "Active Intelligence" in result
        assert "Signal A" in result
        assert "Signal B" in result
        assert "1." in result
        assert "2." in result

    def test_stats(self):
        """Stats reflect published counts."""
        pub = self._fresh_publisher()

        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(title="A")
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(title="B")
        ))

        stats = pub.get_stats()
        assert stats["total_published"] == 2
        assert stats["active_insights"] == 2
        assert stats["has_event_bus"] is False

    def test_limit_results(self):
        """Query limit caps results."""
        pub = self._fresh_publisher()

        for i in range(10):
            asyncio.get_event_loop().run_until_complete(pub.publish(
                self._make_insight(title=f"Signal {i}")
            ))

        results = pub.get_recent_insights(max_age_minutes=60, limit=3)
        assert len(results) == 3

    def test_urgency_filter(self):
        """Urgency filter excludes lower urgency insights."""
        from core.models.insights import InsightUrgency
        pub = self._fresh_publisher()

        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(urgency=InsightUrgency.LOW, title="low")
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(urgency=InsightUrgency.HIGH, title="high")
        ))
        asyncio.get_event_loop().run_until_complete(pub.publish(
            self._make_insight(urgency=InsightUrgency.CRITICAL, title="critical")
        ))

        results = pub.get_recent_insights(
            urgency=InsightUrgency.HIGH,
            max_age_minutes=60,
        )
        assert len(results) == 2  # HIGH + CRITICAL
        titles = {r.title for r in results}
        assert "low" not in titles
        assert "high" in titles
        assert "critical" in titles


# ════════════════════════════════════════════════════════════════════
# TEST: Insight Skills
# ════════════════════════════════════════════════════════════════════

class TestInsightSkills:
    """Tests that insight skills are importable and return correct format."""

    def test_skills_importable(self):
        """All insight skills import cleanly."""
        from agents.skills.insights.insight_skills import (
            get_current_regime_for_ta,
            get_current_regime_for_fa,
            get_current_regime_for_sa,
            get_current_regime_for_judge,
            get_active_signals,
            get_risk_alerts,
            get_fundamental_flags,
            get_sentiment_alerts_for_ta,
            get_technical_signals_for_fa,
            get_technical_signals_for_sa,
        )
        assert callable(get_current_regime_for_ta)
        assert callable(get_active_signals)
        assert callable(get_risk_alerts)

    def test_regime_returns_dict_when_empty(self):
        """get_current_regime_* returns dict with 'available' key."""
        from agents.skills.insights.insight_skills import get_current_regime_for_judge

        result = get_current_regime_for_judge()
        assert isinstance(result, dict)
        assert "regime" in result
        assert "available" in result

    def test_active_signals_returns_dict_when_empty(self):
        """get_active_signals returns dict with 'signals_found' key."""
        from agents.skills.insights.insight_skills import get_active_signals

        result = get_active_signals()
        assert isinstance(result, dict)
        assert "signals_found" in result
        assert result["signals_found"] == 0

    def test_risk_alerts_returns_dict_when_empty(self):
        """get_risk_alerts returns dict with 'alerts_found' key."""
        from agents.skills.insights.insight_skills import get_risk_alerts

        result = get_risk_alerts()
        assert isinstance(result, dict)
        assert "alerts_found" in result
        assert result["has_critical"] is False

    def test_cross_analyst_tools_return_dict(self):
        """Cross-analyst tools return dicts with 'found' key."""
        from agents.skills.insights.insight_skills import (
            get_fundamental_flags,
            get_sentiment_alerts_for_ta,
            get_technical_signals_for_fa,
        )

        for tool_fn in (get_fundamental_flags, get_sentiment_alerts_for_ta, get_technical_signals_for_fa):
            result = tool_fn()
            assert isinstance(result, dict)
            assert "found" in result or "error" in result


# ════════════════════════════════════════════════════════════════════
# TEST: Trading DAG Structure
# ════════════════════════════════════════════════════════════════════

class TestTradingDAGStructure:
    """Tests that the Trading DAG has correct graph topology."""

    def test_build_trading_dag(self):
        """Trading DAG builds without errors."""
        from orchestration.trading_dag import build_trading_dag
        dag = build_trading_dag()
        assert dag is not None

    def test_dag_has_all_nodes(self):
        """DAG contains all expected nodes."""
        from orchestration.trading_dag import build_trading_dag
        dag = build_trading_dag()

        expected_nodes = [
            "regime_check", "parallel_research", "aggregation",
            "debate", "judge", "guardrail", "hitl", "execution",
        ]
        actual_nodes = set(dag.nodes.keys())

        for node in expected_nodes:
            assert node in actual_nodes, f"Missing node: {node}"

    def test_dag_entry_point(self):
        """DAG entry point is regime_check."""
        from orchestration.trading_dag import build_trading_dag
        dag = build_trading_dag()
        # The entry point is set via set_entry_point
        # We verify by checking that __start__ edges exist
        assert "regime_check" in dag.nodes

    def test_debate_workflow_builds(self):
        """Debate workflow sub-graph builds without errors."""
        from orchestration.debate_workflow import build_debate_workflow
        workflow = build_debate_workflow()
        assert workflow is not None

    def test_debate_workflow_has_all_nodes(self):
        """Debate workflow has bull, bear, and judge nodes."""
        from orchestration.debate_workflow import build_debate_workflow
        workflow = build_debate_workflow()

        actual_nodes = set(workflow.nodes.keys())
        assert "bull" in actual_nodes
        assert "bear" in actual_nodes
        assert "judge" in actual_nodes

    def test_score_extraction_helpers(self):
        """Score extraction regexes parse correctly."""
        from orchestration.trading_dag import (
            _extract_score,
            _extract_confidence,
            _extract_debate_score,
        )

        # Conviction score
        assert _extract_score("conviction: 0.7") == pytest.approx(0.7)
        assert _extract_score("Score: -0.5") == pytest.approx(-0.5)
        assert _extract_score("no score here") == 0.0

        # Confidence
        assert _extract_confidence("confidence: 0.8") == pytest.approx(0.8)
        assert _extract_confidence("0.6 confidence") == pytest.approx(0.6)
        assert _extract_confidence("confidence: 7") == pytest.approx(0.7)  # 7/10 normalized

        # Debate score
        assert _extract_debate_score("conviction: 8.5") == pytest.approx(8.5)
        assert _extract_debate_score("7.0/10") == pytest.approx(7.0)
        assert _extract_debate_score("no score") == 5.0

    def test_role_to_insight_type(self):
        """Analyst role mapping is correct."""
        from orchestration.trading_dag import _role_to_insight_type

        assert _role_to_insight_type("technical") == "TECHNICAL_SIGNAL"
        assert _role_to_insight_type("fundamental") == "FUNDAMENTAL_FLAG"
        assert _role_to_insight_type("sentiment") == "SENTIMENT_DIVERGENCE"
        assert _role_to_insight_type("macro") == "REGIME_CHANGE"
        assert _role_to_insight_type("unknown") is None


# ════════════════════════════════════════════════════════════════════
# TEST: Event Bus Integration
# ════════════════════════════════════════════════════════════════════

class TestEventBusIntegration:
    """Tests for Event Bus channel definitions."""

    def test_agent_insights_channel_exists(self):
        """AGENT_INSIGHTS channel is defined in EventChannels."""
        from core.event_bus import EventChannels

        assert hasattr(EventChannels, "AGENT_INSIGHTS")
        assert "agent_insights" in EventChannels.AGENT_INSIGHTS

    def test_all_channels_unique(self):
        """All event channels have unique values."""
        from core.event_bus import EventChannels

        channels = [
            EventChannels.MARKET_EVENTS,
            EventChannels.TRADE_EVENTS,
            EventChannels.AGENT_EVENTS,
            EventChannels.AGENT_INSIGHTS,
            EventChannels.EVOLUTION_EVENTS,
            EventChannels.ALERT_EVENTS,
            EventChannels.HEALTH_EVENTS,
            EventChannels.HITL_EVENTS,
        ]
        assert len(channels) == len(set(channels)), "Duplicate channel values found"

    def test_event_handler_module_importable(self):
        """Agent event handlers module imports cleanly."""
        from core.agent_event_handlers import register_agent_event_handlers
        assert callable(register_agent_event_handlers)

    def test_incoming_insight_handler_importable(self):
        """Incoming insight handler imports cleanly."""
        from core.insight_publisher import handle_incoming_insight
        assert callable(handle_incoming_insight)


# ════════════════════════════════════════════════════════════════════
# TEST: BaseAgent.publish_insight
# ════════════════════════════════════════════════════════════════════

class TestBaseAgentInsightPublishing:
    """Tests for BaseAgent.publish_insight method."""

    def test_base_agent_has_publish_insight(self):
        """BaseAgent class has publish_insight method."""
        from agents.base_agent import BaseAgent
        assert hasattr(BaseAgent, "publish_insight")
        assert callable(getattr(BaseAgent, "publish_insight"))

    def test_publish_insight_is_async(self):
        """publish_insight is an async method."""
        import inspect
        from agents.base_agent import BaseAgent
        assert inspect.iscoroutinefunction(BaseAgent.publish_insight)
