"""
Base Agent Framework

Provides the foundation for all agents in the SelfEvolve system.
Each agent has an immutable Identity Core and mutable Strategic Nuance,
structured output enforcement, cost tracking, and trust weight integration.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional, Type

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from core.models.agents import AgentIdentity, AgentRole, AgentType, AgentStatus
from core.models.audit import CostRecord
from config.constants import COST_TRACKING_MODELS

logger = structlog.get_logger(component="base_agent")


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the hierarchy.
    
    Every agent has:
    - An immutable identity core (cannot be modified by evolution)
    - A mutable strategic nuance (updated by the Meta-Review agent)
    - Structured output enforcement via Pydantic
    - Automatic cost tracking per invocation
    - Trust weight awareness
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
        return self.identity.full_prompt

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
        3. Structured output enforcement
        4. Cost tracking
        5. Error handling with safe defaults
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
            # Use structured output if schema provided
            if output_schema:
                structured_llm = self.llm.with_structured_output(output_schema)
                response = await structured_llm.ainvoke(messages)
                result = response.model_dump() if isinstance(response, BaseModel) else response
            else:
                response = await self.llm.ainvoke(messages)
                result = {"content": response.content}

            # Track costs
            cost_record = self._track_cost(response, start_time)
            result["_cost"] = cost_record.total_cost_usd
            result["_duration_ms"] = int((time.time() - start_time) * 1000)

            await self._logger.ainfo(
                "agent_invocation_complete",
                agent=self.name,
                duration_ms=result["_duration_ms"],
                cost=cost_record.total_cost_usd,
            )
            return result

        except Exception as e:
            await self._logger.aerror(
                "agent_invocation_failed",
                agent=self.name,
                error=str(e),
                exc_info=True,
            )
            # Safe default: return empty/pass result
            return self._safe_default(str(e))

    def _track_cost(self, response: Any, start_time: float) -> CostRecord:
        """Track LLM API cost for this invocation."""
        model_name = getattr(self.llm, "model_name", "unknown")

        # Extract token usage from response metadata
        prompt_tokens = 0
        completion_tokens = 0

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
        }
