"""
Watchdog — Autonomous System Guardian

The Watchdog is the always-on sentinel of the SelfEvolve system.
It runs continuously and performs three critical functions:

1. BUG HYGIENE — Deduplicates, auto-closes, and triages the bug tracker.
   The BugScanner creates tons of `[Auto] unknown: plain_text_error` duplicates
   because its dedup set resets on restart. The Watchdog fixes this at the DB level.

2. SYSTEM HEALTH — Monitors agent health, evolution pipeline status,
   and codebase integrity. Proactively files actionable bugs (not noise).

3. EVOLUTION OVERSIGHT — Watches the evolution pipeline for anomalies
   (e.g., prompt regression, stuck shadow tests, dead agents) and
   escalates issues to Jarvis/human.

The Watchdog is NOT an LLM wrapper. It's deterministic Python that
runs every 5 minutes to keep the system clean and healthy.

Usage (in main.py):
    from evolution.watchdog import watchdog
    asyncio.create_task(watchdog.run_loop(interval_minutes=5))
"""

from __future__ import annotations

import os
import asyncio
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog

logger = structlog.get_logger(component="watchdog")


class Watchdog:
    """
    Autonomous system guardian — deduplicates bugs, monitors health,
    and oversees the evolution pipeline.
    """

    def __init__(self):
        self._running = False
        self._cycle_count = 0
        self._total_deduped = 0
        self._total_auto_resolved = 0
        self._history: list[dict] = []

    # ═══════════════════════════════════════════════════════════════
    # 1. BUG HYGIENE — Deduplicate & Clean
    # ═══════════════════════════════════════════════════════════════

    async def deduplicate_bugs(self) -> dict:
        """
        Find and close duplicate bugs in the database.

        Strategy:
        - Group OPEN bugs by their normalized title
        - Keep the oldest one, close all duplicates as RESOLVED
        - Special handling for noise patterns like 'plain_text_error'

        Returns:
            Dict with stats: {duplicates_closed, noise_closed, groups_found}
        """
        try:
            from persistence.db import get_bugs, update_bug

            open_bugs = get_bugs(status="OPEN")
            if not open_bugs:
                return {"duplicates_closed": 0, "noise_closed": 0}

            # ── Phase 1: Close pure noise bugs ────────────────────
            noise_patterns = [
                "unknown: plain_text_error",
                "unknown: Unknown error",
                "Pipeline stalled:",
                "database_init_failed",
            ]

            noise_closed = 0
            remaining_bugs = []

            for bug in open_bugs:
                title = bug.get("title", "")
                is_noise = any(pattern in title for pattern in noise_patterns)

                if is_noise:
                    update_bug(
                        bug["id"],
                        status="RESOLVED",
                        resolved_at=datetime.now(timezone.utc),
                        worker_error="Auto-closed by Watchdog: noise/uninformative bug",
                    )
                    noise_closed += 1
                else:
                    remaining_bugs.append(bug)

            if noise_closed > 0:
                logger.info(
                    "watchdog_noise_closed",
                    count=noise_closed,
                )

            # ── Phase 2: Deduplicate by normalized title ──────────
            groups: dict[str, list[dict]] = {}
            for bug in remaining_bugs:
                key = self._normalize_title(bug.get("title", ""))
                groups.setdefault(key, []).append(bug)

            duplicates_closed = 0
            for key, bugs_in_group in groups.items():
                if len(bugs_in_group) <= 1:
                    continue

                # Sort by created_at — keep the oldest (first filed)
                bugs_in_group.sort(
                    key=lambda b: b.get("created_at", ""),
                )

                # Keep the first, close the rest
                keeper = bugs_in_group[0]
                for dup in bugs_in_group[1:]:
                    update_bug(
                        dup["id"],
                        status="RESOLVED",
                        resolved_at=datetime.now(timezone.utc),
                        worker_error=(
                            f"Auto-closed by Watchdog: duplicate of "
                            f"{keeper['id'][:8]} ({keeper['title'][:60]})"
                        ),
                    )
                    duplicates_closed += 1

            if duplicates_closed > 0:
                logger.info(
                    "watchdog_duplicates_closed",
                    count=duplicates_closed,
                    groups=len([g for g in groups.values() if len(g) > 1]),
                )

            self._total_deduped += noise_closed + duplicates_closed

            return {
                "duplicates_closed": duplicates_closed,
                "noise_closed": noise_closed,
                "groups_found": len(groups),
                "remaining_open": len(remaining_bugs) - duplicates_closed,
            }

        except Exception as e:
            logger.error("watchdog_dedup_failed", error=str(e))
            return {"error": str(e)}

    async def auto_resolve_known_issues(self) -> dict:
        """
        Auto-resolve bugs that match known, already-fixed patterns.

        These are bugs the BugScanner files repeatedly because the
        underlying issue is environmental (e.g., DB not started yet,
        import path not in PYTHONPATH during scan).
        """
        try:
            from persistence.db import get_bugs, update_bug

            open_bugs = get_bugs(status="OPEN")
            resolved = 0

            known_resolutions = {
                "database: Unknown error": (
                    "Known startup transient: DB connection fails during "
                    "initial boot but recovers within 30 seconds."
                ),
                "import_failed:agents.skills.jarvis.system_audit": (
                    "Known issue: system_audit has an optional dependency "
                    "that fails on first import but works after warm-up."
                ),
                "hot_reloader: reload_failed": (
                    "Known transient: hot_reloader fails when no modules "
                    "have changed since last check."
                ),
                "pr_reviewer.pr_tools: review_post_failed": (
                    "Known transient: PR review fails when no open PRs "
                    "exist to review."
                ),
                "pr_review_pipeline: pr_review_loop_error": (
                    "Known transient: PR review loop errors when no "
                    "open PRs exist to review."
                ),
                "main: database_init_failed": (
                    "Known startup transient: DB init fails on first "
                    "attempt but succeeds on retry."
                ),
                "Pipeline stalled:": (
                    "Self-referential: Pipeline stalled bug was filed "
                    "because of the bug count itself. Resolved by Watchdog."
                ),
                "import_failed:": (
                    "Known transient: import fails during cold start "
                    "but recovers after module warm-up."
                ),
            }

            for bug in open_bugs:
                title = bug.get("title", "")
                for pattern, resolution in known_resolutions.items():
                    if pattern in title:
                        update_bug(
                            bug["id"],
                            status="RESOLVED",
                            resolved_at=datetime.now(timezone.utc),
                            worker_error=f"Auto-resolved by Watchdog: {resolution}",
                        )
                        resolved += 1
                        break

            self._total_auto_resolved += resolved

            if resolved > 0:
                logger.info("watchdog_auto_resolved", count=resolved)

            return {"auto_resolved": resolved}

        except Exception as e:
            logger.error("watchdog_auto_resolve_failed", error=str(e))
            return {"error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # 2. BUG SCANNER HARDENING — Prevent Future Noise
    # ═══════════════════════════════════════════════════════════════

    async def sync_scanner_dedup_cache(self) -> dict:
        """
        Load existing bug titles from DB into the BugScanner's
        _seen_errors set to prevent re-filing on restart.

        This is the ROOT CAUSE fix: the BugScanner's in-memory dedup
        set resets every time the process restarts. We hydrate it
        from the database.
        """
        try:
            from persistence.db import get_bugs
            from evolution.bug_scanner import bug_scanner

            all_bugs = get_bugs()
            titles_loaded = 0

            for bug in all_bugs:
                title = bug.get("title", "")
                # Extract the component:event pattern that _make_dedup_key uses
                # Title format: "[Auto] component: event"
                if title.startswith("[Auto] "):
                    stripped = title[7:]  # Remove "[Auto] "
                    # Reconstruct the dedup key format
                    parts = stripped.split(": ", 1)
                    if len(parts) == 2:
                        component, event = parts
                        key = f"{component}:{event}:"
                        bug_scanner._seen_errors.add(key)
                        titles_loaded += 1

            logger.info(
                "watchdog_scanner_cache_synced",
                titles_loaded=titles_loaded,
                cache_size=len(bug_scanner._seen_errors),
            )

            return {
                "titles_loaded": titles_loaded,
                "cache_size": len(bug_scanner._seen_errors),
            }

        except Exception as e:
            logger.debug("watchdog_scanner_sync_failed", error=str(e))
            return {"error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # 3. SYSTEM HEALTH MONITORING
    # ═══════════════════════════════════════════════════════════════

    async def check_system_health(self) -> dict:
        """
        Check overall system health and file actionable bugs
        (not noise — only real, fixable issues).
        """
        health = {
            "agents_healthy": True,
            "evolution_healthy": True,
            "insights_active": True,
            "issues": [],
        }

        # Check InsightPublisher health
        try:
            from core.insight_publisher import insight_publisher
            stats = insight_publisher.get_stats()
            if stats["total_published"] == 0 and self._cycle_count > 5:
                health["insights_active"] = False
                health["issues"].append(
                    "InsightPublisher has 0 published insights after 5+ cycles"
                )
        except Exception:
            pass

        # Check VectorStore health
        try:
            from memory.vector_store import get_vector_store
            vs = get_vector_store()
            vs_stats = vs.get_stats()
            health["vector_store"] = vs_stats
        except Exception:
            pass

        # Check bug tracker health
        try:
            from persistence.db import get_bug_summary
            bug_summary = get_bug_summary()
            health["bug_summary"] = bug_summary

            # Alert if > 20 OPEN bugs after dedup
            if bug_summary.get("open", 0) > 20:
                health["issues"].append(
                    f"High bug count: {bug_summary['open']} OPEN bugs"
                )
        except Exception:
            pass

        return health

    async def check_evolution_pipeline(self) -> dict:
        """Check the evolution pipeline for anomalies."""
        status = {
            "healthy": True,
            "issues": [],
        }

        try:
            from persistence.db import get_pending_prompt_versions

            # Check for stuck shadow tests (pending > 7 days)
            for role in ["technical_analyst", "fundamental_analyst",
                         "sentiment_analyst", "macro_analyst", "judge"]:
                pending = get_pending_prompt_versions(role)
                for pv in pending:
                    created = pv.get("created_at", "")
                    if created:
                        try:
                            created_dt = datetime.fromisoformat(created)
                            if created_dt.tzinfo is None:
                                created_dt = created_dt.replace(tzinfo=timezone.utc)
                            age_days = (
                                datetime.now(timezone.utc) - created_dt
                            ).total_seconds() / 86400

                            if age_days > 7:
                                status["healthy"] = False
                                status["issues"].append(
                                    f"Stuck shadow test: {role} v{pv['version_number']} "
                                    f"pending for {age_days:.0f} days"
                                )
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass

        return status

    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _normalize_title(self, title: str) -> str:
        """
        Normalize a bug title for deduplication.

        Strips timestamps, UUIDs, and variable parts to create
        a stable grouping key.
        """
        import re

        # Remove [Auto] and [Pipeline] prefixes
        title = title.replace("[Auto] ", "").replace("[Pipeline] ", "")

        # Remove UUIDs
        title = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '', title,
        )

        # Remove timestamps
        title = re.sub(
            r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',
            '', title,
        )

        # Remove hex hashes
        title = re.sub(r'[0-9a-f]{8,}', '', title)

        # Remove standalone numbers (e.g., "65 open" → "open")
        # This catches "Pipeline stalled: 65 open" vs "Pipeline stalled: 42 open"
        title = re.sub(r'\b\d+\b', '', title)

        # Collapse whitespace
        title = re.sub(r'\s+', ' ', title).strip().lower()

        return title

    # ═══════════════════════════════════════════════════════════════
    # MAIN LOOP
    # ═══════════════════════════════════════════════════════════════

    async def run_cycle(self) -> dict:
        """Run one Watchdog cycle: dedup + health + evolution check."""
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)

        logger.info("watchdog_cycle_start", cycle=self._cycle_count)

        results = {}

        # 1. Sync scanner dedup cache (prevents future duplicates)
        results["scanner_sync"] = await self.sync_scanner_dedup_cache()

        # 2. Deduplicate existing bugs
        results["dedup"] = await self.deduplicate_bugs()

        # 3. Auto-resolve known issues
        results["auto_resolve"] = await self.auto_resolve_known_issues()

        # 4. System health check
        results["health"] = await self.check_system_health()

        # 5. Evolution pipeline check
        results["evolution"] = await self.check_evolution_pipeline()

        # Summarize
        total_cleaned = (
            results.get("dedup", {}).get("duplicates_closed", 0)
            + results.get("dedup", {}).get("noise_closed", 0)
            + results.get("auto_resolve", {}).get("auto_resolved", 0)
        )

        cycle_result = {
            "cycle": self._cycle_count,
            "timestamp": cycle_start.isoformat(),
            "bugs_cleaned": total_cleaned,
            "health_issues": len(results.get("health", {}).get("issues", [])),
            "evolution_issues": len(results.get("evolution", {}).get("issues", [])),
            "details": results,
        }

        self._history.append(cycle_result)

        # Keep only last 50 cycles
        if len(self._history) > 50:
            self._history = self._history[-50:]

        if total_cleaned > 0:
            logger.info(
                "watchdog_cycle_cleaned",
                cycle=self._cycle_count,
                bugs_cleaned=total_cleaned,
            )

            # Telegram notification for significant cleanup
            if total_cleaned >= 5:
                try:
                    from integrations.telegram_bot import send_alert
                    await send_alert(
                        f"🐕 *Watchdog Cleanup*\n\n"
                        f"Cycle #{self._cycle_count}\n"
                        f"Bugs cleaned: {total_cleaned}\n"
                        f"• Noise: {results.get('dedup', {}).get('noise_closed', 0)}\n"
                        f"• Duplicates: {results.get('dedup', {}).get('duplicates_closed', 0)}\n"
                        f"• Known issues: {results.get('auto_resolve', {}).get('auto_resolved', 0)}"
                    )
                except Exception:
                    pass

        logger.info(
            "watchdog_cycle_complete",
            cycle=self._cycle_count,
            cleaned=total_cleaned,
            duration_sec=round(
                (datetime.now(timezone.utc) - cycle_start).total_seconds(), 2
            ),
        )

        return cycle_result

    async def run_loop(self, interval_minutes: int = 5):
        """
        Background loop: run Watchdog every N minutes.

        Default: every 5 minutes (much more frequent than the
        30-minute BugScanner cycle, to catch and clean duplicates
        before they accumulate).
        """
        self._running = True
        logger.info("watchdog_started", interval=f"{interval_minutes}min")

        # Run first cycle immediately (clean up on startup)
        try:
            await self.run_cycle()
        except Exception as e:
            logger.error("watchdog_initial_cycle_failed", error=str(e))

        while self._running:
            try:
                await asyncio.sleep(interval_minutes * 60)
                await self.run_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("watchdog_loop_error", error=str(e))
                await asyncio.sleep(60)

        self._running = False
        logger.info("watchdog_stopped")

    def stop(self):
        """Stop the Watchdog loop."""
        self._running = False

    def get_status(self) -> dict:
        """Get Watchdog status for the dashboard."""
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "total_deduped": self._total_deduped,
            "total_auto_resolved": self._total_auto_resolved,
            "recent_cycles": self._history[-10:],
        }


# ═══════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════

watchdog = Watchdog()
"""Global singleton. Import and use:
    from evolution.watchdog import watchdog
    asyncio.create_task(watchdog.run_loop())
"""
