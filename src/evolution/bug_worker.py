"""
Bug Worker — Autonomous Bug/Task Processor

Runs as a background loop. Picks up OPEN bugs from the tracker,
uses Gemini to generate code fixes, commits to a feature branch,
creates a PR on GitHub, and updates the bug status.

This is what makes Jarvis truly self-evolving: bugs and FRs filed
via /fr get worked on automatically.
"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(component="bug_worker")

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Priority order for bug severity
SEVERITY_PRIORITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


class BugWorker:
    """Picks up bugs → generates code → commits → creates PR."""

    def __init__(self):
        self._running = False
        self._processing = False
        self._processed_count = 0
        self._max_per_cycle = 2  # Max bugs to process per cycle
        self._history: list[dict] = []

    async def process_next_bug(self) -> Optional[dict]:
        """Pick the highest-priority OPEN bug and work on it."""
        if self._processing:
            logger.info("bug_worker_busy", message="Already processing a bug")
            return None

        self._processing = True
        try:
            from persistence.db import get_open_bugs_sorted, update_bug

            # Get OPEN bugs sorted by severity from DB
            open_bugs = get_open_bugs_sorted()

            if not open_bugs:
                logger.info("bug_worker_idle", message="No open bugs")
                return None

            bug = open_bugs[0]
            bug_id = bug["id"]
            bug_title = bug.get("title", "Untitled")

            logger.info("bug_worker_starting", bug_id=bug_id[:8], title=bug_title[:50])

            # Mark as IN_PROGRESS in DB
            update_bug(bug_id, status="IN_PROGRESS",
                       started_at=datetime.now(timezone.utc))

            # Notify via Telegram
            try:
                from integrations.telegram_bot import send_alert
                await send_alert(
                    f"🔨 *Working on Bug*\n\n"
                    f"[{bug.get('severity', '?')}] `{bug_title[:60]}`\n"
                    f"Source: {bug.get('source', 'manual')}\n"
                    f"Status: IN_PROGRESS"
                )
            except Exception:
                pass

            # Use Gemini to plan and generate code
            result = await self._generate_fix(bug)

            if result.get("success"):
                # Run full pipeline: pre-submit → PR → AI review
                from agents.skills.pr_reviewer.review_pipeline import review_pipeline
                from agents.skills.jarvis.github_ops import GitHubOps

                github = GitHubOps()
                pipeline_result = await review_pipeline.presubmit_and_create_pr(
                    bug=bug,
                    files_created=result.get("files_created", []),
                    github_ops=github,
                )

                # Check if blocked by pre-submit
                if pipeline_result.get("blocked"):
                    update_bug(bug_id, status="OPEN",
                               worker_error=pipeline_result.get("reason", "Pre-submit failed"))
                    logger.warning("bug_blocked_presubmit", bug_id=bug_id[:8],
                                   reason=pipeline_result.get("reason"))
                    return {"bug_id": bug_id, "status": "BLOCKED", "reason": pipeline_result.get("reason")}

                # PR was created (and possibly reviewed)
                pr_info = pipeline_result.get("pr")
                pr_url_val = pr_info.get("url") if pr_info else None
                review_verdict = (pipeline_result.get("review", {}) or {}).get("verdict", "N/A")

                update_bug(bug_id, status="RESOLVED",
                           resolved_at=datetime.now(timezone.utc),
                           pr_url=pr_url_val)

                self._processed_count += 1
                self._history.append({
                    "bug_id": bug_id[:8],
                    "title": bug_title[:60],
                    "status": "RESOLVED",
                    "pr_url": pr_url_val,
                    "review": review_verdict,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                # Notify success
                try:
                    pr_url = pr_url_val or "no PR"
                    await send_alert(
                        f"✅ *Bug Resolved*\n\n"
                        f"`{bug_title[:60]}`\n"
                        f"Files: {len(result.get('files_created', []))}\n"
                        f"PR: {pr_url}\n"
                        f"Review: {review_verdict}"
                    )
                except Exception:
                    pass

                logger.info("bug_resolved", bug_id=bug_id[:8], pr=pr_info, review=review_verdict)
                return {"bug_id": bug_id, "status": "RESOLVED", "pr": pr_info, "review": review_verdict}

            else:
                update_bug(bug_id, status="OPEN",
                           worker_error=result.get("error", "Unknown"))
                logger.warning("bug_fix_failed", bug_id=bug_id[:8], error=result.get("error"))
                return {"bug_id": bug_id, "status": "FAILED", "error": result.get("error")}

        except Exception as e:
            logger.error("bug_worker_error", error=str(e))
            return {"status": "ERROR", "error": str(e)}
        finally:
            self._processing = False

    async def _generate_fix(self, bug: dict) -> dict:
        """Use Gemini to generate code that fixes the bug."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from config.settings import get_settings
            settings = get_settings()

            llm = ChatGoogleGenerativeAI(
                model=settings.efficient_model,
                google_api_key=settings.gemini_api_key,
                temperature=0.2,
            )

            bug_title = bug.get("title", "")
            bug_desc = bug.get("description", bug_title)

            # Get current agent structure for context
            agent_dirs = []
            skills_root = os.path.join(SRC_ROOT, "agents", "skills")
            if os.path.exists(skills_root):
                for d in sorted(os.listdir(skills_root)):
                    full = os.path.join(skills_root, d)
                    if os.path.isdir(full) and d != "__pycache__":
                        py_files = [
                            f for f in os.listdir(full)
                            if f.endswith(".py") and f != "__init__.py"
                        ]
                        agent_dirs.append(f"{d}: {', '.join(py_files) if py_files else '(no skills)'}")

            context = "\n".join(f"  {a}" for a in agent_dirs)

            response = await llm.ainvoke(
                f"You are a Python developer for the SelfEvolve autonomous trading system.\n\n"
                f"BUG/TASK: {bug_title}\n"
                f"DESCRIPTION: {bug_desc}\n\n"
                f"CURRENT AGENT STRUCTURE:\n{context}\n\n"
                f"PROJECT ROOT: {SRC_ROOT}\n"
                f"Skills directory: {skills_root}\n\n"
                f"Generate the code to fix this bug/task.\n\n"
                f"For EACH file you need to create or modify, output in this format:\n"
                f"===FILE: relative/path/to/file.py===\n"
                f"<complete file contents>\n"
                f"===END_FILE===\n\n"
                f"Be thorough — generate complete, working Python files.\n"
                f"Focus on the skills directory (agents/skills/<agent_name>/).\n"
                f"Create meaningful skills with docstrings and proper structure."
            )

            from core.llm_utils import extract_text
            content = extract_text(response.content)

            # Parse files from response
            files_created = []
            parts = content.split("===FILE:")
            for part in parts[1:]:  # Skip text before first ===FILE:
                if "===END_FILE===" not in part:
                    continue
                header, rest = part.split("===", 1)
                filepath = header.strip().strip("=").strip()
                file_content = rest.replace("END_FILE===", "").strip()

                # Clean up markdown code blocks if present
                if file_content.startswith("```"):
                    lines = file_content.split("\n")
                    # Remove first line (```python) and last line (```)
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    file_content = "\n".join(lines)

                # Resolve path
                if not os.path.isabs(filepath):
                    filepath = os.path.join(SRC_ROOT, filepath)

                # Create directories if needed
                os.makedirs(os.path.dirname(filepath), exist_ok=True)

                # Write file
                with open(filepath, "w") as f:
                    f.write(file_content)

                rel_path = os.path.relpath(filepath, SRC_ROOT)
                files_created.append(rel_path)
                logger.info("bug_worker_file_created", file=rel_path)

            if files_created:
                return {"success": True, "files_created": files_created}
            else:
                return {"success": False, "error": "No files generated by Gemini"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _create_pr(self, bug: dict, result: dict) -> Optional[dict]:
        """Create a git branch, commit, push, and open a PR."""
        try:
            from agents.skills.jarvis.github_ops import GitHubOps
            github = GitHubOps()

            bug_id = bug["id"][:8]
            bug_title = bug.get("title", "fix")[:40]
            safe_title = "".join(c if c.isalnum() or c in "-_" else "-" for c in bug_title.lower()).strip("-")
            timestamp = datetime.now().strftime("%m%d-%H%M")
            branch = f"fix/{safe_title}-{timestamp}"

            files = result.get("files_created", [])
            files_list = "\n".join(f"- `{f}`" for f in files)

            pr_body = (
                f"## Bug Fix: {bug.get('title', '?')}\n\n"
                f"**Source:** {bug.get('source', 'manual')}\n"
                f"**Severity:** {bug.get('severity', '?')}\n"
                f"**Bug ID:** `{bug_id}`\n\n"
                f"### Files Changed\n{files_list}\n\n"
                f"---\n"
                f"_Automatically generated by Jarvis Bug Worker_"
            )

            pr_result = await github.evolution_commit_and_pr(
                branch_name=branch,
                files=[os.path.join(SRC_ROOT, f) for f in files],
                commit_message=f"[BugWorker] {bug.get('severity', 'FIX')}: {bug.get('title', 'fix')[:60]}",
                pr_title=f"[{bug.get('severity', 'FIX')}] {bug.get('title', 'Bug fix')[:70]}",
                pr_body=pr_body,
            )

            return pr_result

        except Exception as e:
            logger.error("pr_creation_failed", error=str(e))
            # Still count as resolved even if PR fails — code was written
            return {"url": None, "error": str(e)}

    async def run_loop(self, interval_minutes: int = 30):
        """Background loop: process bugs every N minutes."""
        self._running = True
        logger.info("bug_worker_started", interval=f"{interval_minutes}min")

        while self._running:
            try:
                processed = 0
                while processed < self._max_per_cycle:
                    result = await self.process_next_bug()
                    if not result or result.get("status") in ("FAILED", "ERROR", None):
                        break
                    processed += 1

                if processed > 0:
                    logger.info("bug_worker_cycle_done", processed=processed)

                await asyncio.sleep(interval_minutes * 60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("bug_worker_loop_error", error=str(e))
                await asyncio.sleep(60)

        self._running = False

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "processing": self._processing,
            "total_processed": self._processed_count,
            "recent": self._history[-10:],
        }


# Module-level singleton
bug_worker = BugWorker()
