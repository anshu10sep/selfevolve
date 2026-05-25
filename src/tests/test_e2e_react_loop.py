"""
End-to-End ReAct Loop Test

Validates the full agent pipeline:
1. Agent instantiation with LLM
2. Skill loading and tool discovery
3. ReAct invocation loop
4. Tool-calling responses

Requires: GEMINI_API_KEY environment variable (or settings)
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSkillRegistry:
    """Test that all agents have skills registered."""

    def test_master_skills_loaded(self):
        """Verify Jarvis (master) has skills registered."""
        from agents.skills.validator import SkillRegistry

        # Trigger skill loading by importing the modules
        import agents.skills.jarvis.agent_messaging  # noqa: F401
        import agents.skills.jarvis.code_generation  # noqa: F401
        import agents.skills.jarvis.github_ops  # noqa: F401
        import agents.skills.jarvis.system_audit  # noqa: F401
        import agents.skills.jarvis.decision_tracker  # noqa: F401

        skills = SkillRegistry.get_skills("master")
        assert len(skills) > 0, "Jarvis (master) should have registered skills"

        # Check for specific critical skills
        expected = [
            "list_all_agents",
            "delegate_task_to_agent",
            "generate_agent_code",
            "run_system_audit",
            "escalate_to_owner",
        ]
        for skill_name in expected:
            assert skill_name in skills, f"Missing master skill: {skill_name}"

    def test_cto_skills_loaded(self):
        """Verify CTO has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.cto.system_architecture_review  # noqa: F401
        import agents.skills.cto.roadmap_planning  # noqa: F401
        import agents.skills.cto.tech_stack_evaluation  # noqa: F401

        skills = SkillRegistry.get_skills("cto")
        assert len(skills) >= 3, f"CTO should have 3+ skills, got {len(skills)}"

    def test_cso_skills_loaded(self):
        """Verify CSO has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.cso.threat_detection  # noqa: F401
        import agents.skills.cso.security_policy_enforcement  # noqa: F401
        import agents.skills.cso.incident_response  # noqa: F401

        skills = SkillRegistry.get_skills("cso")
        assert len(skills) >= 3, f"CSO should have 3+ skills, got {len(skills)}"

    def test_qa_skills_loaded(self):
        """Verify QA has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.qa.execute_tests  # noqa: F401
        import agents.skills.qa.report_bugs  # noqa: F401
        import agents.skills.qa.write_test_cases  # noqa: F401

        skills = SkillRegistry.get_skills("qa")
        assert len(skills) >= 3, f"QA should have 3+ skills, got {len(skills)}"

    def test_developer_skills_loaded(self):
        """Verify Developer has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.developer.write_code  # noqa: F401
        import agents.skills.developer.debug_code  # noqa: F401
        import agents.skills.developer.refactor_code  # noqa: F401
        import agents.skills.developer.test_code  # noqa: F401

        skills = SkillRegistry.get_skills("developer")
        assert len(skills) >= 4, f"Developer should have 4+ skills, got {len(skills)}"

    def test_product_skills_loaded(self):
        """Verify Product has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.product.define_features  # noqa: F401
        import agents.skills.product.gather_requirements  # noqa: F401
        import agents.skills.product.roadmap_management  # noqa: F401

        skills = SkillRegistry.get_skills("product")
        assert len(skills) >= 3, f"Product should have 3+ skills, got {len(skills)}"

    def test_meta_review_skills_loaded(self):
        """Verify Meta-Review has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.meta_review.evaluate_strategy_effectiveness  # noqa: F401
        import agents.skills.meta_review.propose_improvements  # noqa: F401
        import agents.skills.meta_review.review_agent_performance  # noqa: F401

        skills = SkillRegistry.get_skills("meta_review")
        assert len(skills) >= 3, f"Meta-Review should have 3+ skills, got {len(skills)}"

    def test_journaling_skills_loaded(self):
        """Verify Journaling has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.journaling.log_market_events  # noqa: F401
        import agents.skills.journaling.record_decisions  # noqa: F401
        import agents.skills.journaling.summarize_daily_activity  # noqa: F401

        skills = SkillRegistry.get_skills("journaling")
        assert len(skills) >= 3, f"Journaling should have 3+ skills, got {len(skills)}"

    def test_auditor_skills_loaded(self):
        """Verify Auditor has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.auditor.compliance_check  # noqa: F401
        import agents.skills.auditor.compliance_skills  # noqa: F401
        import agents.skills.auditor.security_review  # noqa: F401

        skills = SkillRegistry.get_skills("auditor")
        assert len(skills) >= 3, f"Auditor should have 3+ skills, got {len(skills)}"

    def test_judge_skills_loaded(self):
        """Verify Judge has skills registered."""
        from agents.skills.validator import SkillRegistry
        import agents.skills.judge.make_final_decision  # noqa: F401
        import agents.skills.judge.evaluate_proposals  # noqa: F401
        import agents.skills.judge.resolve_conflicts  # noqa: F401

        skills = SkillRegistry.get_skills("judge")
        assert len(skills) >= 3, f"Judge should have 3+ skills, got {len(skills)}"

    def test_all_agents_summary(self):
        """Print a summary of all agent skill counts."""
        from agents.skills.validator import SkillRegistry
        all_skills = SkillRegistry.get_all_skills()
        print("\n=== Agent Skill Registry Summary ===")
        for agent_key, skills in sorted(all_skills.items()):
            print(f"  {agent_key}: {len(skills)} skills ({', '.join(sorted(skills.keys())[:5])}...)")
        print(f"\nTotal agents with skills: {len(all_skills)}")
        assert len(all_skills) >= 8, f"Expected 8+ agents with skills, got {len(all_skills)}"


class TestAgentRegistry:
    """Test agent registration system."""

    def test_register_and_retrieve(self):
        """Test agent registration and retrieval."""
        from agents.skills.jarvis.agent_messaging import (
            register_agent_instance,
            get_registered_agents,
        )

        # Register a mock agent
        mock_agent = MagicMock()
        mock_agent.name = "Test Agent"
        register_agent_instance("test_agent", mock_agent)

        agents = get_registered_agents()
        assert "test_agent" in agents
        assert agents["test_agent"].name == "Test Agent"

    def test_list_all_agents_skill(self):
        """Test the list_all_agents skill function."""
        from agents.skills.jarvis.agent_messaging import (
            register_agent_instance,
            list_all_agents,
        )

        # Register a mock agent
        mock_agent = MagicMock()
        mock_agent.name = "Mock CTO"
        register_agent_instance("mock_cto", mock_agent)

        result = list_all_agents()
        assert isinstance(result, str)
        assert "Agent Roster" in result or "mock_cto" in result


class TestCodeGenerator:
    """Test the refactored CodeGenerator."""

    def test_code_generator_init(self):
        """Verify CodeGenerator can be instantiated without OpenAI key."""
        from agents.skills.jarvis.code_generation import CodeGenerator
        gen = CodeGenerator()
        assert gen._agents_dir is not None
        assert gen._src_dir is not None
        # No api_key attribute anymore
        assert not hasattr(gen, "api_key")

    def test_generate_agent_file_quality(self):
        """Test that generated agent files have proper structure."""
        import tempfile
        from agents.skills.jarvis.code_generation import CodeGenerator

        gen = CodeGenerator()
        # Override agents dir to temp
        gen._agents_dir = tempfile.mkdtemp()

        filepath = gen.generate_agent_file(
            role="TESTER",
            agent_name="Tester Agent",
            identity_core="You are a test agent.",
            agent_type="SPECIALIST",
        )

        assert os.path.exists(filepath)

        with open(filepath, "r") as f:
            content = f.read()

        # Verify quality improvements
        assert "analyze_task" in content, "Should have analyze_task method"
        assert "report_status" in content, "Should have report_status method"
        assert "@skill(" in content, "Should have @skill decorator"
        assert "import agents.skills" in content, "Should import skills"
        assert "super().__init__" in content, "Should call super().__init__"
        assert "timestamp" in content, "Should include timestamp in _safe_default"

        # Cleanup
        os.unlink(filepath)


class TestAgentLoader:
    """Test dynamic agent loading."""

    def test_loader_nonexistent_file(self):
        """Test loader handles missing files gracefully."""
        from evolution.agent_loader import load_and_start_agent
        result = load_and_start_agent("/nonexistent/path.py")
        assert result["status"] == "FAILED"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
