"""
SelfEvolve Structured Logging Configuration

Uses structlog for JSON-formatted, structured logging with correlation IDs
for tracing across the multi-agent system.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog

# Context variable for correlation ID tracking across async operations
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get or create a correlation ID for the current context."""
    cid = correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())[:8]
        correlation_id.set(cid)
    return cid


def add_correlation_id(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor to add correlation ID to every log entry."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def add_component(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add component name from logger name."""
    if "component" not in event_dict:
        event_dict["component"] = event_dict.get("_logger_name", "system")
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog for the entire application.
    
    Produces JSON-formatted logs with:
    - ISO timestamps
    - Correlation IDs for cross-agent tracing
    - Component names
    - Log level
    - Structured key-value data
    """
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            add_correlation_id,
            add_component,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Suppress noisy third-party loggers
    for noisy_logger in [
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
        "sqlalchemy.engine",
        "aiohttp",
    ]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger for a specific component.
    
    Args:
        component: Name of the component (e.g., 'judge_agent', 'execution_guardrails')
    
    Returns:
        Bound structlog logger with component context
    """
    return structlog.get_logger(component=component)
