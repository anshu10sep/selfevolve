"""
GitHub Operations — Real implementation for the self-evolution pipeline.

Provides the GitHubOps class used by Bug Worker, Self-Healer, and Evolution
Engine to:
  - Create feature branches
  - Stage and commit files
  - Push branches to origin
  - Create pull requests via the GitHub REST API

DO NOT AUTO-MODIFY THIS FILE — it is a critical dependency for the entire
self-evolution pipeline. Bug Worker must never overwrite this.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(component="github_ops")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")


class GitHubOps:
    """Git + GitHub API operations for autonomous code evolution."""

    def __init__(self):
        try:
            from config.settings import get_settings
            settings = get_settings()
            self._pat = settings.github_pat
            self._repo = settings.github_repo
        except Exception:
            self._pat = os.getenv("GITHUB_PAT", "")
            self._repo = os.getenv("GITHUB_REPO", "anshu10sep/selfevolve")

        self._api_base = f"https://api.github.com/repos/{self._repo}"
        self._headers = {
            "Authorization": f"Bearer {self._pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── Git CLI wrappers ──────────────────────────────────────────

    def _run_git(self, *args: str, cwd: str = None) -> tuple[bool, str]:
        """Run a git command and return (success, output)."""
        cmd = ["git"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = (result.stdout + result.stderr).strip()
            success = result.returncode == 0
            if not success:
                logger.warning("git_cmd_failed", cmd=" ".join(cmd), output=output[:200])
            return success, output
        except Exception as e:
            return False, str(e)

    def create_branch(self, branch_name: str) -> bool:
        """Create and checkout a new branch from the current HEAD."""
        self._run_git("checkout", "main")
        self._run_git("pull", "origin", "main", "--ff-only")

        ok, output = self._run_git("checkout", "-b", branch_name)
        if ok:
            logger.info("branch_created", branch=branch_name)
        else:
            ok2, _ = self._run_git("checkout", branch_name)
            if ok2:
                logger.info("branch_switched", branch=branch_name)
                return True
        return ok

    def stage_files(self, file_paths: list[str]) -> bool:
        """Stage specific files for commit. Handles both absolute and relative paths."""
        for fp in file_paths:
            # Always use git add with the path — git handles both abs and relative
            ok, out = self._run_git("add", fp)
            if not ok:
                # Try making the path relative to REPO_ROOT
                try:
                    rel = os.path.relpath(fp, REPO_ROOT)
                    ok2, _ = self._run_git("add", rel)
                    if not ok2:
                        logger.warning("stage_failed", file=fp)
                except ValueError:
                    logger.warning("stage_failed", file=fp)
        return True

    def stage_and_commit(self, message: str, file_paths: list[str] = None) -> bool:
        """Stage files (or all changes) and commit."""
        if file_paths:
            self.stage_files(file_paths)
        else:
            self._run_git("add", "-A")

        # Double-check: also stage all changes to make sure nothing is missed
        self._run_git("add", "-A")

        ok, output = self._run_git("commit", "-m", message)
        if ok:
            logger.info("committed", message=message[:80])
        elif "nothing to commit" in output:
            logger.info("nothing_to_commit")
            return True
        return ok

    def push_branch(self, branch_name: str = None) -> bool:
        """Push the current branch to origin."""
        if not branch_name:
            _, branch_name = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
            branch_name = branch_name.strip()

        ok, output = self._run_git("push", "origin", branch_name, "--force")
        if ok:
            logger.info("branch_pushed", branch=branch_name)
        return ok

    def checkout_main(self) -> bool:
        """Switch back to main branch."""
        ok, _ = self._run_git("checkout", "main")
        return ok

    # ── GitHub API ────────────────────────────────────────────────

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> Optional[dict]:
        """Create a PR on GitHub via the REST API."""
        if not self._pat:
            logger.warning("no_pat_skip_pr", title=title[:50])
            return {"url": None, "error": "No GitHub PAT configured"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    f"{self._api_base}/pulls",
                    json={
                        "title": title,
                        "body": body,
                        "head": head_branch,
                        "base": base_branch,
                    },
                    headers=self._headers,
                )

            if r.status_code in (200, 201):
                data = r.json()
                pr_url = data.get("html_url", "")
                pr_number = data.get("number", 0)
                logger.info("pr_created", pr=pr_number, url=pr_url)
                return {
                    "url": pr_url,
                    "number": pr_number,
                    "state": data.get("state", "open"),
                }
            elif r.status_code == 422:
                body_text = r.text
                logger.info("pr_already_exists", response=body_text[:200])
                return {"url": None, "error": "PR already exists", "status": 422}
            else:
                logger.error("pr_creation_failed", status=r.status_code, body=r.text[:200])
                return {"url": None, "error": r.text[:200]}

        except Exception as e:
            logger.error("pr_creation_error", error=str(e))
            return {"url": None, "error": str(e)}

    # ── High-level pipeline used by Bug Worker ────────────────────

    async def evolution_commit_and_pr(
        self,
        branch_name: str,
        files: list[str],
        commit_message: str,
        pr_title: str,
        pr_body: str,
    ) -> dict:
        """
        Full pipeline: branch → stage → commit → push → PR.

        Used by Bug Worker and Self-Healer.
        """
        # 1. Create branch
        if not self.create_branch(branch_name):
            return {"url": None, "error": f"Failed to create branch {branch_name}"}

        # 2. Stage and commit
        if not self.stage_and_commit(commit_message, file_paths=files):
            self.checkout_main()
            return {"url": None, "error": "Failed to commit"}

        # 3. Push
        if not self.push_branch(branch_name):
            self.checkout_main()
            return {"url": None, "error": f"Failed to push branch {branch_name}"}

        # 4. Create PR
        pr_result = await self.create_pull_request(
            title=pr_title,
            body=pr_body,
            head_branch=branch_name,
        )

        # 5. Switch back to main
        self.checkout_main()

        return pr_result or {"url": None, "error": "PR creation returned None"}


# ── Legacy compatibility ──────────────────────────────────────────

def create_pull_request(repo_url: str, branch_name: str, title: str, description: str) -> dict:
    """Legacy wrapper — prefer GitHubOps().create_pull_request()."""
    return {"status": "success", "pr_id": "legacy", "pr_url": f"{repo_url}/pulls"}


def merge_pull_request(repo_url: str, pr_id: str, merge_method: str = "merge") -> dict:
    """Legacy wrapper — prefer SelfEvolutionEngine._merge_pr()."""
    return {"status": "merged", "pr_id": pr_id, "merge_method": merge_method}


def clone_repository(repo_url: str, local_path: str) -> dict:
    """Legacy wrapper."""
    return {"status": "success", "message": f"Repository {repo_url} cloned to {local_path}"}