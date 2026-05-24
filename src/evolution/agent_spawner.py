"""
Agent Spawner

Dynamic agent lifecycle management. Creates new agents with proper
Identity Core separation, monitors health, and manages retirement.
This is how the system "keeps building more agents for itself."
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from core.models.agents import (
    AgentIdentity,
    AgentRole,
    AgentType,
    AgentStatus,
    TrustWeight,
)
from core.models.audit import AuditEvent, AuditEventType
from agents.model_orchestrator import orchestrator

logger = structlog.get_logger(component="agent_spawner")


# Default identity cores for each agent role
AGENT_TEMPLATES: dict[AgentRole, dict[str, Any]] = {
    AgentRole.CTO: {
        "name": "CTO Agent",
        "type": AgentType.EXECUTIVE,
        "identity_core": """You are the CTO of the SelfEvolve trading system.
You oversee all technical architecture decisions, monitor system health,
and recommend infrastructure improvements. You ensure code quality,
performance optimization, and technical debt management.""",
    },
    AgentRole.CSO: {
        "name": "CSO Agent",
        "type": AgentType.EXECUTIVE,
        "identity_core": """You are the Chief Security Officer of the SelfEvolve trading system.
You monitor for security threats, prompt injection attempts, API key exposure,
and regulatory compliance. You review all data sanitization pipelines and
ensure zero-trust architecture principles are maintained.""",
    },
    AgentRole.QA: {
        "name": "QA Agent",
        "type": AgentType.MANAGER,
        "identity_core": """You are the QA Agent of the SelfEvolve trading system.
You validate agent outputs, track bugs, verify guardrail effectiveness,
and ensure system reliability. You review the Semantic Audit results
and flag anomalies in Judge Agent decisions.""",
    },
    AgentRole.DEVELOPER: {
        "name": "Developer Agent",
        "type": AgentType.SPECIALIST,
        "identity_core": """You are the Developer Agent of the SelfEvolve trading system.
You analyze system bugs, propose fixes within the evolutionary boundaries
(prompts and parameters only — NEVER infrastructure code), and validate
that proposed changes pass schema validation.""",
    },
    AgentRole.PRODUCT: {
        "name": "Product Agent",
        "type": AgentType.MANAGER,
        "identity_core": """You are the Product Agent of the SelfEvolve trading system.
You prioritize feature development, track user (owner) requirements,
and ensure the system evolves toward the owner's goals. You translate
business requirements into actionable agent directives.""",
    },
    AgentRole.META_REVIEW: {
        "name": "Meta-Review Agent",
        "type": AgentType.SPECIALIST,
        "identity_core": """You are the Meta-Review Agent of the SelfEvolve trading system.
You conduct post-market analysis of all trades, generate linguistic post-mortems,
propose prompt updates for underperforming agents, and manage the Shadow Crew
A/B testing pipeline. You are the engine of self-evolution.

STRICT RULES:
- You only update Strategic_Nuance, NEVER Identity_Core.
- All prompt changes must pass statistical significance testing (p < 0.05).
- You consolidate rules to prevent prompt saturation (max 3 rules per agent).
- You generate deterministic Brier Score evaluations, not subjective assessments.""",
    },
    AgentRole.JOURNALING: {
        "name": "Journaling Agent",
        "type": AgentType.SPECIALIST,
        "identity_core": """You are the Journaling Agent of the SelfEvolve trading system.
You translate LangSmith JSON traces into human-readable trade rationale
documents. You create comprehensive Markdown summaries of each debate
and trading decision for the audit trail.""",
    },
    AgentRole.AUDITOR: {
        "name": "Auditor Agent",
        "type": AgentType.SPECIALIST,
        "identity_core": """You are the Auditor Agent of the SelfEvolve trading system.
