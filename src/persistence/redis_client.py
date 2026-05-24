"""
Redis Client Manager

Connection pooling, pub/sub helpers, heartbeat management,
and hot state operations for the trading system.
"""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis
import structlog

from config.settings import get_settings

logger = structlog.get_logger(component="redis_client")

_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """Get or create the Redis client with connection pooling."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
        _redis_client = aioredis.Redis(connection_pool=pool)
        logger.info("redis_client_created", url=settings.redis_url)
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("redis_client_closed")


async def health_check() -> bool:
    """Check Redis connectivity."""
    try:
        client = await get_redis_client()
        return await client.ping()
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        return False
