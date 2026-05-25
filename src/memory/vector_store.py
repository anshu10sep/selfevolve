"""
Vector Store (Qdrant) Integration

Manages multiple memory collections for the SelfEvolve agent system:
1. reflexion_memory  — Post-mortem lessons from trade decisions
2. trade_context     — Full trade decision snapshots for cross-agent learning
3. strategy_rules    — Strategic_Nuance evolution history for meta-analysis

All collections use metadata-filtered retrieval to prevent
"False Analogue" errors (e.g., a 2021 CPI spike should not match
a 2026 CPI spike if the macro regime is different).
"""

from __future__ import annotations

import uuid
from typing import Any, Optional
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(component="vector_store")


# Collection definitions
COLLECTIONS = {
    "reflexion_memory": {
        "description": "Post-mortem lessons from trade analysis",
        "vector_size": 384,  # all-MiniLM-L6-v2
    },
    "trade_context": {
        "description": "Full trade decision snapshots for cross-agent retrieval",
        "vector_size": 384,
    },
    "strategy_rules": {
        "description": "Strategic_Nuance evolution history for meta-analysis",
        "vector_size": 384,
    },
}


class VectorStore:
    """
    Qdrant-backed vector store for agent memory, reflexion, and
    cross-agent learning.

    Provides scoped retrieval: any agent can read from any collection,
    but writes are tagged by source agent role for audit trail.

    Falls back to an in-memory dict store if Qdrant is unavailable,
    enabling development/testing without infrastructure dependencies.
    """

    def __init__(self, qdrant_url: str = None):
        if qdrant_url is None:
            try:
                from config.settings import get_settings
                qdrant_url = get_settings().qdrant_url
            except Exception:
                qdrant_url = "http://localhost:6333"
        self.qdrant_url = qdrant_url
        self._client = None
        self._embedder = None
        self._fallback_store: dict[str, list[dict]] = {}  # In-memory fallback
        self._using_fallback = False

    async def initialize(self) -> None:
        """Initialize the Qdrant client and create all collections."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance

            self._client = QdrantClient(url=self.qdrant_url)

            # Create all collections
            existing = {
                c.name for c in self._client.get_collections().collections
            }

            for name, config in COLLECTIONS.items():
                if name not in existing:
                    self._client.create_collection(
                        collection_name=name,
                        vectors_config=VectorParams(
                            size=config["vector_size"],
                            distance=Distance.COSINE,
                        ),
                    )
                    logger.info(
                        "vector_collection_created",
                        name=name,
                        description=config["description"],
                    )
                else:
                    logger.info("vector_collection_exists", name=name)

            logger.info(
                "vector_store_initialized",
                collections=list(COLLECTIONS.keys()),
                backend="qdrant",
            )

        except ImportError:
            logger.warning(
                "qdrant_not_installed_using_fallback",
                message="Install qdrant-client for persistent vector storage",
            )
            self._using_fallback = True
        except Exception as e:
            logger.warning(
                "qdrant_connection_failed_using_fallback",
                error=str(e),
                message="Falling back to in-memory store",
            )
            self._using_fallback = True

    # ═══════════════════════════════════════════════════════════════════
    # POST-MORTEM / REFLEXION MEMORY
    # ═══════════════════════════════════════════════════════════════════

    async def store_postmortem(
        self,
        agent_id: str,
        trade_id: str,
        postmortem_text: str,
        metadata: dict[str, Any],
    ) -> bool:
        """
        Store a trade post-mortem in the reflexion_memory collection.

        Args:
            agent_id: ID of the agent that made the prediction
            trade_id: Associated trade ID
            postmortem_text: Linguistic post-mortem (the lesson learned)
            metadata: Contextual metadata for filtered retrieval
                Expected keys: agent_role, ticker, market_regime, brier_score, sector
        """
        return await self._store(
            collection="reflexion_memory",
            point_id=trade_id,
            text=postmortem_text,
            metadata={
                "agent_id": agent_id,
                "trade_id": trade_id,
                "text": postmortem_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **metadata,
            },
        )

    async def retrieve_relevant(
        self,
        query_text: str,
        agent_id: Optional[str] = None,
        metadata_filters: Optional[dict] = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant post-mortems with metadata filtering.

        This is the key defense against "False Analogue" errors:
        a 2021 CPI spike should not match a 2026 CPI spike if the
        macro regime is different.
        """
        filters = {}
        if agent_id:
            filters["agent_id"] = agent_id
        if metadata_filters:
            filters.update(metadata_filters)

        return await self._search(
            collection="reflexion_memory",
            query_text=query_text,
            filters=filters,
            limit=limit,
        )

    # ═══════════════════════════════════════════════════════════════════
    # TRADE CONTEXT (Cross-Agent Learning)
    # ═══════════════════════════════════════════════════════════════════

    async def store_trade_context(
        self,
        trade_id: str,
        ticker: str,
        action: str,
        context_text: str,
        analyst_scores: dict[str, float],
        debate_summary: str,
        judge_reasoning: str,
        market_regime: str = "UNKNOWN",
        outcome: Optional[str] = None,
        pnl: Optional[float] = None,
    ) -> bool:
        """
        Store a complete trade decision snapshot for cross-agent retrieval.

        This enables any agent to ask "what did we do last time in a
        similar situation?" across the entire analyst team.

        Args:
            trade_id: Unique trade identifier
            ticker: Asset symbol
            action: BUY/SELL/PASS
            context_text: Human-readable trade narrative
            analyst_scores: Dict of agent_role → conviction score
            debate_summary: Bull/Bear debate summary
            judge_reasoning: Judge's final reasoning
            market_regime: Market regime at time of trade
            outcome: Trade outcome (win/loss/pending)
            pnl: Profit/loss if closed
        """
        full_text = (
            f"Trade {action} {ticker} in {market_regime} regime. "
            f"Debate: {debate_summary[:200]}. "
            f"Judge: {judge_reasoning[:200]}. "
            f"Outcome: {outcome or 'pending'}."
        )

        return await self._store(
            collection="trade_context",
            point_id=trade_id,
            text=full_text,
            metadata={
                "trade_id": trade_id,
                "ticker": ticker,
                "action": action,
                "market_regime": market_regime,
                "analyst_scores": analyst_scores,
                "debate_summary": debate_summary[:500],
                "judge_reasoning": judge_reasoning[:300],
                "outcome": outcome or "pending",
                "pnl": pnl,
                "text": full_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def retrieve_cross_agent(
        self,
        query_text: str,
        market_regime: Optional[str] = None,
        ticker: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve trade contexts from ALL agents, filtered by conditions.

        This is the cross-agent learning mechanism: the Technical Analyst
        can see what the full team decided last time the market was in
        a similar regime.

        Args:
            query_text: Natural language query (e.g., "AAPL in bear market")
            market_regime: Filter by regime (BULL, BEAR, PANIC, etc.)
            ticker: Filter by specific ticker
            outcome: Filter by outcome (win, loss)
            limit: Max results
        """
        filters = {}
        if market_regime:
            filters["market_regime"] = market_regime
        if ticker:
            filters["ticker"] = ticker
        if outcome:
            filters["outcome"] = outcome

        return await self._search(
            collection="trade_context",
            query_text=query_text,
            filters=filters,
            limit=limit,
        )

    # ═══════════════════════════════════════════════════════════════════
    # STRATEGY RULES (Evolution History)
    # ═══════════════════════════════════════════════════════════════════

    async def store_rule_evolution(
        self,
        agent_role: str,
        version: int,
        nuance_text: str,
        change_description: str,
        brier_before: float,
        brier_after: Optional[float] = None,
        status: str = "CANDIDATE",
    ) -> bool:
        """
        Track the history of Strategic_Nuance changes for meta-analysis.

        This allows the MetaReview to see what prompt changes have been
        tried before, what worked, and what failed — preventing repetition.

        Args:
            agent_role: Agent role being evolved
            version: Prompt version number
            nuance_text: The Strategic_Nuance text
            change_description: Why this change was made
            brier_before: Brier score before the change
            brier_after: Brier score after (if evaluated)
            status: CANDIDATE, PROMOTED, DISCARDED
        """
        rule_id = f"{agent_role}_v{version}"
        full_text = (
            f"Agent {agent_role} v{version}: {change_description}. "
            f"Nuance: {nuance_text[:300]}. "
            f"Brier before: {brier_before:.4f}. "
            f"Status: {status}."
        )

        return await self._store(
            collection="strategy_rules",
            point_id=rule_id,
            text=full_text,
            metadata={
                "agent_role": agent_role,
                "version": version,
                "nuance_text": nuance_text,
                "change_description": change_description,
                "brier_before": brier_before,
                "brier_after": brier_after,
                "status": status,
                "text": full_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def retrieve_rule_history(
        self,
        agent_role: str,
        query_text: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve past Strategic_Nuance changes for an agent.

        Used by MetaReview to avoid proposing changes that have
        already been tried and failed.

        Args:
            agent_role: Filter by agent role
            query_text: Optional semantic query
            status: Filter by status (PROMOTED, DISCARDED, CANDIDATE)
            limit: Max results
        """
        filters = {"agent_role": agent_role}
        if status:
            filters["status"] = status

        search_text = query_text or f"Strategic nuance evolution for {agent_role}"

        return await self._search(
            collection="strategy_rules",
            query_text=search_text,
            filters=filters,
            limit=limit,
        )

    # ═══════════════════════════════════════════════════════════════════
    # INTERNAL: Unified Store / Search with Qdrant + Fallback
    # ═══════════════════════════════════════════════════════════════════

    async def _store(
        self,
        collection: str,
        point_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> bool:
        """Store a vector point in the specified collection."""
        if self._using_fallback:
            return self._fallback_store_point(collection, point_id, text, metadata)

        if not self._client:
            return False

        try:
            from qdrant_client.models import PointStruct

            embedding = await self._embed(text)
            if embedding is None:
                return self._fallback_store_point(collection, point_id, text, metadata)

            point = PointStruct(
                id=point_id if isinstance(point_id, int) else hash(point_id) % (2**63),
                vector=embedding,
                payload=metadata,
            )

            self._client.upsert(
                collection_name=collection,
                points=[point],
            )

            logger.info(
                "vector_point_stored",
                collection=collection,
                point_id=point_id[:20] if isinstance(point_id, str) else point_id,
            )
            return True

        except Exception as e:
            logger.error(
                "vector_store_failed",
                collection=collection,
                error=str(e),
            )
            return self._fallback_store_point(collection, point_id, text, metadata)

    async def _search(
        self,
        collection: str,
        query_text: str,
        filters: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search a collection with metadata filtering."""
        if self._using_fallback:
            return self._fallback_search(collection, filters, limit)

        if not self._client:
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            embedding = await self._embed(query_text)
            if embedding is None:
                return self._fallback_search(collection, filters, limit)

            # Build metadata filters
            must_conditions = []
            for key, value in filters.items():
                if value is not None:
                    must_conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )

            search_filter = Filter(must=must_conditions) if must_conditions else None

            results = self._client.search(
                collection_name=collection,
                query_vector=embedding,
                query_filter=search_filter,
                limit=limit,
            )

            return [
                {
                    "text": r.payload.get("text", ""),
                    "score": r.score,
                    "metadata": r.payload,
                }
                for r in results
            ]

        except Exception as e:
            logger.error(
                "vector_search_failed",
                collection=collection,
                error=str(e),
            )
            return self._fallback_search(collection, filters, limit)

    # ═══════════════════════════════════════════════════════════════════
    # FALLBACK: In-Memory Dict Store
    # ═══════════════════════════════════════════════════════════════════

    def _fallback_store_point(
        self,
        collection: str,
        point_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> bool:
        """Store a point in the in-memory fallback store."""
        if collection not in self._fallback_store:
            self._fallback_store[collection] = []

        self._fallback_store[collection].append({
            "id": point_id,
            "text": text,
            "metadata": metadata,
        })

        # Cap at 1000 entries per collection to prevent memory bloat
        if len(self._fallback_store[collection]) > 1000:
            self._fallback_store[collection] = self._fallback_store[collection][-1000:]

        logger.debug(
            "fallback_store_point",
            collection=collection,
            total_points=len(self._fallback_store[collection]),
        )
        return True

    def _fallback_search(
        self,
        collection: str,
        filters: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Search the in-memory fallback store (exact metadata match, no semantic)."""
        entries = self._fallback_store.get(collection, [])
        if not entries:
            return []

        # Filter by metadata
        matched = []
        for entry in reversed(entries):  # Most recent first
            meta = entry.get("metadata", {})
            match = all(
                meta.get(k) == v for k, v in filters.items() if v is not None
            )
            if match:
                matched.append({
                    "text": entry.get("text", ""),
                    "score": 1.0,  # No semantic score in fallback
                    "metadata": meta,
                })
            if len(matched) >= limit:
                break

        return matched

    # ═══════════════════════════════════════════════════════════════════
    # EMBEDDING
    # ═══════════════════════════════════════════════════════════════════

    async def _embed(self, text: str) -> Optional[list[float]]:
        """Generate an embedding for text."""
        try:
            if self._embedder is None:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")

            embedding = self._embedder.encode(text).tolist()
            return embedding
        except ImportError:
            logger.warning("sentence_transformers_not_installed")
            return None
        except Exception as e:
            logger.error("embedding_failed", error=str(e))
            return None

    # ═══════════════════════════════════════════════════════════════════
    # HEALTH / STATS
    # ═══════════════════════════════════════════════════════════════════

    def get_stats(self) -> dict[str, Any]:
        """Get vector store statistics."""
        stats = {
            "backend": "fallback" if self._using_fallback else "qdrant",
            "qdrant_url": self.qdrant_url,
            "collections": {},
        }

        if self._using_fallback:
            for name in COLLECTIONS:
                stats["collections"][name] = {
                    "points": len(self._fallback_store.get(name, [])),
                }
        elif self._client:
            try:
                for name in COLLECTIONS:
                    info = self._client.get_collection(name)
                    stats["collections"][name] = {
                        "points": info.points_count,
                        "vectors": info.vectors_count,
                    }
            except Exception as e:
                stats["error"] = str(e)

        return stats


# ═══════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════

_vector_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get the singleton VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance


async def initialize_vector_store() -> VectorStore:
    """Initialize and return the singleton VectorStore."""
    store = get_vector_store()
    await store.initialize()
    return store
