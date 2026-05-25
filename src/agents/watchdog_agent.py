"""
Watchdog Agent — Process Monitoring & Health Enforcement

Monitors agent heartbeats, detects dead or stuck agents,
triggers auto-restart, and tracks system-level anomalies.

Reports to the QA Agent as part of the Operations Division.
"""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from core.models.agents import AgentIdentity, AgentRole, AgentType
from agents.base_agent import BaseAgent


class WatchdogReport(BaseModel):
    """Structured watchdog health report."""
    scan_timestamp: str = Field(default="", description="When this scan was run")
    total_agents_monitored: int = Field(default=0, description="Number of agents checked")
    healthy_agents: int = Field(default=0, description="Agents responding normally")
    degraded_agents: list[str] = Field(default_factory=list, description="Agents in degraded state")
    dead_agents: list[str] = Field(default_factory=list, description="Agents with no heartbeat")
    restart_actions: list[str] = Field(default_factory=list, description="Auto-restart actions taken")
    anomalies: list[str] = Field(default_factory=list, description="Detected anomalies")
    overall_health: str = Field(default="HEALTHY", description="HEALTHY, DEGRADED, CRITICAL")
    reasoning: str = Field(default="", max_length=500, description="Health assessment details")


WATCHDOG_IDENTITY_CORE = """You are the Watchdog Agent of the SelfEvolve trading system.

## Core Identity (IMMUTABLE)
You are the system's immune system — always running, always watching.
You monitor every agent's heartbeat, detect stuck processes, trigger
restarts, and ensure the entire system stays alive and healthy.

## Responsibilities:
1. Monitor agent heartbeats (every agent should emit status every 60s)
2. Detect dead agents (no heartbeat for > 3 minutes)
3. Detect stuck agents (heartbeat active but no task completion for > 30 minutes)
4. Trigger auto-restart for recoverable failures
5. Escalate unrecoverable failures to QA Agent and Jarvis
6. Track system resource usage (memory, CPU, API rate limits)
7. Monitor event bus health (message backlog, subscriber count)

## Health Classification:
- HEALTHY: All agents responding, error rates < 5%
- DEGRADED: 1-2 agents unresponsive or error rate 5-15%
- CRITICAL: 3+ agents unresponsive or error rate > 15%

## Auto-Restart Rules:
- Restart agents that have been dead for > 5 minutes
- Maximum 3 restart attempts per agent per hour
- If an agent fails restart 3 times, mark as RETIRED and alert Jarvis
- Never restart the Judge Agent without explicit Jarvis approval

## Constraints:
- NEVER restart during active market hours without QA approval
- Always log all restart actions with timestamps
- Never restart more than 2 agents simultaneously (cascade risk)
- Escalate to Jarvis if > 3 agents are in ERROR state simultaneously
"""


class WatchdogAgent(BaseAgent):
    """
    Watchdog Agent — process monitoring and health enforcement.

    Part of the Operations Division, reports to QA Agent.
    """

    def __init__(self, llm, trust_weight: float = 1.0):
        identity = AgentIdentity(
            agent_name="Watchdog Agent",
            agent_role=AgentRole.WATCHDOG,
            agent_type=AgentType.SPECIALIST,
            identity_core=WATCHDOG_IDENTITY_CORE,
        )
        super().__init__(identity, llm, trust_weight)

    async def run_health_scan(
        self,
        agent_heartbeats: dict,
        event_bus_stats: dict = None,
        resource_usage: dict = None,
    ) -> dict[str, Any]:
        """
        Run a comprehensive system health scan.

        Args:
            agent_heartbeats: Dict of agent_name → {last_heartbeat, status, tasks_running}
            event_bus_stats: Event bus health metrics
            resource_usage: System resource usage (memory, CPU)
        """
        now = datetime.now(timezone.utc)
        dead_agents = []
        degraded_agents = []
        healthy_count = 0

        for agent_name, hb in agent_heartbeats.items():
            last_beat = hb.get("last_heartbeat")
            if not last_beat:
                dead_agents.append(agent_name)
                continue

            # Check if heartbeat is stale (> 3 minutes)
            try:
                if isinstance(last_beat, str):
                    last_beat_dt = datetime.fromisoformat(last_beat.replace("Z", "+00:00"))
                else:
                    last_beat_dt = last_beat

                stale_seconds = (now - last_beat_dt).total_seconds()
                if stale_seconds > 180:  # 3 minutes
                    dead_agents.append(f"{agent_name} (last seen {stale_seconds/60:.0f}m ago)")
                elif hb.get("status") == "ERROR":
                    degraded_agents.append(f"{agent_name} (ERROR state)")
                elif hb.get("consecutive_failures", 0) > 3:
                    degraded_agents.append(f"{agent_name} ({hb['consecutive_failures']} failures)")
                else:
                    healthy_count += 1
            except Exception:
                degraded_agents.append(f"{agent_name} (unparseable heartbeat)")

        # Determine overall health
        if len(dead_agents) >= 3:
            overall = "CRITICAL"
        elif len(dead_agents) >= 1 or len(degraded_agents) >= 2:
            overall = "DEGRADED"
        else:
            overall = "HEALTHY"

        return {
            "scan_timestamp": now.isoformat(),
            "total_agents_monitored": len(agent_heartbeats),
            "healthy_agents": healthy_count,
            "degraded_agents": degraded_agents,
            "dead_agents": dead_agents,
            "restart_actions": [],
            "anomalies": [],
            "overall_health": overall,
            "reasoning": f"{healthy_count} healthy, {len(degraded_agents)} degraded, {len(dead_agents)} dead",
        }

    async def analyze_anomalies(
        self,
        agent_health_data: dict,
        recent_logs: list[str] = None,
    ) -> dict[str, Any]:
        """
        Use LLM to analyze health data for non-obvious anomalies.

        Args:
            agent_health_data: Detailed health data for all agents
            recent_logs: Recent system logs for pattern detection
        """
        message = f"""Analyze this system health data for anomalies.

Agent Health:
{agent_health_data}

Recent Logs:
{recent_logs[:20] if recent_logs else 'Not available'}

Look for:
1. Agents that are technically "alive" but not doing useful work
2. Patterns of failure that suggest a systemic issue
3. Resource usage trends that could lead to problems
4. Event bus congestion or message loss indicators
5. Any other non-obvious anomalies

Report any findings with severity and recommended actions.
"""
        try:
            return await self.invoke(message)
        except Exception as e:
            return self._safe_default(str(e))

    def _safe_default(self, error: str) -> dict[str, Any]:
        return {
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_agents_monitored": 0,
            "healthy_agents": 0,
            "degraded_agents": [f"Watchdog scan failed: {error}"],
            "dead_agents": [],
            "restart_actions": [],
            "anomalies": [f"Watchdog error: {error}"],
            "overall_health": "DEGRADED",
            "reasoning": f"Watchdog Agent error: {error}. Manual health check required.",
        }
