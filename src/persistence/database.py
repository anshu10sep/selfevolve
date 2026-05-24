"""
Database Connection Manager

Async SQLAlchemy engine with connection pooling, health checks,
and schema initialization from SQL files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import structlog

from config.settings import get_settings

logger = structlog.get_logger(component="database")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def get_engine() -> AsyncEngine:
    """Get or create the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.postgres_url,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=3600,
            echo=False,
        )
        logger.info("database_engine_created", url=settings.postgres_url.split("@")[-1])
    return _engine


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        engine = await get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection for async database sessions."""
    factory = await get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def initialize_database() -> None:
    """
    Initialize the database by executing all SQL schema files.
    
    Schema files are executed in sorted order (001_*, 002_*, etc.)
    to respect foreign key dependencies.
    """
    engine = await get_engine()
    schemas_dir = Path(__file__).parent / "schemas"

    if not schemas_dir.exists():
        logger.warning("schemas_directory_not_found", path=str(schemas_dir))
        return

    sql_files = sorted(schemas_dir.glob("*.sql"))
    async with engine.begin() as conn:
        for sql_file in sql_files:
            try:
                sql = sql_file.read_text()
                await conn.execute(sql)  # type: ignore
                logger.info("schema_executed", file=sql_file.name)
            except Exception as e:
                logger.error(
                    "schema_execution_failed",
                    file=sql_file.name,
                    error=str(e),
                )
                raise


async def health_check() -> bool:
    """Check database connectivity."""
    try:
        engine = await get_engine()
        async with engine.connect() as conn:
            from sqlalchemy import text
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return False


async def close_database() -> None:
    """Close the database engine and release all connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_engine_closed")
