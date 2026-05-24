"""
TPM Tracking Agent — Watchdog for the Bug Pipeline

Acts as a Technical Program Manager that monitors the bug queue:
  1. Runs every 30 minutes
  2. Identifies bugs stuck for > 1 hour
  3. Escalates stuck bugs by increasing severity
  4. Dispatches the Engineer Agent for deep diagnosis
  5. Sends Telegram alerts for stalled bugs
  6. Tracks SLA metrics
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

logger = structlog.get_logger(component="tpm_tracker")

PICKUP_SLA_MINUTES = 60
RESOLVE_SLA_MINUTES = 180
ESCALATION_THRESHOLD_MINUTES = 120
SEVERITY_LADDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class TPMTracker:
    """Watchdog agent — ensures bugs are being processed on time."""

    def __init__(self):
        self._running = False
        self._cycle_count = 0
        self._escalations = 0
        self._engineer_dispatches = 0
        self._last_report_time: Optional[datetime] = None
        self._history: list[dict] = []
        self._max_dispatches_per_cycle = 3

    def _get_all_bugs(self) -> dict:
        try:
            from persistence.db import get_bugs, get_stuck_bugs
            open_bugs = get_bugs(status="OPEN")
            in_progress = get_bugs(status="IN_PROGRESS")
            stuck = get_stuck_bugs(stuck_minutes=PICKUP_SLA_MINUTES)
            resolved_today = [
                b for b in get_bugs(status="RESOLVED")
                if b.get("resolved_at") and
                datetime.fromisoformat(b["resolved_at"]).date() == datetime.now(timezone.utc).date()
            ]
            return {"open": open_bugs, "in_progress": in_progress,
                    "stuck": stuck, "resolved_today": resolved_today}
        except Exception as e:
            logger.error("tpm_bug_query_failed", error=str(e))
            return {"open": [], "in_progress": [], "stuck": [], "resolved_today": []}

    def _check_sla_violations(self, bugs: dict) -> list[dict]:
        violations = []
        now = datetime.now(timezone.utc)

        for bug in bugs.get("open", []):
            created = bug.get("created_at")
            if not created:
                continue
            try:
                created_dt = datetime.fromisoformat(created)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                age_minutes = (now - created_dt).total_seconds() / 60
                if age_minutes > PICKUP_SLA_MINUTES:
                    violations.append({
                        "bug_id": bug["id"], "title": bug.get("title", "?"),
                        "severity": bug.get("severity", "MEDIUM"),
                        "violation": "PICKUP_SLA", "age_minutes": round(age_minutes),
                    })
            except (ValueError, TypeError):
                pass

        for bug in bugs.get("in_progress", []):
            started = bug.get("started_at")
            if not started:
                continue
            try:
                started_dt = datetime.fromisoformat(started)
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=timezone.utc)
                work_minutes = (now - started_dt).total_seconds() / 60
                if work_minutes > RESOLVE_SLA_MINUTES:
                    violations.append({
                        "bug_id": bug["id"], "title": bug.get("title", "?"),
                        "severity": bug.get("severity", "MEDIUM"),
                        "violation": "RESOLVE_SLA", "age_minutes": round(work_minutes),
                        "worker_error": bug.get("worker_error"),
                    })
            except (ValueError, TypeError):
                pass

        return violations

    async def _escalate_bug(self, bug_id: str, current_severity: str, reason: str) -> bool:
        try:
            from persistence.db import update_bug
            current_idx = SEVERITY_LADDER.index(current_severity) if current_severity in SEVERITY_LADDER else 1
            new_idx = min(current_idx + 1, len(SEVERITY_LADDER) - 1)
            new_severity = SEVERITY_LADDER[new_idx]
            if new_severity == current_severity:
                return False
            update_bug(bug_id, severity=new_severity)
            self._escalations += 1
            logger.info("bug_escalated", bug_id=bug_id[:8],
                        from_severity=current_severity, to_severity=new_severity, reason=reason)
            return True
        except Exception as e:
            logger.error("escalation_failed", bug_id=bug_id[:8], error=str(e))
            return False

    async def _dispatch_engineer(self, violation: dict) -> Optional[dict]:
        try:
            from evolution.engineer_agent import engineer_agent
            bug_id = violation["bug_id"]
            logger.info("dispatching_engineer", bug_id=bug_id[:8])
            result = await engineer_agent.diagnose_bug(bug_id)
            self._engineer_dispatches += 1
            return result
        except Exception as e:
            logger.error("engineer_dispatch_failed", error=str(e))
            return {"status": "DISPATCH_FAILED", "error": str(e)}

    async def _send_status_report(self, bugs: dict, violations: list, actions: list):
        try:
            from integrations.telegram_bot import send_alert
            open_c = len(bugs.get("open", []))
            ip_c = len(bugs.get("in_progress", []))
            stuck_c = len(bugs.get("stuck", []))
            res_c = len(bugs.get("resolved_today", []))

            viol_text = ""
            if violations:
                viol_text = "\n\n⚠️ *SLA Violations:*\n" + "\n".join(
                    f"  • `{v['title'][:40]}` — {v['violation']} ({v['age_minutes']}min)"
                    for v in violations[:5])

            await send_alert(
                f"📊 *TPM Status Report*\n\n"
                f"🟡 Open: *{open_c}* | 🔵 In Progress: *{ip_c}*\n"
                f"🔴 Stuck: *{stuck_c}* | ✅ Resolved Today: *{res_c}*\n"
                f"📈 Escalations: *{self._escalations}* | 🔧 Dispatches: *{self._engineer_dispatches}*"
                f"{viol_text}")
        except Exception as e:
            logger.warning("tpm_report_failed", error=str(e))

    async def run_tracking_cycle(self) -> dict:
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)
        actions_taken = []
        logger.info("tpm_cycle_starting", cycle=self._cycle_count)

        bugs = self._get_all_bugs()
        violations = self._check_sla_violations(bugs)

        dispatches = 0
        for v in violations:
            escalated = await self._escalate_bug(v["bug_id"], v["severity"],
                                                  reason=f"{v['violation']}: {v['age_minutes']}min")
            if escalated:
                actions_taken.append({"action": "ESCALATED", "title": v["title"]})

            if v["age_minutes"] > ESCALATION_THRESHOLD_MINUTES:
                await self._escalate_bug(v["bug_id"], "HIGH", reason="Past 2hr threshold")

            if dispatches < self._max_dispatches_per_cycle:
                if v["violation"] == "PICKUP_SLA" or v.get("worker_error"):
                    result = await self._dispatch_engineer(v)
                    if result:
                        dispatches += 1
                        actions_taken.append({"action": "ENGINEER_DISPATCHED", "title": v["title"]})

        await self._send_status_report(bugs, violations, actions_taken)
        self._last_report_time = cycle_start
        cycle_result = {
            "cycle": self._cycle_count, "timestamp": cycle_start.isoformat(),
            "open_bugs": len(bugs.get("open", [])), "violations": len(violations),
            "actions_taken": len(actions_taken),
        }
        self._history.append(cycle_result)
        logger.info("tpm_cycle_complete", cycle=self._cycle_count, violations=len(violations))
        return cycle_result

    async def run_loop(self, interval_minutes: int = 30):
        self._running = True
        logger.info("tpm_tracker_started", interval=f"{interval_minutes}min")
        await asyncio.sleep(90)
        while self._running:
            try:
                await self.run_tracking_cycle()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("tpm_tracker_loop_error", error=str(e))
                await asyncio.sleep(60)
        self._running = False

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "running": self._running, "cycle_count": self._cycle_count,
            "escalations": self._escalations,
            "engineer_dispatches": self._engineer_dispatches,
            "last_report": self._last_report_time.isoformat() if self._last_report_time else None,
            "recent_cycles": self._history[-10:],
        }


# Module-level singleton
tpm_tracker = TPMTracker()
