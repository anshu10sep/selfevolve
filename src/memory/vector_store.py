"""
Vector Store (Qdrant) Integration

Manages the Reflexion memory store for all agents.
Stores trade post-mortems with metadata-filtered retrieval
to prevent "False Analogue" errors.
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(component="vector_store")


class VectorStore:
    """
    Qdrant-backed vector store for agent memory and reflexion.
    
    Each trade post-mortem is stored with rich metadata:
    - Ticker, sector, market_cap_bucket
    - Market regime at decision time
    - VIX level, Fed policy state
    - Outcome and Brier score
    
    Retrieval uses metadata filters to ensure the agent only
    retrieves analogous situations (not false pattern matches).
    """

    COLLECTION_NAME = "reflexion_memory"

    def __init__(self, qdrant_url: str = "http://localhost:6333"):
        self.qdrant_url = qdrant_url
        self._client = None
        self._embedder = None

    async def initialize(self) -> None:
        """Initialize the Qdrant client and create collection if needed."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import (
                VectorParams,
                Distance,
            )

            self._client = QdrantClient(url=self.qdrant_url)

            # Create collection if it doesn't exist
            collections = self._client.get_collections().collections
            exists = any(c.name == self.COLLECTION_NAME for c in collections)

            if not exists:
                self._client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=384,  # all-MiniLM-L6-v2 dimension
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("vector_collection_created", name=self.COLLECTION_NAME)
            else:
                logger.info("vector_collection_exists", name=self.COLLECTION_NAME)

        except ImportError:
            logger.warning("qdrant_client_not_installed")
        except Exception as e:
            logger.error("vector_store_init_failed", error=str(e))

    async def store_postmortem(
        self,
        agent_id: str,
        trade_id: str,
        postmortem_text: str,
        metadata: dict[str, Any],
    ) -> bool:
        """
        Store a trade post-mortem in the vector store.
        
        Args:
            agent_id: ID of the agent that made the prediction
            trade_id: Associated trade ID
            postmortem_text: Linguistic post-mortem (the lesson learned)
            metadata: Contextual metadata for filtered retrieval
        """
        if not self._client:
            return False

        try:
            from qdrant_client.models import PointStruct

            embedding = await self._embed(postmortem_text)
            if embedding is None:
                return False

            point = PointStruct(
                id=trade_id,
                vector=embedding,
                payload={
                    "agent_id": agent_id,
                    "trade_id": trade_id,
                    "text": postmortem_text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **metadata,
                },
            )

            self._client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[point],
            )

            logger.info(
                "postmortem_stored",
                agent_id=agent_id,
                trade_id=trade_id,
            )
            return True

        except Exception as e:
            logger.error("postmortem_store_failed", error=str(e))
            return False

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
        if not self._client:
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            embedding = await self._embed(query_text)
            if embedding is None:
                return []

            # Build metadata filters
            must_conditions = []
            if agent_id:
                must_conditions.append(
                    FieldCondition(key="agent_id", match=MatchValue(value=agent_id))
                )
            if metadata_filters:
                for key, value in metadata_filters.items():
                    must_conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )

            search_filter = Filter(must=must_conditions) if must_conditions else None

            results = self._client.search(
                collection_name=self.COLLECTION_NAME,
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
            logger.error("vector_search_failed", error=str(e))
            return []

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
