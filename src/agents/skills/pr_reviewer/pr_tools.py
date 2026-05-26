"""
PR Reviewer Skill: GitHub PR Tools

GitHub API tools for the PR Reviewer agent:
  - Fetch PR details and diffs
  - Post review comments
  - Approve or request changes
  - List open PRs needing review
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(component="pr_reviewer.pr_tools")


class PRTools:
    """GitHub API tools for PR review operations."""

    def __init__(self):
        try:
            from config.settings import get_settings
            settings = get_settings()
            self._pat = settings.github_pat
            self._repo = settings.github_repo
        except Exception:
            self._pat = os.getenv("GITHUB_PAT", "")
            self._repo = os.getenv("GITHUB_REPO", "anshu10sep/selfevolve")

        self._base_url = f"https://api.github.com/repos/{self._repo}"
        self._headers = {
            "Authorization": f"Bearer {self._pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── Read Operations ────────────────────────────────────────────

    async def get_pr(self, pr_number: int) -> Optional[dict]:
        """Get PR details."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/pulls/{pr_number}",
                headers=self._headers,
            )
        if r.status_code == 200:
            data = r.json()
            return {
                "number": data["number"],
                "title": data["title"],
                "body": data.get("body", ""),
                "state": data["state"],
                "branch": data["head"]["ref"],
                "base": data["base"]["ref"],
                "user": data["user"]["login"],
                "created_at": data["created_at"],
                "changed_files": data.get("changed_files", 0),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0),
            }
        return None

    async def get_pr_files(self, pr_number: int) -> list[dict]:
        """Get list of files changed in a PR."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/pulls/{pr_number}/files",
                headers=self._headers,
            )
        if r.status_code == 200:
            return [
                {
                    "filename": f["filename"],
                    "status": f["status"],  # added, modified, removed
                    "additions": f["additions"],
                    "deletions": f["deletions"],
                    "patch": f.get("patch", ""),
                }
                for f in r.json()
            ]
        return []

    async def get_pr_diff(self, pr_number: int) -> str:
        """Get the full diff for a PR."""
        headers = {**self._headers, "Accept": "application/vnd.github.diff"}
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/pulls/{pr_number}",
                headers=headers,
            )
        return r.text if r.status_code == 200 else ""

    async def list_open_prs(self) -> list[dict]:
        """List all open PRs."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._base_url}/pulls?state=open",
                headers=self._headers,
            )
        if r.status_code == 200:
            return [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "branch": pr["head"]["ref"],
                    "user": pr["user"]["login"],
                    "created_at": pr["created_at"],
                }
                for pr in r.json()
            ]
        return []

    async def _get_authenticated_user(self) -> str:
        """Get the login name of the authenticated GitHub user (PAT owner).

        Cached after first call to avoid repeated API requests.
        """
        if hasattr(self, "_cached_login") and self._cached_login:
            return self._cached_login

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.github.com/user",
                    headers=self._headers,
                )
            if r.status_code == 200:
                self._cached_login = r.json().get("login", "")
                return self._cached_login
        except Exception as e:
            logger.debug("get_authenticated_user_failed", error=str(e))

        self._cached_login = ""
        return ""

    async def _has_our_review(self, pr_number: int, my_login: str) -> bool:
        """Check if we've already reviewed a PR (via formal review OR comment).

        Checks two sources:
          1. GitHub formal reviews from our user
          2. Issue comments containing our review signature
        """
        # ── Check 1: Formal GitHub reviews ────────────────────────
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self._base_url}/pulls/{pr_number}/reviews",
                    headers=self._headers,
                )
            if r.status_code == 200:
                for rv in r.json():
                    reviewer = rv.get("user", {}).get("login", "").lower()
                    # Match our login, or common bot names
                    if reviewer and (
                        reviewer == my_login.lower()
                        or "jarvis" in reviewer
                        or "bot" in reviewer
                    ):
                        return True
        except Exception as e:
            logger.debug("review_check_failed", pr=pr_number, error=str(e))

        # ── Check 2: Comment-based reviews (fallback path) ────────
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self._base_url}/issues/{pr_number}/comments",
                    headers=self._headers,
                )
            if r.status_code == 200:
                for comment in r.json():
                    body = comment.get("body", "")
                    commenter = comment.get("user", {}).get("login", "").lower()
                    # Our review signature from code_review.py to_markdown()
                    if "Reviewed by PR Reviewer Agent" in body:
                        return True
                    # Our user posted a review-like comment
                    if commenter == my_login.lower() and "Code Review:" in body:
                        return True
        except Exception as e:
            logger.debug("comment_check_failed", pr=pr_number, error=str(e))

        return False

    async def list_unreviewed_prs(self) -> list[dict]:
        """List PRs that haven't been reviewed yet by our system.

        Checks both formal GitHub reviews and comment-based reviews
        to avoid re-reviewing PRs that were already processed.
        """
        prs = await self.list_open_prs()
        my_login = await self._get_authenticated_user()
        unreviewed = []

        for pr in prs:
            if await self._has_our_review(pr["number"], my_login):
                continue  # Already reviewed — skip
            unreviewed.append(pr)

        return unreviewed

    # ── Write Operations ───────────────────────────────────────────

    async def post_review(
        self,
        pr_number: int,
        body: str,
        event: str = "COMMENT",  # APPROVE, REQUEST_CHANGES, COMMENT
        comments: list[dict] = None,
    ) -> Optional[dict]:
        """
        Post a review on a PR.

        Args:
            pr_number: PR number
            body: Review body text
            event: APPROVE, REQUEST_CHANGES, or COMMENT
            comments: List of inline comments: [{"path": "file.py", "line": 10, "body": "..."}]
        """
        payload = {
            "body": body,
            "event": event,
        }

        if comments:
            # GitHub requires commit_id for inline comments
            pr = await self.get_pr(pr_number)
            if pr:
                async with httpx.AsyncClient() as client:
                    r = await client.get(
                        f"{self._base_url}/pulls/{pr_number}",
                        headers=self._headers,
                    )
                if r.status_code == 200:
                    payload["commit_id"] = r.json()["head"]["sha"]
                    payload["comments"] = comments

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/pulls/{pr_number}/reviews",
                json=payload,
                headers=self._headers,
            )

        if r.status_code == 200:
            review = r.json()
            logger.info("review_posted", pr=pr_number, event=event, review_id=review["id"])
            return {
                "review_id": review["id"],
                "state": review["state"],
                "url": review["html_url"],
            }
        else:
            logger.error("review_post_failed", pr=pr_number, status=r.status_code,
                         body=r.text[:300])
            return None

    async def post_comment(self, pr_number: int, body: str) -> Optional[dict]:
        """Post a simple comment on a PR (not a review)."""
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/issues/{pr_number}/comments",
                json={"body": body},
                headers=self._headers,
            )
        if r.status_code == 201:
            return {"id": r.json()["id"], "url": r.json()["html_url"]}
        return None

    async def add_labels(self, pr_number: int, labels: list[str]) -> bool:
        """Add labels to a PR."""
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base_url}/issues/{pr_number}/labels",
                json={"labels": labels},
                headers=self._headers,
            )
        return r.status_code == 200


# Module-level singleton
pr_tools = PRTools()
