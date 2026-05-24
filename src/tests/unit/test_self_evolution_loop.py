"""
Regression tests for the self-evolution loop.

These tests guard against the 4 root causes that killed Jarvis's
autonomous self-improvement overnight on 2026-05-24:

1. Broken __init__.py (stray '===' from Gemini output parser)
2. Bug worker ignoring stuck IN_PROGRESS bugs
3. continuous_evolution crashing on import errors
4. No syntax validation of auto-generated code

Run with:
    cd /home/agentx/self-evolving
    PYTHONPATH=src pytest src/tests/unit/test_self_evolution_loop.py -v
"""

import os
import sys
import py_compile
import tempfile
import uuid
from datetime import datetime, timezone, timedelta

import pytest

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ══════════════════════════════════════════════════════════════════
# TEST GROUP 1: Syntax / Import Integrity
# ══════════════════════════════════════════════════════════════════

class TestCodeIntegrity:
    """Prevent broken syntax from killing the evolution loop."""

    def test_all_python_files_compile(self):
        """Every .py file under src/ must compile without SyntaxError.

        This catches stray '===' artifacts, unclosed strings, and other
        syntax errors introduced by the Bug Worker's Gemini output parser.
        """
        errors = []
        for root, dirs, files in os.walk(SRC_ROOT):
            # Skip __pycache__, .git, virtual envs
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "venv", ".venv", "node_modules")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                filepath = os.path.join(root, f)
                try:
                    py_compile.compile(filepath, doraise=True)
                except py_compile.PyCompileError as e:
                    rel = os.path.relpath(filepath, SRC_ROOT)
                    errors.append(f"{rel}: {e}")

        assert not errors, (
            f"{len(errors)} Python file(s) have syntax errors:\n"
            + "\n".join(errors)
        )

    def test_all_skill_packages_importable(self):
        """Every __init__.py under agents/skills/ must compile cleanly.

        This is the exact failure that killed the evolution loop:
        agents/skills/__init__.py had a stray '===' on line 5.
        """
        skills_root = os.path.join(SRC_ROOT, "agents", "skills")
        if not os.path.exists(skills_root):
            pytest.skip("agents/skills/ directory not found")

        errors = []
        for root, dirs, files in os.walk(skills_root):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            if "__init__.py" in files:
                init_path = os.path.join(root, "__init__.py")
                try:
                    py_compile.compile(init_path, doraise=True)
                except py_compile.PyCompileError as e:
                    rel = os.path.relpath(init_path, SRC_ROOT)
                    errors.append(f"{rel}: {e}")

        assert not errors, (
            f"{len(errors)} skill package __init__.py file(s) have syntax errors:\n"
            + "\n".join(errors)
        )

    def test_continuous_evolution_import_chain(self):
        """The full import chain used by _run_continuous_evolution must work.

        continuous_evolution imports SystemAuditor which traverses through
        agents.skills.__init__. If that __init__.py is broken, the entire
        6-hourly evolution cycle crashes silently.
        """
        # This import chain is what broke:
        # main.py -> agents.skills.jarvis.system_audit -> agents.skills.__init__
        try:
            from agents.skills.jarvis.system_audit import SystemAuditor
            auditor = SystemAuditor()
            # Just verify it instantiates — don't need to run audit
            assert auditor is not None
        except (SyntaxError, ImportError) as e:
            pytest.fail(
                f"Import chain for SystemAuditor broken: {e}\n"
                f"This means _run_continuous_evolution will crash every 6 hours."
            )

    def test_pr_reviewer_import_chain(self):
        """The PR reviewer import chain must work.

        The bug worker imports review_pipeline through agents.skills.
        If agents/skills/__init__.py is broken, bug worker can't create PRs.
        """
        try:
            from agents.skills.pr_reviewer.review_pipeline import review_pipeline
            assert review_pipeline is not None
        except SyntaxError as e:
            pytest.fail(
                f"SyntaxError in import chain for review_pipeline: {e}\n"
                f"This means the bug worker cannot create PRs for its fixes."
            )


