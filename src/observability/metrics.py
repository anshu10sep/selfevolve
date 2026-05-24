"""
Prometheus Metrics & Observability

Exposes all system metrics for Prometheus scraping and Grafana dashboards.
Metrics are categorized into: Portfolio, Agents, Execution, Evolution, and System.
"""

from __future__ import annotations

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    start_http_server,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
import structlog

logger = structlog.get_logger(component="metrics")

# ════════════════════════════════════════════════════════════════════
# PORTFOLIO METRICS
# ════════════════════════════════════════════════════════════════════

portfolio_equity = Gauge(
    "selfevolve_portfolio_equity_usd",
    "Current total portfolio equity in USD",
)

portfolio_cash_settled = Gauge(
    "selfevolve_portfolio_cash_settled_usd",
    "Settled cash available for trading",
)

portfolio_drawdown_pct = Gauge(
    "selfevolve_portfolio_drawdown_pct",
    "Current drawdown from high water mark",
)

portfolio_daily_pnl = Gauge(
    "selfevolve_portfolio_daily_pnl_usd",
    "Today's realized P&L in USD",
)

portfolio_net_pnl = Gauge(
    "selfevolve_portfolio_net_pnl_usd",
    "Net P&L (trading profit - API costs)",
)

# ════════════════════════════════════════════════════════════════════
# TRADE METRICS
# ════════════════════════════════════════════════════════════════════

trades_total = Counter(
    "selfevolve_trades_total",
    "Total number of trades executed",
    ["side", "status"],
)

trades_pnl = Histogram(
    "selfevolve_trade_pnl_usd",
    "P&L per trade in USD",
    buckets=[-10, -5, -2, -1, -0.5, 0, 0.5, 1, 2, 5, 10],
)

trades_slippage = Histogram(
    "selfevolve_trade_slippage_pct",
    "Slippage percentage per trade",
    buckets=[0, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0],
)

trades_conviction = Histogram(
    "selfevolve_trade_conviction_score",
    "Judge conviction score distribution",
    buckets=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
)

tranches_available = Gauge(
    "selfevolve_tranches_available",
    "Number of available capital tranches",
)

tranches_locked = Gauge(
    "selfevolve_tranches_locked",
    "Number of locked capital tranches",
)

gfv_strikes = Gauge(
    "selfevolve_gfv_strikes",
    "Current GFV strike count (max 2)",
)

# ════════════════════════════════════════════════════════════════════
# AGENT METRICS
# ════════════════════════════════════════════════════════════════════

agents_active = Gauge(
    "selfevolve_agents_active",
    "Number of active agents",
)

agent_trust_weight = Gauge(
    "selfevolve_agent_trust_weight",
    "Current trust weight per agent",
    ["agent_name", "agent_role"],
)

agent_brier_score = Gauge(
    "selfevolve_agent_brier_score",
    "Rolling Brier score per agent",
    ["agent_name", "agent_role"],
)

agent_invocations = Counter(
    "selfevolve_agent_invocations_total",
    "Total LLM invocations per agent",
    ["agent_name", "model"],
)

# ════════════════════════════════════════════════════════════════════
# LLM COST METRICS
# ════════════════════════════════════════════════════════════════════

llm_cost_total = Counter(
    "selfevolve_llm_cost_usd_total",
    "Total LLM API cost in USD",
    ["model", "task_type"],
)

llm_tokens_total = Counter(
    "selfevolve_llm_tokens_total",
    "Total tokens used",
    ["model", "direction"],  # direction = prompt | completion
)

llm_latency = Histogram(
    "selfevolve_llm_latency_seconds",
    "LLM invocation latency in seconds",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10, 30],
)

llm_budget_remaining = Gauge(
    "selfevolve_llm_budget_remaining_usd",
    "Remaining daily LLM API budget",
)

# ════════════════════════════════════════════════════════════════════
# EVOLUTION METRICS
# ════════════════════════════════════════════════════════════════════

evolution_events_total = Counter(
    "selfevolve_evolution_events_total",
    "Total evolution events",
    ["event_type"],
)

evolution_promotions = Counter(
    "selfevolve_evolution_promotions_total",
    "Total prompt promotions from A/B testing",
)

evolution_rollbacks = Counter(
    "selfevolve_evolution_rollbacks_total",
    "Total prompt rollbacks",
)

# ════════════════════════════════════════════════════════════════════
# SYSTEM HEALTH METRICS
# ════════════════════════════════════════════════════════════════════

system_uptime = Gauge(
    "selfevolve_system_uptime_seconds",
    "System uptime in seconds",
)

circuit_breaker_trips = Counter(
    "selfevolve_circuit_breaker_trips_total",
    "Total circuit breaker trips",
)

hcf_activations = Counter(
    "selfevolve_hcf_activations_total",
    "Total HCF protocol activations",
)

heartbeat_age = Gauge(
    "selfevolve_heartbeat_age_seconds",
    "Age of last overwatch heartbeat in seconds",
)

bugs_open = Gauge(
    "selfevolve_bugs_open",
    "Number of open bug reports",
    ["severity"],
)

system_info = Info(
    "selfevolve_system",
    "System information",
)


def initialize_metrics() -> None:
    """Initialize system info metrics."""
    system_info.info({
        "version": "1.0.0",
        "environment": "paper",
        "account_type": "CASH",
    })

    # Set initial values
    portfolio_equity.set(100.0)
    portfolio_cash_settled.set(100.0)
    tranches_available.set(10)
    llm_budget_remaining.set(1.0)


def start_metrics_server(port: int = 9090) -> None:
    """Start the Prometheus metrics HTTP server."""
    start_http_server(port)
    logger.info("metrics_server_started", port=port)
