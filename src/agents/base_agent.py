"""
Base Agent Framework

Provides the foundation for all agents in the SelfEvolve system.
Each agent has an immutable Identity Core and mutable Strategic Nuance,
structured output enforcement, cost tracking, trust weight integration,
and a tool-calling bridge that wires registered skills as LLM tools.
"""

from __future__ import annotations

import time
import uuid
import inspect
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional, Type, Callable

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from pydantic import BaseModel

from core.models.agents import AgentIdentity, AgentRole, AgentType, AgentStatus
from core.models.audit import CostRecord
from config.constants import COST_TRACKING_MODELS
from core.activity_tracker import tracker as _activity_tracker

logger = structlog.get_logger(component="base_agent")

# Maximum tool-calling iterations to prevent infinite loops
MAX_TOOL_CALL_ITERATIONS = 10


def _convert_skill_to_langchain_tool(
    func: Callable, skill_name: str
) -> Any:
    """
    Convert a registered skill function into a LangChain tool.

    Uses StructuredTool.from_function to properly preserve the original
    function's type hints, docstring, and parameter schema — critical
    for Gemini API function declaration compatibility.
    """
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        func=func,
        name=skill_name,
        description=func.__doc__ or f"Tool: {skill_name}",
    )


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the hierarchy.

    Every agent has:
    - An immutable identity core (cannot be modified by evolution)
    - A mutable strategic nuance (updated by the Meta-Review agent)
    - Structured output enforcement via Pydantic
    - Automatic cost tracking per invocation
    - Trust weight awareness
    - Tool-calling bridge: registered skills are available as LLM tools
    """

    def __init__(
        self,
        identity: AgentIdentity,
        llm: BaseChatModel,
        trust_weight: float = 1.0,
    ):
        self.identity = identity
        self.llm = llm
        self.trust_weight = trust_weight
        self._invocation_count = 0
        self._total_cost = 0.0
        self._logger = structlog.get_logger(
            component=f"agent.{identity.agent_role.value.lower()}"
        )

        # ── Tool-Calling Bridge ─────────────────────────────────────
        # Load skills from the SkillRegistry for this agent's role
        self._tools: list[Callable] = []
        self._tool_map: dict[str, Callable] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        """
        Load registered skills from the SkillRegistry for this agent.

        Looks up skills by multiple keys to maximize discovery:
        1. Agent role lowercase (e.g., "fundamental_analyst")
        2. Agent name (e.g., "Fundamental Analyst")
        3. Agent role value (e.g., "FUNDAMENTAL_ANALYST")

        Each discovered skill is converted to a LangChain tool.
        """
        # Try to load tool skills for this agent using decorators
        try:
            from agents.skills.validator import SkillRegistry
            import agents.skills.jarvis.agent_messaging  # noqa: F401
            import agents.skills.jarvis.evolution_skills  # noqa: F401
            # Cross-agent insight tools (registers for multiple agent roles)
            import agents.skills.insights.insight_skills  # noqa: F401
        except ImportError:
            self._logger.debug("skill_registry_not_available")
            return

        # Try multiple keys to find skills
        lookup_keys = [
            self.role.value.lower(),                    # e.g. "fundamental_analyst"
            self.name,                                  # e.g. "Fundamental Analyst"
            self.name.lower().replace(" ", "_"),        # e.g. "fundamental_analyst"
            self.role.value,                            # e.g. "FUNDAMENTAL_ANALYST"
            "common",                                   # Load common skills for all agents
        ]

        all_skills: dict[str, Callable] = {}
        for key in lookup_keys:
            found = SkillRegistry.get_skills(key)
            if found:
                all_skills.update(found)

        if not all_skills:
            self._logger.debug(
                "no_skills_found", agent=self.name, keys_tried=lookup_keys
            )
            return

        for skill_name, skill_func in all_skills.items():
            try:
                lc_tool = _convert_skill_to_langchain_tool(skill_func, skill_name)
                self._tools.append(lc_tool)
                self._tool_map[skill_name] = skill_func
            except Exception as e:
                self._logger.warning(
                    "skill_conversion_failed",
                    skill=skill_name, error=str(e),
                )

        if self._tools:
            self._logger.info(
                "skills_loaded",
                agent=self.name,
                skill_count=len(self._tools),
                skills=list(self._tool_map.keys()),
            )

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @property
    def name(self) -> str:
        return self.identity.agent_name

    @property
    def role(self) -> AgentRole:
        return self.identity.agent_role

    @property
    def system_prompt(self) -> str:
        """Assembled system prompt from core + strategic nuance."""
        prompt = self.identity.full_prompt

        # If the agent has tools, append a tool guidance section
        if self._tools:
            tool_names = ", ".join(self._tool_map.keys())
            prompt += (
                f"\n\nAvailable Tools:\n"
                f"You have access to the following tools: {tool_names}\n"
                f"Use these tools to gather real data and perform real "
                f"calculations. ALWAYS prefer tool results over guessing."
            )

        return prompt

    async def invoke(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
        output_schema: Type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """
        Invoke the agent with a message and optional context.

        Handles:
        1. System prompt injection (identity core + strategic nuance)
        2. Context injection (portfolio state, market data)
        3. Tool-calling loop (if agent has registered skills)
        4. Structured output enforcement
        5. Cost tracking
        6. Error handling with safe defaults
        """
        start_time = time.time()
        self._invocation_count += 1

        # Build messages
        messages = [SystemMessage(content=self.system_prompt)]

        # Inject context if provided
        if context:
            context_str = "\n".join(
                f"**{k}**: {v}" for k, v in context.items()
            )
            messages.append(
                HumanMessage(content=f"Current Context:\n{context_str}")
            )

        messages.append(HumanMessage(content=user_message))

        try:
            # ── Execute Tools first if available ─────────
            tool_result = None
            if self._tools:
                tool_result = await self._invoke_with_tools(messages)
                # If we don't need structured output, this is our final result
                if not output_schema:
                    result = tool_result
            
            # ── Extract Structured Output if requested ─────────
            if output_schema:
                if tool_result:
                    # Append the text result of the tool loop and ask the LLM to coerce it
                    messages.append(AIMessage(content=tool_result["content"]))
                    messages.append(HumanMessage(content="Please format your final conclusion into the requested structured output schema based on your analysis above."))
                
                structured_llm = self.llm.with_structured_output(output_schema)
                response = await structured_llm.ainvoke(messages)
                result = response.model_dump() if isinstance(response, BaseModel) else response
                
                # Preserve tool metrics
                if tool_result:
                    result["_tools_used"] = tool_result.get("_tools_used", [])
                    result["_tool_iterations"] = tool_result.get("_tool_iterations", 0)
                    
            # ── Fallback: Simple invocation (no tools, no schema) ─────
            elif not self._tools and not output_schema:
                response = await self.llm.ainvoke(messages)
                from core.llm_utils import extract_text
                result = {"content": extract_text(response.content)}

            # Track costs
            cost_record = self._track_cost(None, start_time)
            result["_cost"] = cost_record.total_cost_usd
            result["_duration_ms"] = int((time.time() - start_time) * 1000)

            # Report to the centralized activity tracker (feeds dashboard)
            _activity_tracker.record(
                agent_role=self.role.value,
                cost=cost_record.total_cost_usd,
                tokens=cost_record.prompt_tokens + cost_record.completion_tokens,
                success=True,
            )

            await self._logger.ainfo(
                "agent_invocation_complete",
                agent=self.name,
                duration_ms=result["_duration_ms"],
                cost=cost_record.total_cost_usd,
                tools_used=result.get("_tools_used", []),
            )
            return result

        except Exception as e:
            await self._logger.aerror(
                "agent_invocation_failed",
                agent=self.name,
                error=str(e),
                exc_info=True,
            )
            # Record the failure in the activity tracker
            _activity_tracker.record(
                agent_role=self.role.value,
                cost=0.0,
                tokens=0,
                success=False,
            )
            # Safe default: return empty/pass result
            return self._safe_default(str(e))

    async def _invoke_with_tools(
        self, messages: list
    ) -> dict[str, Any]:
        """
        Invoke the LLM with tool-calling capability.

        This implements the ReAct loop:
        1. LLM sees the message + available tools
        2. LLM either responds with text OR requests tool calls
        3. If tool calls requested → execute them → feed results back
        4. Repeat until LLM responds with final text
        5. Safety: max MAX_TOOL_CALL_ITERATIONS iterations
        """
        tools_used = []
        llm_with_tools = self.llm.bind_tools(self._tools)

        for iteration in range(MAX_TOOL_CALL_ITERATIONS):
            response = await llm_with_tools.ainvoke(messages)

            # Check if LLM wants to call tools
            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                # LLM is done — extract final response
                from core.llm_utils import extract_text
                content = extract_text(response.content)
                return {
                    "content": content,
                    "_tools_used": tools_used,
                    "_tool_iterations": iteration,
                }

            # Add the AI message with tool calls to the conversation
            messages.append(response)

            # Execute each tool call
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                tool_args = tc.get("args", {})
                tool_id = tc.get("id", str(uuid.uuid4()))

                await self._logger.ainfo(
                    "tool_call_executing",
                    agent=self.name,
                    tool=tool_name,
                    args_keys=list(tool_args.keys()),
                )

                try:
                    # Look up the original skill function and call it
                    if tool_name in self._tool_map:
                        func = self._tool_map[tool_name]
                        if inspect.iscoroutinefunction(func):
                            result = await func(**tool_args)
                        else:
                            result = func(**tool_args)
                    else:
                        result = f"Error: Unknown tool '{tool_name}'"

                    tools_used.append({
                        "tool": tool_name,
                        "status": "success",
                        "iteration": iteration,
                    })

                except Exception as e:
                    result = f"Tool error ({tool_name}): {str(e)}"
                    tools_used.append({
                        "tool": tool_name,
                        "status": "error",
                        "error": str(e),
                        "iteration": iteration,
                    })
                    await self._logger.awarning(
                        "tool_call_failed",
                        agent=self.name,
                        tool=tool_name,
                        error=str(e),
                    )

                # Feed tool result back to LLM
                messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id,
                    )
                )

        # Safety: max iterations reached
        await self._logger.awarning(
            "tool_call_max_iterations",
            agent=self.name,
            max_iterations=MAX_TOOL_CALL_ITERATIONS,
        )
        from core.llm_utils import extract_text
        last_content = extract_text(
            getattr(messages[-1], "content", "Max tool iterations reached.")
        )
        return {
            "content": last_content,
            "_tools_used": tools_used,
            "_tool_iterations": MAX_TOOL_CALL_ITERATIONS,
            "_warning": "max_tool_iterations_reached",
        }

    def _track_cost(self, response: Any, start_time: float) -> CostRecord:
        """Track LLM API cost for this invocation."""
        model_name = getattr(self.llm, "model_name", "unknown")

        # Extract token usage from response metadata
        prompt_tokens = 0
        completion_tokens = 0

        if response is not None:
            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("token_usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
            elif hasattr(response, "usage_metadata"):
                prompt_tokens = getattr(response.usage_metadata, "input_tokens", 0)
                completion_tokens = getattr(response.usage_metadata, "output_tokens", 0)

        # Calculate cost
        pricing = COST_TRACKING_MODELS.get(model_name, {"prompt": 0.001, "completion": 0.002})
        cost = (
            (prompt_tokens / 1000.0) * pricing["prompt"]
            + (completion_tokens / 1000.0) * pricing["completion"]
        )
        self._total_cost += cost

        return CostRecord(
            agent_role=self.role.value,
            model_used=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost_usd=cost,
            task_type=self.__class__.__name__,
        )

    @abstractmethod
    def _safe_default(self, error: str) -> dict[str, Any]:
        """Return a safe default when the agent fails."""
        pass

    def update_strategic_nuance(self, new_nuance: str, new_version: int) -> None:
        """Update the agent's mutable strategic nuance (called by evolution pipeline).

        This is the ONLY way an agent's prompt can be modified at runtime.
        The identity_core remains immutable. The evolution pipeline validates
        the update via AgentUpdate (Pydantic domain isolation) before calling this.

        Args:
            new_nuance: New Strategic_Nuance text (max 3 rules)
            new_version: Incremented version number
        """
        old_version = self.identity.version
        self.identity.strategic_nuance = new_nuance
        self.identity.version = new_version
        self._logger.info(
            "strategic_nuance_updated",
            agent=self.name,
            old_version=old_version,
            new_version=new_version,
            nuance_length=len(new_nuance),
        )

    def reload_skills(self) -> None:
        """Reload skills from the registry (e.g., after hot-reload)."""
        self._tools = []
        self._tool_map = {}
        self._load_skills()

    def get_available_tools(self) -> list[str]:
        """Get list of available tool names for this agent."""
        return list(self._tool_map.keys())

    async def publish_insight(
        self,
        insight_type: str,
        title: str,
        description: str,
        confidence: float = 0.5,
        data: dict | None = None,
        ticker: str | None = None,
        urgency: str = "MEDIUM",
    ) -> None:
        """
        Publish an insight to the agent insight bus for cross-agent consumption.

        This is how agents share real-time intelligence with each other.
        All insights are typed, timestamped, and auto-expire.

        Args:
            insight_type: InsightType value (e.g., "REGIME_CHANGE", "TECHNICAL_SIGNAL")
            title: Short headline (e.g., "Bullish Breakout: AAPL")
            description: Detailed explanation (max 1000 chars)
            confidence: Confidence in this insight (0-1)
            data: Structured supporting data dict
            ticker: Ticker scope (None = system-wide)
            urgency: "LOW", "MEDIUM", "HIGH", "CRITICAL"
        """
        try:
            from core.models.insights import AgentInsight, InsightType as IT, InsightUrgency
            from core.insight_publisher import insight_publisher

            insight = AgentInsight(
                source_agent=self.role.value,
                insight_type=IT(insight_type),
                ticker=ticker,
                title=title,
                description=description[:1000],
                confidence=max(0.0, min(1.0, confidence)),
                urgency=InsightUrgency(urgency),
                data=data or {},
            )

            await insight_publisher.publish(insight)

        except Exception as e:
            self._logger.debug(
                "publish_insight_failed",
                agent=self.name,
                error=str(e),
            )

    def get_health(self) -> dict[str, Any]:
        """Get agent health metrics."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role.value,
            "status": self.identity.status.value,
            "invocations": self._invocation_count,
            "total_cost": round(self._total_cost, 6),
            "trust_weight": self.trust_weight,
            "version": self.identity.version,
            "tools_available": len(self._tools),
            "tool_names": self.get_available_tools(),
        }