# ══════════════════════════════════════════════════════════════════
# TEST GROUP 2: Bug Worker Stuck-Bug Recovery
# ══════════════════════════════════════════════════════════════════

class TestBugWorkerRecovery:
    """Prevent bugs from getting permanently stuck in IN_PROGRESS."""

    @pytest.fixture
    def test_db(self, tmp_path):
        """Create a fresh test database."""
        import importlib
        import persistence.db as db_module

        # Point to a temp DB
        test_db_path = str(tmp_path / "test_jarvis.db")
        original_url = db_module.DATABASE_URL
        original_engine = db_module.engine
        original_session = db_module.SessionLocal

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        test_engine = create_engine(
            f"sqlite:///{test_db_path}",
            connect_args={"check_same_thread": False},
        )
        test_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

        db_module.engine = test_engine
        db_module.SessionLocal = test_session
        db_module.Base.metadata.create_all(bind=test_engine)

        yield db_module

        # Restore originals
        db_module.engine = original_engine
        db_module.SessionLocal = original_session

    def test_get_open_bugs_sorted_excludes_resolved(self, test_db):
        """RESOLVED bugs must not appear in the bug worker's queue."""
        resolved_id = str(uuid.uuid4())
        open_id = str(uuid.uuid4())
        test_db.create_bug(id=resolved_id, title="Resolved bug",
                           severity="HIGH")
        test_db.create_bug(id=open_id, title="Open bug", severity="HIGH")
        test_db.update_bug(resolved_id, status="RESOLVED")

        open_bugs = test_db.get_open_bugs_sorted()

        # Only OPEN bugs should appear
        assert len(open_bugs) == 1
        assert open_bugs[0]["status"] == "OPEN"
        assert open_bugs[0]["title"] == "Open bug"

    def test_get_stuck_bugs_finds_errored_bugs(self, test_db):
        """Bugs with IN_PROGRESS status and worker_error should be found."""
        bug_id = str(uuid.uuid4())
        test_db.create_bug(id=bug_id, title="Stuck bug", severity="HIGH")
        test_db.update_bug(
            bug_id,
            status="IN_PROGRESS",
            worker_error="'list' object has no attribute 'split'",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        stuck = test_db.get_stuck_bugs(stuck_minutes=60)
        assert len(stuck) == 1
        assert stuck[0]["id"] == bug_id
        assert stuck[0]["status"] == "IN_PROGRESS"

    def test_get_stuck_bugs_ignores_recent(self, test_db):
        """IN_PROGRESS bugs without errors that started recently should NOT be stuck."""
        bug_id = str(uuid.uuid4())
        test_db.create_bug(id=bug_id, title="Working bug", severity="HIGH")
        test_db.update_bug(
            bug_id,
            status="IN_PROGRESS",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        stuck = test_db.get_stuck_bugs(stuck_minutes=60)
        assert len(stuck) == 0

    def test_reset_stuck_bugs_flips_to_open(self, test_db):
        """reset_stuck_bugs() must flip errored IN_PROGRESS bugs back to OPEN."""
        bug_id = str(uuid.uuid4())
        test_db.create_bug(id=bug_id, title="Stuck bug", severity="HIGH")
        test_db.update_bug(
            bug_id,
            status="IN_PROGRESS",
            worker_error="model not found",
            started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        # Verify it's stuck
        assert len(test_db.get_open_bugs_sorted()) == 0
        assert len(test_db.get_stuck_bugs(stuck_minutes=60)) == 1

        # Reset
        count = test_db.reset_stuck_bugs(stuck_minutes=60)
        assert count == 1

        # Now it should be OPEN and visible to the worker
        open_bugs = test_db.get_open_bugs_sorted()
        assert len(open_bugs) == 1
        assert open_bugs[0]["status"] == "OPEN"
        assert open_bugs[0]["worker_error"] is None

    def test_bug_worker_sees_reset_bugs(self, test_db):
        """After reset, the bug worker's get_open_bugs_sorted finds them."""
        # Create two bugs: one stuck with error, one already resolved
        stuck_id = str(uuid.uuid4())
        resolved_id = str(uuid.uuid4())

        test_db.create_bug(id=stuck_id, title="Stuck", severity="HIGH")
        test_db.update_bug(stuck_id, status="IN_PROGRESS",
                           worker_error="SyntaxError",
                           started_at=datetime.now(timezone.utc) - timedelta(hours=3))

        test_db.create_bug(id=resolved_id, title="Done", severity="LOW")
        test_db.update_bug(resolved_id, status="RESOLVED")

        # Before reset: no open bugs
        assert len(test_db.get_open_bugs_sorted()) == 0

        # Reset stuck bugs
        test_db.reset_stuck_bugs(stuck_minutes=60)

        # After reset: stuck bug is now open
        open_bugs = test_db.get_open_bugs_sorted()
        assert len(open_bugs) == 1
        assert open_bugs[0]["id"] == stuck_id
        assert open_bugs[0]["title"] == "Stuck"


# ══════════════════════════════════════════════════════════════════
# TEST GROUP 3: Bug Worker Output Validation
# ══════════════════════════════════════════════════════════════════

class TestBugWorkerOutputValidation:
    """Validate that the bug worker's file parser produces valid Python."""

    def test_file_parser_rejects_stray_delimiters(self):
        """The ===FILE: parser must not leave stray '===' in generated files.

        This is the root cause: Gemini's response included ===FILE:...===
        delimiters, and the parser left residual '===' in the output.
        """
        from evolution.bug_worker import parse_gemini_files

        # Simulate Gemini response with the delimiter format
        gemini_response = (
            "Here are the files:\n"
            "===FILE: agents/skills/test/__init__.py===\n"
            "from .test_skill import TestSkill\n"
            "\n"
            "__all__ = ['TestSkill']\n"
            "===END_FILE===\n"
        )

        files = parse_gemini_files(gemini_response)

        assert len(files) == 1
        filepath, content = files[0]

        # Must not have stray delimiters
        assert "===" not in content, (
            f"Stray '===' found in generated file {filepath}:\n{content}"
        )
        # Must compile
        try:
            compile(content, filepath, "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated file {filepath} has syntax error: {e}")

    def test_file_parser_handles_multiple_files(self):
        """Parser must correctly handle multiple files in one response."""
        from evolution.bug_worker import parse_gemini_files

        response = (
            "===FILE: a.py===\n"
            "x = 1\n"
            "===END_FILE===\n"
            "===FILE: b.py===\n"
            "y = 2\n"
            "===END_FILE===\n"
        )

        files = parse_gemini_files(response)
        assert len(files) == 2
        assert files[0][0] == "a.py"
        assert files[1][0] == "b.py"
        for _, content in files:
            assert "===" not in content


# ══════════════════════════════════════════════════════════════════
# TEST GROUP 4: Evolution Engine Smoke Tests
# ══════════════════════════════════════════════════════════════════

class TestEvolutionEngine:
    """Smoke tests for the self-evolution engine."""

    def test_evolution_engine_instantiates(self):
        """The evolution engine singleton must instantiate without errors."""
        from evolution.self_evolution import SelfEvolutionEngine
        engine = SelfEvolutionEngine()
        status = engine.get_status()
        assert "current_sha" in status
        assert "merge_count" in status
        assert "pending_restart" in status

    def test_evolution_engine_status_has_sha(self):
        """get_status() must return a valid-looking SHA."""
        from evolution.self_evolution import evolution_engine
        status = evolution_engine.get_status()
        sha = status["current_sha"]
        # SHA should be 8 chars hex or 'unknown'
        assert sha == "unknown" or (len(sha) == 8 and all(c in "0123456789abcdef" for c in sha))
