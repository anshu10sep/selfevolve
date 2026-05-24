"""
Bug Scanner Agent — Proactive Bug Detection

Continuously scans the codebase and runtime logs for issues:
  1. Parses jarvis.log / jarvis-error.log for ERROR/CRITICAL entries
  2. Validates Python imports across all agent modules
  3. Checks key integration health (DB, API connectivity)
  4. Auto-files bugs into the database when issues are found

Runs every 30 minutes as a background task in main.py.
"""

from __future__ import annotations

import os
import re
import importlib
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

logger = structlog.get_logger(component="bug_scanner")

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.abspath(os.path.join(SRC_ROOT, ".."))
LOG_DIR = os.path.join(REPO_ROOT, "logs")


class BugScanner:
    """Proactive bug detection — scans logs and code for issues."""

    def __init__(self):
        self._running = False
        self._scan_count = 0
        self._bugs_filed = 0
        self._last_scan_time: Optional[datetime] = None
        self._seen_errors: set[str] = set()  # Dedup: don't file same bug twice
        self._history: list[dict] = []

    # ── Log Scanning ──────────────────────────────────────────────

    def _scan_log_file(self, log_path: str, since_minutes: int = 35) -> list[dict]:
        """
        Parse a structured JSON log file for ERROR/CRITICAL entries
        that occurred within the last `since_minutes`.

        Returns list of dicts: {timestamp, level, component, event, message}
        """
        if not os.path.exists(log_path):
            return []

        errors = []
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

        try:
            import json
            with open(log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # Try JSON structured log
                    try:
                        entry = json.loads(line)
                        level = entry.get("level", "").upper()
                        if level not in ("ERROR", "CRITICAL"):
                            continue

                        ts_str = entry.get("timestamp", "")
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if ts < cutoff:
                                    continue
                            except (ValueError, TypeError):
                                pass

                        errors.append({
                            "timestamp": ts_str,
                            "level": level,
                            "component": entry.get("component", "unknown"),
                            "event": entry.get("event", ""),
                            "message": entry.get("error", entry.get("message", "")),
                            "source_file": log_path,
                        })
                    except json.JSONDecodeError:
                        # Plain text log line — check for ERROR/CRITICAL keywords
                        if any(kw in line.upper() for kw in ("ERROR", "CRITICAL", "TRACEBACK")):
                            errors.append({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "level": "ERROR",
                                "component": "unknown",
                                "event": "plain_text_error",
                                "message": line[:200],
                                "source_file": log_path,
                            })
        except Exception as e:
            logger.warning("log_scan_error", file=log_path, error=str(e))

        return errors

    def scan_all_logs(self, since_minutes: int = 35) -> list[dict]:
        """Scan all log files for recent errors."""
        all_errors = []

        log_files = [
            os.path.join(LOG_DIR, "jarvis.log"),
            os.path.join(LOG_DIR, "jarvis-error.log"),
        ]

        for lf in log_files:
            errors = self._scan_log_file(lf, since_minutes=since_minutes)
            all_errors.extend(errors)

        return all_errors

    # ── Import Validation ────────────────────────────────────────

    def scan_imports(self) -> list[dict]:
        """
        Validate that all critical modules can be imported.
        Returns list of import failures.
        """
        critical_modules = [
            "agents.skills.jarvis.github_ops",
            "agents.skills.jarvis.system_audit",
            "agents.skills.jarvis.code_generation",
            "evolution.bug_worker",
            "evolution.self_healer",
            "evolution.self_evolution",
            "evolution.hot_reloader",
            "persistence.db",
            "core.llm_utils",
            "config.settings",
        ]

        failures = []
        for module_name in critical_modules:
            try:
                importlib.import_module(module_name)
            except Exception as e:
                failures.append({
                    "module": module_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                })
                logger.warning("import_check_failed", module=module_name, error=str(e))

        return failures

    # ── Integration Health ───────────────────────────────────────

    def check_db_health(self) -> Optional[dict]:
        """Verify the database is accessible."""
        try:
            from persistence.db import get_session
            with get_session() as s:
                s.execute("SELECT 1")  # noqa: raw SQL health check
            return None  # Healthy
        except Exception as e:
            return {
                "component": "database",
                "error": str(e),
                "severity": "CRITICAL",
            }

    def check_service_health(self) -> Optional[dict]:
        """Check if the jarvis systemd service is healthy."""
        try:
            import subprocess
            result = subprocess.run(
                ["systemctl", "is-active", "jarvis"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip() != "active":
                return {
                    "component": "systemd_service",
                    "error": f"Service status: {result.stdout.strip()}",
                    "severity": "CRITICAL",
                }
            return None
        except Exception as e:
            return {
                "component": "systemd_service",
                "error": str(e),
                "severity": "HIGH",
            }

    # ── Bug Filing ───────────────────────────────────────────────

    def _make_dedup_key(self, error: dict) -> str:
        """Create a deduplication key for an error."""
        component = error.get("component", "")
        event = error.get("event", "")
        msg = error.get("message", "")[:80]
        return f"{component}:{event}:{msg}"

    async def file_bug_from_error(self, error: dict) -> Optional[dict]:
        """File a bug in the database from a detected error."""
        dedup_key = self._make_dedup_key(error)
        if dedup_key in self._seen_errors:
            return None  # Already filed

        try:
            from persistence.db import create_bug
            import uuid

            severity = error.get("severity", "MEDIUM")
            if error.get("level") == "CRITICAL":
                severity = "CRITICAL"
            elif error.get("level") == "ERROR":
                severity = "HIGH"

            title = (
                f"[Auto] {error.get('component', 'unknown')}: "
                f"{error.get('event', error.get('message', 'Unknown error'))}"
            )[:200]

            description = (
                f"Detected by Bug Scanner at {datetime.now(timezone.utc).isoformat()}\n\n"
                f"Component: {error.get('component', 'unknown')}\n"
                f"Event: {error.get('event', '')}\n"
                f"Message: {error.get('message', '')}\n"
                f"Source: {error.get('source_file', '')}\n"
                f"Original timestamp: {error.get('timestamp', '')}"
            )

            bug = create_bug(
                id=str(uuid.uuid4()),
                title=title,
                severity=severity,
                source="bug_scanner",
                description=description,
            )

            self._seen_errors.add(dedup_key)
            self._bugs_filed += 1
            logger.info("bug_auto_filed", title=title[:60], severity=severity)

            # Telegram notification
            try:
                from integrations.telegram_bot import send_alert
                await send_alert(
                    f"🔍 *Bug Scanner — New Bug Filed*\n\n"
                    f"[{severity}] `{title[:60]}`\n"
                    f"Component: {error.get('component', '?')}\n"
                    f"Source: bug_scanner"
                )
            except Exception:
                pass

            return bug

        except Exception as e:
            logger.error("bug_filing_failed", error=str(e))
            return None

    # ── Main Scan Cycle ──────────────────────────────────────────

    async def run_scan(self) -> dict:
        """Run a full scan cycle: logs + imports + integrations."""
        self._scan_count += 1
        scan_start = datetime.now(timezone.utc)
        bugs_filed = 0

        logger.info("bug_scan_starting", scan_number=self._scan_count)

        # 1. Scan logs for errors
        log_errors = self.scan_all_logs(since_minutes=35)
        for error in log_errors:
            result = await self.file_bug_from_error(error)
            if result:
                bugs_filed += 1

        # 2. Check imports
        import_failures = self.scan_imports()
        for failure in import_failures:
            error = {
                "component": "import_check",
                "event": f"import_failed:{failure['module']}",
                "message": f"Cannot import {failure['module']}: {failure['error']}",
                "severity": "HIGH",
            }
            result = await self.file_bug_from_error(error)
            if result:
                bugs_filed += 1

        # 3. Check integrations
        for check_fn in [self.check_db_health, self.check_service_health]:
            issue = check_fn()
            if issue:
                result = await self.file_bug_from_error(issue)
                if result:
                    bugs_filed += 1

        self._last_scan_time = scan_start
        scan_result = {
            "scan_number": self._scan_count,
            "timestamp": scan_start.isoformat(),
            "log_errors_found": len(log_errors),
            "import_failures": len(import_failures),
            "bugs_filed": bugs_filed,
        }
        self._history.append(scan_result)

        logger.info(
            "bug_scan_complete",
            scan_number=self._scan_count,
            log_errors=len(log_errors),
            import_failures=len(import_failures),
            bugs_filed=bugs_filed,
        )

        return scan_result

    # ── Background Loop ──────────────────────────────────────────

    async def run_loop(self, interval_minutes: int = 30):
        """Background loop: scan for bugs every N minutes."""
        self._running = True
        logger.info("bug_scanner_started", interval=f"{interval_minutes}min")

        # Initial delay to let system stabilize
        await asyncio.sleep(60)

        while self._running:
            try:
                await self.run_scan()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("bug_scanner_loop_error", error=str(e))
                await asyncio.sleep(60)

        self._running = False

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "bugs_filed": self._bugs_filed,
            "last_scan": self._last_scan_time.isoformat() if self._last_scan_time else None,
            "seen_errors": len(self._seen_errors),
            "recent_scans": self._history[-10:],
        }


# Module-level singleton
bug_scanner = BugScanner()
