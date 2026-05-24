"""
Jarvis Skill: GitHub Operations

Enables Jarvis to create branches, commit code, push to remote,
and open Pull Requests on GitHub for autonomous code evolution.
"""

from __future__ import annotations

import os
import subprocess
import json
from datetime import datetime, timezone
from typing import Optional, List

import structlog
import httpx

logger = structlog.get_logger(component="jarvis.github_ops")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


class GitHubOps:
    """Git and GitHub operations for autonomous code evolution."""

    def __init__(self, repo_path: str = REPO_ROOT):
        self.repo_path = repo_path
        self._github_pat: Optional[str] = os.getenv("GITHUB_PAT")
        self._github_repo: str = os.getenv("GITHUB_REPO", "anshu10sep/selfevolve")

    def _run_git(self, *args: str) -> tuple[int, str, str]:
        """Run a git command and return (returncode, stdout, stderr)."""
        result = subprocess.run(
            ["git"] + list(args),
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    # ── Branch Operations ─────────────────────────────────────────

    def create_branch(self, branch_name: str, from_branch: str = "main") -> bool:
        """Create a new feature branch from the specified base."""
        # Fetch latest
        self._run_git("fetch", "origin")
        # Create and checkout
        code, out, err = self._run_git("checkout", "-b", branch_name, f"origin/{from_branch}")
        if code != 0:
            logger.error("branch_create_failed", branch=branch_name, error=err)
            return False
        logger.info("branch_created", branch=branch_name, from_branch=from_branch)
        return True

    def checkout_branch(self, branch_name: str) -> bool:
        """Switch to an existing branch."""
        code, _, err = self._run_git("checkout", branch_name)
        return code == 0

    def current_branch(self) -> str:
        """Get the current branch name."""
        _, out, _ = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        return out

    def list_branches(self) -> List[str]:
        """List all local branches."""
        _, out, _ = self._run_git("branch", "--list")
        return [b.strip().lstrip("* ") for b in out.split("\n") if b.strip()]

    # ── Commit Operations ─────────────────────────────────────────

    def stage_files(self, file_paths: List[str]) -> bool:
        """Stage specific files for commit."""
        code, _, err = self._run_git("add", *file_paths)
        if code != 0:
            logger.error("stage_failed", files=file_paths, error=err)
            return False
        return True

    def stage_all(self) -> bool:
        """Stage all changes."""
        code, _, _ = self._run_git("add", "-A")
        return code == 0

    def commit(self, message: str, author: str = "Jarvis <jarvis@selfevolve.ai>") -> bool:
        """Create a commit with the given message."""
        code, out, err = self._run_git(
            "commit", "-m", message, f"--author={author}"
        )
        if code != 0:
            logger.error("commit_failed", error=err)
            return False
        logger.info("commit_created", message=message[:80])
        return True

    def get_diff_summary(self) -> str:
        """Get a summary of staged changes."""
        _, out, _ = self._run_git("diff", "--cached", "--stat")
        return out

    # ── Push Operations ───────────────────────────────────────────

    def push(self, branch: Optional[str] = None) -> bool:
        """Push current branch to origin."""
        branch = branch or self.current_branch()
        code, _, err = self._run_git("push", "-u", "origin", branch)
        if code != 0:
            logger.error("push_failed", branch=branch, error=err)
            return False
        logger.info("push_success", branch=branch)
        return True

    # ── Pull Request Operations ───────────────────────────────────

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> Optional[dict]:
        """Create a Pull Request on GitHub via the REST API."""
        if not self._github_pat:
            logger.error("github_pat_missing", message="Set GITHUB_PAT in .env")
            return None

        url = f"https://api.github.com/repos/{self._github_repo}/pulls"
        headers = {
            "Authorization": f"Bearer {self._github_pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 201:
            pr_data = response.json()
            logger.info(
                "pr_created",
                number=pr_data["number"],
                url=pr_data["html_url"],
            )
            return {
                "number": pr_data["number"],
                "url": pr_data["html_url"],
                "state": pr_data["state"],
            }
        else:
            logger.error(
                "pr_create_failed",
                status=response.status_code,
                body=response.text[:500],
            )
            return None

    async def list_open_prs(self) -> List[dict]:
        """List all open PRs on the repository."""
        if not self._github_pat:
            return []

        url = f"https://api.github.com/repos/{self._github_repo}/pulls?state=open"
        headers = {
            "Authorization": f"Bearer {self._github_pat}",
            "Accept": "application/vnd.github+json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code == 200:
            return [
                {"number": pr["number"], "title": pr["title"], "branch": pr["head"]["ref"]}
                for pr in response.json()
            ]
        return []

    # ── Full Evolution Workflow ────────────────────────────────────

    async def evolution_commit_and_pr(
        self,
        branch_name: str,
        files: List[str],
        commit_message: str,
        pr_title: str,
        pr_body: str,
    ) -> Optional[dict]:
        """
        Full evolution workflow:
        1. Create feature branch
        2. Stage files
        3. Commit
        4. Push
        5. Open PR
        """
        # 1. Create branch
        if not self.create_branch(branch_name):
            return None

        # 2. Stage
        if not self.stage_files(files):
            return None

        # 3. Commit
        if not self.commit(commit_message):
            return None

        # 4. Push
        if not self.push(branch_name):
            return None

        # 5. PR
        pr = await self.create_pull_request(pr_title, pr_body, branch_name)

        # Return to main
        self.checkout_branch("main")

        return pr
