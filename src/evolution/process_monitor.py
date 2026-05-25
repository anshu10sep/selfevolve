"""
Process Monitor — Meta-Watchdog for the Bug Pipeline

Monitors the health of the entire autonomous bug lifecycle:
  1. Checks if bug_worker, tpm_tracker, bug_scanner are alive
  2. Tracks pipeline throughput (bugs processed per cycle)
  3. Detects stalled pipelines and files CRITICAL bugs
  4. Monitors systemd service health
  5. Can trigger auto-restart if processes are dead (with cooldown)

Runs every 30 minutes. This is the "watcher that watches the watchers."
"""

from __future__ import annotations

import os
import subprocess
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

logger = structlog.get_logger(component="process_monitor")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOG_DIR = os.path.join(REPO_ROOT, "logs")

# Cooldown: max 1 restart per 30 minutes
RESTART_COOLDOWN_MINUTES = 30


class ProcessMonitor:
    """Meta-watchdog: ensures the bug pipeline itself is healthy."""

    def __init__(self):
        self._running = False
        self._check_count = 0
        self._issues_found = 0
        self._last_restart: Optional[datetime] = None
        self._history: list[dict] = []
        self._pipeline_throughput: list[dict] = []

    # ── Agent Health Checks ──────────────────────────────────────

    def _check_agent_health(self) -> list[dict]:
        """Check if all pipeline agents are running."""
        issues = []

        agents_to_check = [
            ("bug_worker", "evolution.bug_worker", "bug_worker"),
            ("bug_scanner", "evolution.bug_scanner", "bug_scanner"),
            ("tpm_tracker", "evolution.tpm_tracker", "tpm_tracker"),
        ]

        for name, module_path, singleton_name in agents_to_check:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                agent = getattr(mod, singleton_name, None)
                if agent is None:
                    issues.append({
                        "agent": name,
                        "issue": "SINGLETON_MISSING",
                        "severity": "HIGH",
                    })
                elif hasattr(agent, "_running") and not agent._running:
                    issues.append({
                        "agent": name,
                        "issue": "NOT_RUNNING",
                        "severity": "HIGH",
                    })
                elif hasattr(agent, "get_status"):
                    status = agent.get_status()
                    if not status.get("running", False):
                        issues.append({
                            "agent": name,
                            "issue": "STOPPED",
                            "severity": "HIGH",
                            "status": status,
                        })
            except ImportError as e:
                issues.append({
                    "agent": name,
                    "issue": f"IMPORT_FAILED: {e}",
                    "severity": "CRITICAL",
                })
            except Exception as e:
                issues.append({
                    "agent": name,
                    "issue": f"CHECK_FAILED: {e}",
                    "severity": "MEDIUM",
                })

        return issues

    # ── Throughput Monitoring ────────────────────────────────────

    def _check_throughput(self) -> dict:
        """Check if bugs are actually being processed."""
        try:
            from persistence.db import get_bug_summary
            summary = get_bug_summary()

            throughput = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total": summary.get("total", 0),
                "open": summary.get("open", 0),
                "in_progress": summary.get("in_progress", 0),
                "resolved": summary.get("resolved", 0),
                "critical": summary.get("critical", 0),
            }
            self._pipeline_throughput.append(throughput)

            # Keep only last 20 snapshots
            if len(self._pipeline_throughput) > 20:
                self._pipeline_throughput = self._pipeline_throughput[-20:]

            # Check if pipeline is stalled: open count increasing, resolved not
            if len(self._pipeline_throughput) >= 3:
                recent = self._pipeline_throughput[-3:]
                open_trend = [s["open"] for s in recent]
                resolved_trend = [s["resolved"] for s in recent]

                # Stalled = open growing + resolved flat for 3 consecutive checks
                if (open_trend[-1] > open_trend[0] and
                        resolved_trend[-1] == resolved_trend[0] and
                        open_trend[-1] > 0):
                    throughput["stalled"] = True
                else:
                    throughput["stalled"] = False
            else:
                throughput["stalled"] = False

            return throughput

        except Exception as e:
            logger.warning("throughput_check_failed", error=str(e))
            return {"stalled": False, "error": str(e)}

    # ── Service Health ───────────────────────────────────────────

    def _check_service(self) -> dict:
        """Check systemd service status."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "jarvis"],
                capture_output=True, text=True, timeout=5,
            )
            status = result.stdout.strip()
            return {"service": "jarvis", "status": status, "healthy": status == "active"}
        except Exception as e:
            return {"service": "jarvis", "status": "unknown", "healthy": False, "error": str(e)}

    # ── Auto-Restart ─────────────────────────────────────────────

    async def _trigger_restart(self, reason: str) -> bool:
        """Trigger a service restart with cooldown protection."""
        now = datetime.now(timezone.utc)

        if self._last_restart:
            cooldown_delta = timedelta(minutes=RESTART_COOLDOWN_MINUTES)
            if now - self._last_restart < cooldown_delta:
                logger.warning("restart_cooldown_active",
                               last_restart=self._last_restart.isoformat())
                return False

        logger.info("triggering_restart", reason=reason)

        # Notify via Telegram before restart
        try:
            from integrations.telegram_bot import send_alert
            await send_alert(
                f"🔄 *Process Monitor — Restart Triggered*\n\n"
                f"Reason: {reason}\n"
                f"_Restarting in 5 seconds..._"
            )
        except Exception:
            pass

        self._last_restart = now
        await asyncio.sleep(5)

        # Exit cleanly — systemd will restart us
        logger.info("process_monitor_restarting", reason=reason)
        os._exit(0)
        return True  # Unreachable but satisfies type checker

    # ── Bug Filing ───────────────────────────────────────────────

    async def _file_pipeline_bug(self, issue: dict) -> Optional[dict]:
        """File a bug about a pipeline problem (with deduplication)."""
        try:
            from persistence.db import create_bug_dedup

            title = f"[Pipeline] {issue['agent']}: {issue['issue']}"[:200]
            severity = issue.get("severity", "HIGH")

            bug = create_bug_dedup(
                title=title,
                severity=severity,
                source="process_monitor",
                description=(
                    f"Process Monitor detected a pipeline issue:\n"
                    f"Agent: {issue.get('agent', '?')}\n"
                    f"Issue: {issue.get('issue', '?')}\n"
                    f"Time: {datetime.now(timezone.utc).isoformat()}"
                ),
            )

            if bug is None:
                return None  # Duplicate already exists

            self._issues_found += 1
            logger.info("pipeline_bug_filed", title=title[:60])
            return bug
        except Exception as e:
            logger.error("pipeline_bug_filing_failed", error=str(e))
            return None

    # ── Main Monitor Cycle ───────────────────────────────────────

    async def run_monitor_cycle(self) -> dict:
        """Run a full monitoring cycle."""
        self._check_count += 1
        cycle_start = datetime.now(timezone.utc)

        logger.info("monitor_cycle_starting", check=self._check_count)

        # 1. Check agent health
        agent_issues = self._check_agent_health()

        # 2. Check throughput
        throughput = self._check_throughput()

        # 3. Check service health
        service = self._check_service()

        # 4. Take actions
        actions = []

        # File bugs for agent issues
        for issue in agent_issues:
            bug = await self._file_pipeline_bug(issue)
            if bug:
                actions.append({"action": "BUG_FILED", "agent": issue["agent"]})

        # If pipeline is stalled, file a CRITICAL bug
        if throughput.get("stalled"):
            stall_issue = {
                "agent": "pipeline",
                "issue": f"Pipeline stalled: {throughput.get('open', 0)} open, no new resolutions",
                "severity": "CRITICAL",
            }
            bug = await self._file_pipeline_bug(stall_issue)
            if bug:
                actions.append({"action": "STALL_BUG_FILED"})

        # If service is down, try restart
        if not service.get("healthy"):
            actions.append({"action": "SERVICE_UNHEALTHY", "status": service.get("status")})
            # Note: if service is truly dead, this code wouldn't be running.
            # This catches edge cases like "activating" or "degraded" states.

        # Send summary
        try:
            from integrations.telegram_bot import send_alert
            health_emoji = "✅" if not agent_issues and service.get("healthy") else "⚠️"
            stall_emoji = "🔴 STALLED" if throughput.get("stalled") else "🟢 Flowing"

            await send_alert(
                f"🔍 *Process Monitor*\n\n"
                f"{health_emoji} Pipeline Health\n"
                f"  Agents: {len(agent_issues)} issues\n"
                f"  Service: {service.get('status', '?')}\n"
                f"  Flow: {stall_emoji}\n"
                f"  Open bugs: {throughput.get('open', '?')}\n"
                f"  Resolved: {throughput.get('resolved', '?')}\n"
                f"  Actions: {len(actions)}"
            )
        except Exception:
            pass

        cycle_result = {
            "check": self._check_count,
            "timestamp": cycle_start.isoformat(),
            "agent_issues": len(agent_issues),
            "pipeline_stalled": throughput.get("stalled", False),
            "service_healthy": service.get("healthy", False),
            "actions": len(actions),
        }
        self._history.append(cycle_result)

        logger.info("monitor_cycle_complete", check=self._check_count,
                     issues=len(agent_issues), stalled=throughput.get("stalled"))
        return cycle_result

    # ── Background Loop ──────────────────────────────────────────

    async def run_loop(self, interval_minutes: int = 30):
        """Background loop: monitor pipeline every N minutes."""
        self._running = True
        logger.info("process_monitor_started", interval=f"{interval_minutes}min")

        # Longer initial delay — let all other agents start first
        await asyncio.sleep(120)

        while self._running:
            try:
                await self.run_monitor_cycle()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("process_monitor_loop_error", error=str(e))
                await asyncio.sleep(60)

        self._running = False

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "check_count": self._check_count,
            "issues_found": self._issues_found,
            "last_restart": self._last_restart.isoformat() if self._last_restart else None,
            "recent_checks": self._history[-10:],
            "throughput": self._pipeline_throughput[-5:],
        }


# Module-level singleton
process_monitor = ProcessMonitor()
