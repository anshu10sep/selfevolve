"""
PR Reviewer Skill: Code Review

Uses Gemini to perform intelligent code review on PR diffs.
Analyzes code changes for:
  - Bugs and logic errors
  - Security vulnerabilities
  - Performance issues
  - Missing error handling
  - Architecture violations
  - Test coverage gaps

Returns structured review with line-specific comments.
"""

from __future__ import annotations

import os
from typing import Optional
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(component="pr_reviewer.code_review")


@dataclass
class ReviewComment:
    """A single review comment on a specific file/line."""
    file: str
    line: Optional[int]
    severity: str        # CRITICAL, WARNING, SUGGESTION, PRAISE
    category: str        # bug, security, performance, style, architecture
    message: str

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
        }


@dataclass
class CodeReviewReport:
    """Full code review report."""
    verdict: str          # APPROVE, REQUEST_CHANGES, COMMENT
    summary: str
    comments: list[ReviewComment]
    risk_score: float     # 0.0 (safe) to 1.0 (high risk)

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == "CRITICAL")

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.comments if c.severity == "WARNING")

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "summary": self.summary,
            "risk_score": self.risk_score,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "comments": [c.to_dict() for c in self.comments],
        }

    def to_markdown(self) -> str:
        """Render as GitHub review body."""
        icon = {"APPROVE": "✅", "REQUEST_CHANGES": "❌", "COMMENT": "💬"}.get(self.verdict, "📝")
        lines = [
            f"## {icon} Code Review: {self.verdict}",
            "",
            f"**Risk Score:** {'🟢' if self.risk_score < 0.3 else '🟡' if self.risk_score < 0.7 else '🔴'} {self.risk_score:.1f}/1.0",
            f"**Critical:** {self.critical_count} | **Warnings:** {self.warning_count} | **Total Comments:** {len(self.comments)}",
            "",
            f"### Summary",
            self.summary,
            "",
        ]

        if self.comments:
            lines.append("### Comments")
            for c in self.comments:
                sev_icon = {"CRITICAL": "🔴", "WARNING": "🟡", "SUGGESTION": "💡", "PRAISE": "👍"}.get(c.severity, "📝")
                loc = f"`{c.file}:{c.line}`" if c.line else f"`{c.file}`"
                lines.append(f"- {sev_icon} **[{c.severity}]** {loc} — {c.message}")

        lines.append("")
        lines.append("---")
        lines.append("_Reviewed by PR Reviewer Agent 🤖_")

        return "\n".join(lines)


class CodeReviewer:
    """AI-powered code reviewer using Gemini."""

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if not self._llm:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from config.settings import get_settings
            settings = get_settings()
            self._llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=settings.gemini_api_key,
                temperature=0.1,
            )
        return self._llm

    async def review_files(
        self,
        file_paths: list[str],
        pr_title: str = "",
        pr_body: str = "",
    ) -> CodeReviewReport:
        """
        Review a set of files using AI.

        Args:
            file_paths: Absolute paths to changed files
            pr_title: PR title for context
            pr_body: PR body for context

        Returns:
            CodeReviewReport with verdict and comments
        """
        # Read file contents
        file_contents = {}
        for fp in file_paths:
            if os.path.isfile(fp) and fp.endswith(".py"):
                try:
                    with open(fp) as f:
                        file_contents[os.path.basename(fp)] = f.read()
                except Exception:
                    pass

        if not file_contents:
            return CodeReviewReport(
                verdict="APPROVE",
                summary="No Python files to review.",
                comments=[],
                risk_score=0.0,
            )

        # Build the review prompt
        files_text = ""
        for name, content in file_contents.items():
            files_text += f"\n{'='*60}\n📄 {name}\n{'='*60}\n{content}\n"

        prompt = f"""You are an expert code reviewer for the SelfEvolve autonomous trading system.

PR Title: {pr_title}
PR Description: {pr_body}

Review the following code changes. For each issue found, output in this exact format:
COMMENT: <file>:<line_number>|<severity>|<category>|<message>

Severity levels: CRITICAL, WARNING, SUGGESTION, PRAISE
Categories: bug, security, performance, style, architecture, test

After all comments, provide:
VERDICT: <APPROVE or REQUEST_CHANGES or COMMENT>
RISK_SCORE: <0.0 to 1.0>
SUMMARY: <one paragraph summary>

Focus on:
1. Bugs and logic errors (off-by-one, null checks, race conditions)
2. Security (hardcoded secrets, injection, unsafe operations)
3. Error handling (bare except, missing error paths)
4. Architecture (does it fit the agent pattern?)
5. Missing docstrings or unclear code
6. Praise excellent code too!

Be thorough but fair. Not everything is a bug.

{files_text}"""

        try:
            llm = self._get_llm()
            response = await llm.ainvoke(prompt)
            return self._parse_review(response.content, list(file_contents.keys()))
        except Exception as e:
            logger.error("review_failed", error=str(e))
            return CodeReviewReport(
                verdict="COMMENT",
                summary=f"Review failed: {str(e)[:100]}",
                comments=[],
                risk_score=0.5,
            )

    def _parse_review(self, response: str, files: list[str]) -> CodeReviewReport:
        """Parse Gemini's review response into structured report."""
        import re

        comments = []
        verdict = "COMMENT"
        risk_score = 0.3
        summary = "Review completed."

        for line in response.split("\n"):
            line = line.strip()

            # Parse comments
            if line.startswith("COMMENT:"):
                try:
                    rest = line[8:].strip()
                    parts = rest.split("|", 3)
                    if len(parts) >= 4:
                        file_loc = parts[0].strip()
                        severity = parts[1].strip().upper()
                        category = parts[2].strip().lower()
                        message = parts[3].strip()

                        # Parse file:line
                        file_name = file_loc
                        line_num = None
                        if ":" in file_loc:
                            fname, lnum = file_loc.rsplit(":", 1)
                            file_name = fname
                            try:
                                line_num = int(lnum)
                            except ValueError:
                                pass

                        if severity in ("CRITICAL", "WARNING", "SUGGESTION", "PRAISE"):
                            comments.append(ReviewComment(
                                file=file_name,
                                line=line_num,
                                severity=severity,
                                category=category,
                                message=message,
                            ))
                except Exception:
                    pass

            # Parse verdict
            elif line.startswith("VERDICT:"):
                v = line[8:].strip().upper()
                if v in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
                    verdict = v

            # Parse risk score
            elif line.startswith("RISK_SCORE:"):
                try:
                    risk_score = float(line[11:].strip())
                    risk_score = max(0.0, min(1.0, risk_score))
                except ValueError:
                    pass

            # Parse summary
            elif line.startswith("SUMMARY:"):
                summary = line[8:].strip()

        # Auto-escalate if critical issues found
        critical_count = sum(1 for c in comments if c.severity == "CRITICAL")
        if critical_count > 0 and verdict == "APPROVE":
            verdict = "REQUEST_CHANGES"

        return CodeReviewReport(
            verdict=verdict,
            summary=summary,
            comments=comments,
            risk_score=risk_score,
        )


# Module-level singleton
code_reviewer = CodeReviewer()
