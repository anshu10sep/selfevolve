"""
Production Readiness Tracker

Monitors paper trading performance and calculates readiness
for production deployment. The Master Agent uses this to tell
the owner: "We are X days from production."

Target: 2 weeks of paper trading with validated metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

from config.constants import (
    PAPER_TRADE_TARGET_DAYS,
    PROD_READINESS_MIN_TRADES,
    PROD_READINESS_MIN_WIN_RATE,
    PROD_READINESS_MAX_DRAWDOWN,
    PROD_READINESS_MIN_SHARPE,
)

logger = structlog.get_logger(component="prod_readiness")


@dataclass
class ReadinessMetric:
    """Individual readiness metric."""
    name: str
    current_value: float
    target_value: float
    unit: str
    passed: bool = False
    description: str = ""

    @property
    def progress_pct(self) -> float:
        """Progress toward target (0-100%)."""
        if self.target_value == 0:
            return 100.0 if self.passed else 0.0
        return min(100.0, (self.current_value / self.target_value) * 100)


@dataclass
class ReadinessReport:
    """Complete production readiness assessment."""
    paper_start_date: datetime
    days_trading: int
    total_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    total_pnl: float
    metrics: list[ReadinessMetric] = field(default_factory=list)
    overall_ready: bool = False
    estimated_days_remaining: int = 14
    assessment: str = ""

    @property
    def readiness_score(self) -> float:
        """Overall readiness score (0-100%)."""
        if not self.metrics:
            return 0.0
        return sum(1 for m in self.metrics if m.passed) / len(self.metrics) * 100


class ProductionReadinessTracker:
    """
    Tracks paper trading metrics and determines when the system
    is ready for production deployment.
    
    The Master Agent reports this to the owner every day.
    """

    def __init__(self, paper_start_date: datetime | None = None):
        self.paper_start_date = paper_start_date or datetime.now(timezone.utc)

    def evaluate(
        self,
        total_trades: int,
        winning_trades: int,
        total_pnl: float,
        max_drawdown_pct: float,
        sharpe_ratio: float,
        api_cost_total: float = 0.0,
        circuit_breaker_trips: int = 0,
        bugs_critical: int = 0,
    ) -> ReadinessReport:
        """
        Evaluate production readiness based on paper trading performance.
        
        Returns a comprehensive report with per-metric pass/fail status.
        """
        now = datetime.now(timezone.utc)
        days_trading = (now - self.paper_start_date).days

        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0

        metrics = [
            ReadinessMetric(
                name="Paper Trading Duration",
                current_value=days_trading,
                target_value=PAPER_TRADE_TARGET_DAYS,
                unit="days",
                passed=days_trading >= PAPER_TRADE_TARGET_DAYS,
                description=f"Trading for {days_trading}/{PAPER_TRADE_TARGET_DAYS} days",
            ),
            ReadinessMetric(
                name="Minimum Trades",
                current_value=total_trades,
                target_value=PROD_READINESS_MIN_TRADES,
                unit="trades",
                passed=total_trades >= PROD_READINESS_MIN_TRADES,
                description=f"{total_trades}/{PROD_READINESS_MIN_TRADES} trades executed",
            ),
            ReadinessMetric(
                name="Win Rate",
                current_value=win_rate,
                target_value=PROD_READINESS_MIN_WIN_RATE,
                unit="%",
                passed=win_rate >= PROD_READINESS_MIN_WIN_RATE,
                description=f"{win_rate:.1%} win rate (target: ≥{PROD_READINESS_MIN_WIN_RATE:.0%})",
            ),
            ReadinessMetric(
                name="Max Drawdown",
                current_value=max_drawdown_pct,
                target_value=PROD_READINESS_MAX_DRAWDOWN * 100,
                unit="%",
                passed=max_drawdown_pct <= PROD_READINESS_MAX_DRAWDOWN * 100,
                description=f"{max_drawdown_pct:.1f}% drawdown (target: <{PROD_READINESS_MAX_DRAWDOWN*100:.0f}%)",
            ),
            ReadinessMetric(
                name="Sharpe Ratio",
                current_value=sharpe_ratio,
                target_value=PROD_READINESS_MIN_SHARPE,
                unit="ratio",
                passed=sharpe_ratio >= PROD_READINESS_MIN_SHARPE,
                description=f"Sharpe: {sharpe_ratio:.2f} (target: ≥{PROD_READINESS_MIN_SHARPE})",
            ),
            ReadinessMetric(
                name="Profitable System",
                current_value=total_pnl,
                target_value=0.0,
                unit="USD",
                passed=total_pnl > 0,
                description=f"Net P&L: ${total_pnl:.2f} (must be positive)",
            ),
            ReadinessMetric(
                name="Circuit Breaker Stability",
                current_value=circuit_breaker_trips,
                target_value=0,
                unit="trips",
                passed=circuit_breaker_trips == 0,
                description=f"{circuit_breaker_trips} circuit breaker trips (must be 0)",
            ),
            ReadinessMetric(
                name="No Critical Bugs",
                current_value=bugs_critical,
                target_value=0,
                unit="bugs",
                passed=bugs_critical == 0,
                description=f"{bugs_critical} critical bugs (must be 0)",
            ),
        ]

        overall_ready = all(m.passed for m in metrics)

        # Estimate remaining days
        if overall_ready:
            estimated_remaining = 0
        else:
            # Calculate based on the most lagging metric
            remaining_days = max(0, PAPER_TRADE_TARGET_DAYS - days_trading)
            if total_trades < PROD_READINESS_MIN_TRADES and total_trades > 0:
                trades_per_day = total_trades / max(1, days_trading)
                trade_days_needed = (PROD_READINESS_MIN_TRADES - total_trades) / max(1, trades_per_day)
                remaining_days = max(remaining_days, int(trade_days_needed) + 1)
            estimated_remaining = max(1, remaining_days)

        # Generate assessment
        passed_count = sum(1 for m in metrics if m.passed)
        if overall_ready:
            assessment = (
                "🟢 PRODUCTION READY. All metrics meet or exceed targets. "
                "Recommend switching ALPACA_BASE_URL to https://api.alpaca.markets "
                "and ENVIRONMENT to 'live'."
            )
        elif passed_count >= 6:
            assessment = (
                f"🟡 ALMOST READY. {passed_count}/{len(metrics)} metrics passing. "
                f"Estimated {estimated_remaining} day(s) remaining."
            )
        elif passed_count >= 4:
            assessment = (
                f"🟠 MAKING PROGRESS. {passed_count}/{len(metrics)} metrics passing. "
                f"Estimated {estimated_remaining} day(s) remaining. "
                "Focus on failing metrics."
            )
        else:
            assessment = (
                f"🔴 NOT READY. {passed_count}/{len(metrics)} metrics passing. "
                f"Estimated {estimated_remaining} day(s) remaining. "
                "System needs more trading data and stability."
            )

        report = ReadinessReport(
            paper_start_date=self.paper_start_date,
            days_trading=days_trading,
            total_trades=total_trades,
            win_rate=win_rate,
            max_drawdown=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            total_pnl=total_pnl,
            metrics=metrics,
            overall_ready=overall_ready,
            estimated_days_remaining=estimated_remaining,
            assessment=assessment,
        )

        logger.info(
            "readiness_evaluated",
            overall_ready=overall_ready,
            score=report.readiness_score,
            days_remaining=estimated_remaining,
            passed=passed_count,
            total=len(metrics),
        )

        return report

    def format_report(self, report: ReadinessReport) -> str:
        """Format the readiness report for the owner."""
        lines = [
            "# Production Readiness Report",
            f"Paper Trading Start: {report.paper_start_date.strftime('%Y-%m-%d')}",
            f"Days Trading: {report.days_trading}",
            f"Total Trades: {report.total_trades}",
            f"Net P&L: ${report.total_pnl:.2f}",
            "",
            f"## Assessment: {report.assessment}",
            f"## Readiness Score: {report.readiness_score:.0f}%",
            f"## Estimated Days to Production: {report.estimated_days_remaining}",
            "",
            "## Metrics",
        ]

        for m in report.metrics:
            status = "✅" if m.passed else "❌"
            lines.append(f"  {status} {m.name}: {m.description}")

        return "\n".join(lines)
