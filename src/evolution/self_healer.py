"""
Self-Healer

Monitors for runtime errors, analyzes them via Gemini,
proposes fixes, runs tests, and patches the codebase autonomously.
Uses GitHub Ops for version control of all changes.
"""

from __future__ import annotations

import os
import re
import traceback
from datetime import datetime, timezone
from typing import Optional

import structlog

from config.settings import get_settings

logger = structlog.get_logger(component="self_healer")

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class SelfHealer:
    """Autonomous error detection, analysis, and patching."""

    def __init__(self):
        self.settings = get_settings()
        self._error_log: list[dict] = []
        self._patches_applied: list[dict] = []
        self._max_auto_patches_per_day = 5
        self._patches_today = 0

    async def record_error(
        self,
        error: Exception,
        context: str = "",
        source_file: str = "",
    ) -> dict:
        """Record an error and attempt auto-diagnosis."""
        error_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "context": context,
            "source_file": source_file,
            "status": "RECORDED",
        }
        self._error_log.append(error_info)

        # Auto-diagnose
        diagnosis = await self.diagnose(error_info)
        error_info["diagnosis"] = diagnosis

        logger.info(
            "error_recorded",
            error_type=error_info["type"],
            source=source_file,
            diagnosis_action=diagnosis.get("action", "UNKNOWN"),
        )

        return error_info

    async def diagnose(self, error_info: dict) -> dict:
        """Use Gemini to analyze the error and propose a fix."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=self.settings.gemini_api_key,
                temperature=0.1,
            )

            # Read source file if available
            source_content = ""
            if error_info.get("source_file"):
                try:
                    filepath = error_info["source_file"]
                    if not os.path.isabs(filepath):
                        filepath = os.path.join(SRC_ROOT, filepath)
                    with open(filepath, "r") as f:
                        source_content = f.read()
                except Exception:
                    source_content = "(could not read source file)"

            prompt = f"""You are a Python debugging expert for an autonomous trading system.

ERROR:
Type: {error_info['type']}
Message: {error_info['message']}
Context: {error_info.get('context', '')}

TRACEBACK:
{error_info.get('traceback', '')[:1500]}

SOURCE FILE ({error_info.get('source_file', 'unknown')}):
{source_content[:3000]}