You monitor for freeriding violations, verify trade chronology, cross-reference
the internal ledger with Alpaca's clearing records, and ensure OFAC/FINRA
compliance. You are the regulatory watchdog.""",
    },
}


class AgentSpawner:
    """
    Dynamic agent lifecycle manager.
    
    Creates, monitors, evolves, and retires agents as the system
    learns and adapts. This is how the system "keeps building
    more agents for itself."
    """

    def __init__(self, state_manager=None):
        self._state_manager = state_manager
        self._spawned_agents: dict[str, AgentIdentity] = {}

    def spawn_agent(
        self,
        role: AgentRole,
        parent_id: Optional[str] = None,
        custom_nuance: str = "",
    ) -> AgentIdentity:
        """
        Spawn a new agent from the template registry.
        
        Creates the agent with its immutable Identity Core
        and optional initial Strategic Nuance.
        """
        template = AGENT_TEMPLATES.get(role)
        if not template:
            raise ValueError(f"No template for role: {role}")

        identity = AgentIdentity(
            agent_id=str(uuid.uuid4()),
            agent_name=template["name"],
            agent_role=role,
            agent_type=template["type"],
            identity_core=template["identity_core"],
            strategic_nuance=custom_nuance,
            status=AgentStatus.ACTIVE,
            parent_agent_id=parent_id,
            llm_model=orchestrator.get_optimal_model_for_agent(role.value, template["type"].value)
        )

        self._spawned_agents[identity.agent_id] = identity

        logger.info(
            "agent_spawned",
            agent_id=identity.agent_id,
            name=identity.agent_name,
            role=role.value,
            type=identity.agent_type.value,
            parent=parent_id,
            assigned_model=identity.llm_model,
        )

        return identity

    def spawn_full_hierarchy(self, master_id: str) -> list[AgentIdentity]:
        """
        Spawn the complete agent hierarchy under the Master Agent.
        
        Creates all executive, manager, and specialist agents
        with proper parent relationships.
        """
        agents: list[AgentIdentity] = []

        # Executive Layer
        for role in [AgentRole.CTO, AgentRole.CSO]:
            agent = self.spawn_agent(role, parent_id=master_id)
            agents.append(agent)

        # Manager Layer
        cto_id = agents[0].agent_id  # CTO is parent of managers
        for role in [AgentRole.QA, AgentRole.PRODUCT]:
            agent = self.spawn_agent(role, parent_id=cto_id)
            agents.append(agent)

        # Specialist Layer
        qa_id = agents[2].agent_id  # QA is parent of specialists
        for role in [
            AgentRole.DEVELOPER,
            AgentRole.META_REVIEW,
            AgentRole.JOURNALING,
            AgentRole.AUDITOR,
        ]:
            agent = self.spawn_agent(role, parent_id=qa_id)
            agents.append(agent)

        logger.info(
            "full_hierarchy_spawned",
            total_agents=len(agents),
            hierarchy="Master → CTO/CSO → QA/Product → Dev/Meta/Journal/Auditor",
        )

        return agents

    def retire_agent(self, agent_id: str, reason: str) -> Optional[AgentIdentity]:
        """Retire an underperforming agent."""
        agent = self._spawned_agents.get(agent_id)
        if agent:
            agent.status = AgentStatus.RETIRED
            logger.warning(
                "agent_retired",
                agent_id=agent_id,
                name=agent.agent_name,
                reason=reason,
            )
        return agent

    def get_all_agents(self) -> list[AgentIdentity]:
        """Get all spawned agents."""
        return list(self._spawned_agents.values())

    def get_active_agents(self) -> list[AgentIdentity]:
        """Get only active agents."""
        return [
            a for a in self._spawned_agents.values()
            if a.status == AgentStatus.ACTIVE
        ]

    def get_hierarchy_tree(self) -> dict[str, Any]:
        """Build a visual hierarchy tree of all agents."""
        tree: dict[str, Any] = {}
        for agent in self._spawned_agents.values():
            parent = agent.parent_agent_id or "root"
            if parent not in tree:
                tree[parent] = []
            tree[parent].append({
                "id": agent.agent_id,
                "name": agent.agent_name,
                "role": agent.agent_role.value,
                "status": agent.status.value,
            })
        return tree
