"""
Phase 4 Integration Tests — VectorStore & Memory

Tests the VectorStore in-memory fallback mode (no Qdrant required)
and validates the memory tools return the expected format.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta


# ════════════════════════════════════════════════════════════════════
# TEST: VectorStore (In-Memory Fallback)
# ════════════════════════════════════════════════════════════════════

class TestVectorStore:
    """Tests for VectorStore in-memory fallback mode."""

    def _get_store(self):
        """Get a fresh VectorStore instance in fallback mode."""
        from memory.vector_store import VectorStore
        store = VectorStore.__new__(VectorStore)
        store._client = None
        store._embedder = None
        store._using_fallback = True
        store.qdrant_url = "test://mock"
        store._fallback_store = {
            "reflexion_memory": [],
            "trade_context": [],
            "strategy_rules": [],
        }
        return store

    def _run(self, coro):
        """Run an async function synchronously."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_store_and_retrieve_postmortem(self):
        """Post-mortem stored in reflexion_memory is retrievable."""
        store = self._get_store()

        self._run(store.store_postmortem(
            agent_id="technical_analyst",
            trade_id="trade-001",
            postmortem_text="RSI overbought led to false breakout",
            metadata={
                "agent_role": "technical_analyst",
                "brier_score": 0.45,
                "market_regime": "BULL",
                "ticker": "AAPL",
            },
        ))

        results = self._run(store.retrieve_relevant(
            query_text="RSI overbought breakout",
            agent_id="technical_analyst",
            limit=5,
        ))

        assert len(results) >= 1
        assert "RSI overbought" in results[0].get("text", results[0].get("metadata", {}).get("text", ""))

    def test_store_multiple_postmortems_different_agents(self):
        """Post-mortems from different agents are stored separately."""
        store = self._get_store()

        self._run(store.store_postmortem(
            agent_id="technical_analyst",
            trade_id="trade-001",
            postmortem_text="Momentum divergence missed",
            metadata={"agent_role": "technical_analyst", "market_regime": "BULL"},
        ))
        self._run(store.store_postmortem(
            agent_id="fundamental_analyst",
            trade_id="trade-002",
            postmortem_text="P/E expansion overlooked",
            metadata={"agent_role": "fundamental_analyst", "market_regime": "BULL"},
        ))

        # Filter by agent_id
        results = self._run(store.retrieve_relevant(
            query_text="analyst error",
            agent_id="technical_analyst",
            limit=10,
        ))

        # Should only get technical_analyst results
        assert len(results) >= 1
        for r in results:
            meta = r.get("metadata", {})
            assert meta.get("agent_id") == "technical_analyst"

    def test_store_trade_context(self):
        """Trade context is stored and retrievable via cross-agent query."""
        store = self._get_store()

        self._run(store.store_trade_context(
            trade_id="trade-100",
            ticker="AAPL",
            action="BUY",
            context_text="Strong momentum with volume breakout",
            analyst_scores={"technical": 0.8, "fundamental": 0.5},
            debate_summary="Bull argued breakout, Bear argued overextended",
            judge_reasoning="Breakout with volume confirmation",
            market_regime="BULL",
            outcome="win",
            pnl=35.0,
        ))

        results = self._run(store.retrieve_cross_agent(
            query_text="AAPL trade",
            ticker="AAPL",
            limit=5,
        ))

        assert len(results) >= 1

    def test_store_rule_evolution(self):
        """Rule evolution history is tracked."""
        store = self._get_store()

        self._run(store.store_rule_evolution(
            agent_role="technical_analyst",
            version=3,
            nuance_text="Added RSI divergence check to prompt",
            change_description="Incorporate RSI divergence for better breakout detection",
            brier_before=0.45,
            brier_after=0.32,
            status="PROMOTED",
        ))

        results = self._run(store.retrieve_rule_history(
            agent_role="technical_analyst",
            limit=10,
        ))

        assert len(results) >= 1

    def test_retrieve_empty_collection(self):
        """Querying an empty collection returns empty list."""
        store = self._get_store()

        results = self._run(store.retrieve_relevant(
            query_text="anything",
            limit=5,
        ))
        assert results == []

    def test_retrieve_cross_agent_empty(self):
        """Cross-agent query on empty collection returns empty list."""
        store = self._get_store()

        results = self._run(store.retrieve_cross_agent(
            query_text="anything",
            limit=5,
        ))
        assert results == []

    def test_get_stats(self):
        """Stats reflect stored document counts."""
        store = self._get_store()

        self._run(store.store_postmortem(
            agent_id="ta",
            trade_id="t1",
            postmortem_text="lesson 1",
            metadata={"agent_role": "ta"},
        ))
        self._run(store.store_postmortem(
            agent_id="fa",
            trade_id="t2",
            postmortem_text="lesson 2",
            metadata={"agent_role": "fa"},
        ))
        self._run(store.store_trade_context(
            trade_id="trade-1",
            ticker="AAPL",
            action="BUY",
            context_text="test trade",
            analyst_scores={"ta": 0.5},
            debate_summary="test",
            judge_reasoning="test",
        ))

        stats = store.get_stats()
        assert stats["collections"]["reflexion_memory"]["points"] == 2
        assert stats["collections"]["trade_context"]["points"] == 1
        assert stats["collections"]["strategy_rules"]["points"] == 0
        assert stats["backend"] == "fallback"


# ════════════════════════════════════════════════════════════════════
# TEST: Memory Tools Output Format
# ════════════════════════════════════════════════════════════════════

class TestMemoryToolsFormat:
    """Tests that memory tool registration and output format are correct."""

    def test_memory_tools_importable(self):
        """Memory tools module imports cleanly."""
        from agents.skills.memory import memory_tools
        assert hasattr(memory_tools, 'recall_technical_lessons')
        assert hasattr(memory_tools, 'recall_fundamental_lessons')
        assert hasattr(memory_tools, 'recall_sentiment_lessons')
        assert hasattr(memory_tools, 'recall_macro_lessons')
        assert hasattr(memory_tools, 'recall_similar_trades')

    def test_memory_tools_are_callable(self):
        """Each memory tool is a callable function."""
        from agents.skills.memory.memory_tools import (
            recall_technical_lessons,
            recall_fundamental_lessons,
            recall_sentiment_lessons,
            recall_macro_lessons,
            recall_similar_trades,
        )
        assert callable(recall_technical_lessons)
        assert callable(recall_fundamental_lessons)
        assert callable(recall_sentiment_lessons)
        assert callable(recall_macro_lessons)
        assert callable(recall_similar_trades)

    def test_recall_returns_dict_with_no_store(self):
        """recall_* tools return gracefully when VectorStore is empty."""
        from agents.skills.memory.memory_tools import recall_technical_lessons

        result = recall_technical_lessons(query="RSI test")
        assert isinstance(result, dict)
        # Should have a 'lessons' key or 'error' key
        assert "lessons" in result or "error" in result