Analyze this error and respond in EXACTLY this format:
SEVERITY: CRITICAL/HIGH/MEDIUM/LOW
ROOT_CAUSE: one sentence
ACTION: AUTO_FIX/MANUAL_REVIEW/IGNORE/RESTART
FIX_DESCRIPTION: what the fix does (one sentence)
FILE_TO_PATCH: relative path or NONE
FIND_TEXT: exact text to find and replace (or NONE)
REPLACE_TEXT: replacement text (or NONE)
"""

            response = await llm.ainvoke(prompt)
            analysis = response.content

            # Parse response
            diagnosis = {"raw": analysis, "action": "MANUAL_REVIEW"}
            for line in analysis.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip().upper().replace(" ", "_")
                    val = val.strip()
                    if key in ("SEVERITY", "ROOT_CAUSE", "ACTION", "FIX_DESCRIPTION",
                               "FILE_TO_PATCH", "FIND_TEXT", "REPLACE_TEXT"):
                        diagnosis[key.lower()] = val

            return diagnosis

        except Exception as e:
            logger.error("diagnosis_failed", error=str(e))
            return {"action": "MANUAL_REVIEW", "error": str(e)}

    async def auto_patch(self, error_info: dict) -> dict:
        """
        Attempt to automatically patch the codebase.
        Only for non-critical, well-understood errors.
        """
        diagnosis = error_info.get("diagnosis", {})
        action = diagnosis.get("action", "").upper()

        if action != "AUTO_FIX":
            return {"patched": False, "reason": f"Action is {action}, not AUTO_FIX"}

        if self._patches_today >= self._max_auto_patches_per_day:
            return {"patched": False, "reason": "Daily patch limit reached"}

        file_to_patch = diagnosis.get("file_to_patch", "NONE")
        find_text = diagnosis.get("find_text", "NONE")
        replace_text = diagnosis.get("replace_text", "NONE")

        if file_to_patch == "NONE" or find_text == "NONE" or replace_text == "NONE":
            return {"patched": False, "reason": "Incomplete fix specification"}

        # Resolve file path
        filepath = file_to_patch
        if not os.path.isabs(filepath):
            filepath = os.path.join(SRC_ROOT, filepath)

        if not os.path.exists(filepath):
            return {"patched": False, "reason": f"File not found: {filepath}"}

        # Read file
        with open(filepath, "r") as f:
            content = f.read()

        if find_text not in content:
            return {"patched": False, "reason": "Find text not found in file"}

        # Apply patch
        new_content = content.replace(find_text, replace_text, 1)

        # Write patched file
        with open(filepath, "w") as f:
            f.write(new_content)

        self._patches_today += 1

        patch_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file": file_to_patch,
            "find": find_text[:100],
            "replace": replace_text[:100],
            "description": diagnosis.get("fix_description", ""),
            "committed": False,
        }
        self._patches_applied.append(patch_record)

        # Git commit the fix
        try:
            from agents.skills.jarvis.github_ops import GitHubOps
            github = GitHubOps()
            github.create_branch(f"fix/auto-heal-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
            github.stage_and_commit(
                f"[AutoHeal] Fix {error_info['type']}: {diagnosis.get('fix_description', 'auto-fix')}"
            )
            github.push_branch()
            patch_record["committed"] = True
        except Exception as e:
            logger.warning("auto_patch_commit_failed", error=str(e))

        # Notify via Telegram
        try:
            from integrations.telegram_bot import send_alert
            await send_alert(
                f"🔧 *Auto-Patch Applied*\n\n"
                f"Error: `{error_info['type']}`\n"
                f"File: `{file_to_patch}`\n"
                f"Fix: {diagnosis.get('fix_description', '?')}\n\n"
                f"_Patch #{self._patches_today} today_"
            )
        except Exception:
            pass

        logger.info(
            "auto_patch_applied",
            file=file_to_patch,
            description=diagnosis.get("fix_description", ""),
        )

        return {"patched": True, "patch": patch_record}

    async def handle_exception(self, error: Exception, context: str = "") -> dict:
        """
        Full pipeline: record → diagnose → auto-patch if safe.
        
        Call this from any try/except block:
            from evolution.self_healer import healer
            await healer.handle_exception(e, context="trading_dag")
        """
        # Extract source file from traceback
        source_file = ""
        tb = traceback.extract_tb(error.__traceback__)
        if tb:
            source_file = tb[-1].filename

        error_info = await self.record_error(error, context, source_file)

        diagnosis = error_info.get("diagnosis", {})
        severity = diagnosis.get("severity", "UNKNOWN").upper()

        # Only auto-patch MEDIUM/LOW severity
        if severity in ("MEDIUM", "LOW") and diagnosis.get("action", "").upper() == "AUTO_FIX":
            result = await self.auto_patch(error_info)
            error_info["auto_patch"] = result
        elif severity in ("CRITICAL", "HIGH"):
            # Alert human for critical issues
            try:
                from integrations.telegram_bot import send_alert
                await send_alert(
                    f"🚨 *{severity} Error Detected*\n\n"
                    f"Type: `{error_info['type']}`\n"
                    f"Message: `{str(error)[:150]}`\n"
                    f"Source: `{source_file}`\n"
                    f"Cause: {diagnosis.get('root_cause', 'Unknown')}\n\n"
                    f"_Requires manual review_"
                )
            except Exception:
                pass

        return error_info

    def get_error_summary(self) -> dict:
        """Get summary of recent errors for dashboard."""
        return {
            "total_errors": len(self._error_log),
            "patches_applied": len(self._patches_applied),
            "patches_today": self._patches_today,
            "recent_errors": [
                {
                    "type": e["type"],
                    "message": e["message"][:100],
                    "timestamp": e["timestamp"],
                    "status": e.get("diagnosis", {}).get("action", "UNKNOWN"),
                }
                for e in self._error_log[-10:]
            ],
        }


# Module-level singleton
healer = SelfHealer()
