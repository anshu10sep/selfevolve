"""
Engineer Agent — Deep Diagnosis for Stuck Bugs

Dispatched by the TPM Tracker when a bug is stuck:
  1. Reads the bug from the database
  2. Examines relevant source files and error logs
  3. Uses Gemini to perform root-cause analysis
  4. Either generates a fix directly or provides detailed diagnosis
  5. Updates the bug record with findings

Budget: max 5 diagnoses per cycle, 10 per day.
"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(component="engineer_agent")

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.abspath(os.path.join(SRC_ROOT, ".."))
LOG_DIR = os.path.join(REPO_ROOT, "logs")


class EngineerAgent:
    """Deep-diagnosis engineer dispatched by the TPM for stuck bugs."""

    def __init__(self):
        self._diagnoses_today = 0
        self._max_daily = 10
        self._history: list[dict] = []

    def _read_recent_errors(self, max_lines: int = 50) -> str:
        """Read the most recent error log entries for context."""
        error_log = os.path.join(LOG_DIR, "jarvis-error.log")
        main_log = os.path.join(LOG_DIR, "jarvis.log")

        lines = []
        for log_path in [error_log, main_log]:
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r") as f:
                        all_lines = f.readlines()
                        # Get last N lines that contain ERROR
                        error_lines = [l.strip() for l in all_lines if "error" in l.lower()]
                        lines.extend(error_lines[-max_lines:])
                except Exception:
                    pass
        return "\n".join(lines[-max_lines:])

    def _read_source_file(self, filepath: str) -> str:
        """Read a source file for context, with path resolution."""
        if not os.path.isabs(filepath):
            filepath = os.path.join(SRC_ROOT, filepath)
        if not os.path.exists(filepath):
            return f"(file not found: {filepath})"
        try:
            with open(filepath, "r") as f:
                content = f.read()
            return content[:5000]  # Cap at 5K chars
        except Exception as e:
            return f"(read error: {e})"

    def _find_related_files(self, bug_title: str) -> list[str]:
        """Guess which files are related to a bug based on its title."""
        related = []
        title_lower = bug_title.lower()

        # Map keywords to files
        keyword_map = {
            "github": "agents/skills/jarvis/github_ops.py",
            "import": "evolution/bug_worker.py",
            "telegram": "integrations/telegram_bot.py",
            "database": "persistence/db.py",
            "trading": "broker/alpaca_client.py",
            "crypto": "integrations/crypto_data.py",
            "llm": "core/llm_utils.py",
            "healer": "evolution/self_healer.py",
            "scanner": "evolution/bug_scanner.py",
            "evolution": "evolution/self_evolution.py",
            "dashboard": "dashboard/api/main.py",
            "config": "config/settings.py",
        }

        for keyword, filepath in keyword_map.items():
            if keyword in title_lower:
                full_path = os.path.join(SRC_ROOT, filepath)
                if os.path.exists(full_path):
                    related.append(filepath)

        # Always include the file mentioned in worker_error if present
        return related[:3]  # Max 3 files for context

    async def diagnose_bug(self, bug_id: str) -> dict:
        """
        Perform deep diagnosis on a stuck bug.

        1. Fetch bug details from DB
        2. Gather context (error logs, related source files)
        3. Ask Gemini for root-cause analysis
        4. Apply fix if possible, or update bug with diagnosis
        """
        if self._diagnoses_today >= self._max_daily:
            logger.warning("engineer_daily_limit", limit=self._max_daily)
            return {"status": "DAILY_LIMIT", "message": f"Max {self._max_daily} diagnoses/day"}

        logger.info("engineer_diagnosing", bug_id=bug_id[:8])

        try:
            from persistence.db import get_bugs, update_bug
            # Fetch the bug
            all_bugs = get_bugs()
            bug = next((b for b in all_bugs if b["id"] == bug_id), None)
            if not bug:
                return {"status": "NOT_FOUND", "bug_id": bug_id}

            bug_title = bug.get("title", "")
            bug_desc = bug.get("description", "")
            worker_error = bug.get("worker_error", "")

            # Gather context
            error_logs = self._read_recent_errors(max_lines=30)
            related_files = self._find_related_files(bug_title)
            file_contents = {}
            for rf in related_files:
                file_contents[rf] = self._read_source_file(rf)

            # Build context for LLM
            files_context = "\n\n".join(
                f"=== {fp} ===\n{content[:2000]}"
                for fp, content in file_contents.items()
            )

            # Ask Gemini for diagnosis
            from langchain_google_genai import ChatGoogleGenerativeAI
            from config.settings import get_settings
            from core.llm_utils import extract_text

            settings = get_settings()
            llm = ChatGoogleGenerativeAI(
                model=settings.efficient_model,
                google_api_key=settings.gemini_api_key,
                temperature=0.1,
            )

            prompt = (
                f"You are a senior engineer debugging an autonomous trading system.\n\n"
                f"STUCK BUG:\n"
                f"  Title: {bug_title}\n"
                f"  Description: {bug_desc[:500]}\n"
                f"  Worker Error: {worker_error}\n"
                f"  Severity: {bug.get('severity', '?')}\n"
                f"  Created: {bug.get('created_at', '?')}\n\n"
                f"RECENT ERROR LOGS:\n{error_logs[:2000]}\n\n"
                f"RELATED SOURCE FILES:\n{files_context[:4000]}\n\n"
                f"Provide your diagnosis in this format:\n"
                f"ROOT_CAUSE: one sentence\n"
                f"FIX_APPROACH: one sentence describing how to fix it\n"
                f"COMPLEXITY: SIMPLE/MODERATE/COMPLEX\n"
                f"CAN_AUTO_FIX: YES/NO\n"
                f"RECOMMENDED_ACTION: description of next steps"
            )

            response = await llm.ainvoke(prompt)
            diagnosis = extract_text(response.content)

            # Parse diagnosis
            parsed = {"raw": diagnosis}
            for line in diagnosis.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip().upper().replace(" ", "_")
                    if key in ("ROOT_CAUSE", "FIX_APPROACH", "COMPLEXITY",
                               "CAN_AUTO_FIX", "RECOMMENDED_ACTION"):
                        parsed[key.lower()] = val.strip()

            # Update the bug with diagnosis
            update_bug(
                bug_id,
                description=(
                    f"{bug_desc}\n\n--- Engineer Diagnosis ---\n"
                    f"Time: {datetime.now(timezone.utc).isoformat()}\n"
                    f"Root Cause: {parsed.get('root_cause', 'Unknown')}\n"
                    f"Fix: {parsed.get('fix_approach', 'Unknown')}\n"
                    f"Complexity: {parsed.get('complexity', '?')}\n"
                    f"Action: {parsed.get('recommended_action', 'Manual review needed')}"
                ),
            )

            # If it's a simple auto-fix, attempt it via the bug worker
            if parsed.get("can_auto_fix", "").upper() == "YES":
                # Reset to OPEN so bug_worker picks it up with the new context
                update_bug(bug_id, status="OPEN", worker_error=None, started_at=None)
                logger.info("engineer_reset_for_retry", bug_id=bug_id[:8])

            self._diagnoses_today += 1
            result = {
                "status": "DIAGNOSED",
                "bug_id": bug_id,
                "diagnosis": parsed,
                "related_files": related_files,
            }
            self._history.append({
                "bug_id": bug_id[:8],
                "title": bug_title[:60],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "root_cause": parsed.get("root_cause", "?")[:100],
                "can_auto_fix": parsed.get("can_auto_fix", "NO"),
            })

            # Notify
            try:
                from integrations.telegram_bot import send_alert
                await send_alert(
                    f"🔬 *Engineer Diagnosis*\n\n"
                    f"Bug: `{bug_title[:50]}`\n"
                    f"Root Cause: {parsed.get('root_cause', '?')[:100]}\n"
                    f"Complexity: {parsed.get('complexity', '?')}\n"
                    f"Auto-fix: {parsed.get('can_auto_fix', 'NO')}"
                )
            except Exception:
                pass

            logger.info("engineer_diagnosis_complete", bug_id=bug_id[:8],
                        root_cause=parsed.get("root_cause", "?")[:80])
            return result

        except Exception as e:
            logger.error("engineer_diagnosis_failed", bug_id=bug_id[:8], error=str(e))
            return {"status": "ERROR", "bug_id": bug_id, "error": str(e)}

    def get_status(self) -> dict:
        return {
            "diagnoses_today": self._diagnoses_today,
            "max_daily": self._max_daily,
            "recent": self._history[-10:],
        }


# Module-level singleton
engineer_agent = EngineerAgent()
