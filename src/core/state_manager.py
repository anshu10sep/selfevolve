"""
Central State Manager

Manages all system state across Redis (hot) and PostgreSQL (cold).
Provides atomic operations for portfolio state, tranches, and agent states.
The LLM never directly accesses state — it flows through this manager.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
import structlog

from core.models.portfolio import (
    PortfolioState,
    TrancheState,
    TrancheStatus,
)
from core.models.agents import AgentIdentity, AgentStatus
from config.constants import DEFAULT_TRANCHE_COUNT, DEFAULT_TRANCHE_SIZES

logger = structlog.get_logger(component="state_manager")


class StateManager:
    """
    Centralized state management for the SelfEvolve system.
    
    Hot state (Redis): Portfolio, tranches, agent status — sub-ms access.
    Cold state (PostgreSQL): Persisted periodically for durability.
    """

    PORTFOLIO_KEY = "selfevolve:portfolio_state"
    TRANCHE_KEY_PREFIX = "selfevolve:tranche:"
    AGENT_KEY_PREFIX = "selfevolve:agent:"
    AGENT_REGISTRY_KEY = "selfevolve:agent_registry"

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    # ── Portfolio State ────────────────────────────────────────────

    async def get_portfolio_state(self) -> PortfolioState:
        """Retrieve current portfolio state from Redis."""
        data = await self._redis.get(self.PORTFOLIO_KEY)
        if data:
            return PortfolioState.model_validate_json(data)
        # Initialize default state
        state = self._create_default_portfolio()
        await self.update_portfolio(state)
        return state

    async def update_portfolio(self, state: PortfolioState) -> None:
        """Atomically update portfolio state in Redis."""
        state.updated_at = datetime.now(timezone.utc)
        await self._redis.set(
            self.PORTFOLIO_KEY,
            state.model_dump_json(),
        )
        await logger.ainfo(
            "portfolio_state_updated",
            equity=state.total_equity,
            settled_cash=state.settled_cash,
            net_pnl=state.net_pnl_today,
        )

    # ── Tranche Management ─────────────────────────────────────────

    async def initialize_tranches(self, sizes: list[float] | None = None) -> None:
        """Initialize capital tranches. Called on system startup."""
        sizes = sizes or DEFAULT_TRANCHE_SIZES
        for i, amount in enumerate(sizes):
            tranche = TrancheState(tranche_index=i, amount=amount)
            await self._save_tranche(tranche)
        await logger.ainfo(
            "tranches_initialized",
            count=len(sizes),
            total=sum(sizes),
        )

    async def checkout_tranche(self, trade_id: str) -> Optional[TrancheState]:
        """
        Atomically checkout an available tranche for a trade.
        
        Returns the locked tranche, or None if no tranches available.
        Uses Redis transactions to prevent double-checkout.
        """
        for i in range(DEFAULT_TRANCHE_COUNT):
            key = f"{self.TRANCHE_KEY_PREFIX}{i}"
            async with self._redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(key)
                    data = await pipe.get(key)
                    if not data:
                        continue

                    tranche = TrancheState.model_validate_json(data)
                    if tranche.status != TrancheStatus.AVAILABLE:
                        continue

                    # Lock the tranche atomically
                    tranche.status = TrancheStatus.LOCKED
                    tranche.locked_trade_id = trade_id
                    tranche.locked_at = datetime.now(timezone.utc)

                    pipe.multi()
                    pipe.set(key, tranche.model_dump_json())
                    await pipe.execute()

                    await logger.ainfo(
                        "tranche_checked_out",
                        tranche_index=i,
                        trade_id=trade_id,
                        amount=tranche.amount,
                    )
                    return tranche
                except aioredis.WatchError:
                    # Another process grabbed this tranche, try next
                    continue

        await logger.awarning("no_tranches_available", trade_id=trade_id)
        return None

    async def release_tranche(
        self, tranche_index: int, settling_until: Optional[datetime] = None
    ) -> None:
        """Release a tranche back to available or settling state."""
        tranche = await self._get_tranche(tranche_index)
        if not tranche:
            return

        if settling_until:
            tranche.status = TrancheStatus.SETTLING
            tranche.settling_until = settling_until
        else:
            tranche.status = TrancheStatus.AVAILABLE
            tranche.locked_trade_id = None
            tranche.locked_at = None
            tranche.settling_until = None

        await self._save_tranche(tranche)
        await logger.ainfo(
            "tranche_released",
            tranche_index=tranche_index,
            new_status=tranche.status.value,
        )

    async def settle_matured_tranches(self) -> int:
        """Check and settle tranches whose T+1 window has passed."""
        settled_count = 0
        now = datetime.now(timezone.utc)

        for i in range(DEFAULT_TRANCHE_COUNT):
            tranche = await self._get_tranche(i)
            if (
                tranche
                and tranche.status == TrancheStatus.SETTLING
                and tranche.settling_until
                and now >= tranche.settling_until
            ):
                tranche.status = TrancheStatus.AVAILABLE
                tranche.locked_trade_id = None
                tranche.locked_at = None
                tranche.settling_until = None
                await self._save_tranche(tranche)
                settled_count += 1

        if settled_count > 0:
            await logger.ainfo("tranches_settled", count=settled_count)
        return settled_count

    async def get_all_tranches(self) -> list[TrancheState]:
        """Get all tranche states."""
        tranches = []
        for i in range(DEFAULT_TRANCHE_COUNT):
            tranche = await self._get_tranche(i)
            if tranche:
                tranches.append(tranche)
        return tranches

    # ── Agent State ────────────────────────────────────────────────

    async def register_agent(self, agent: AgentIdentity) -> None:
        """Register a new agent in the system."""
        key = f"{self.AGENT_KEY_PREFIX}{agent.agent_id}"
        await self._redis.set(key, agent.model_dump_json())
        await self._redis.sadd(self.AGENT_REGISTRY_KEY, agent.agent_id)
        await logger.ainfo(
            "agent_registered",
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            role=agent.agent_role.value,
        )

    async def get_agent_state(self, agent_id: str) -> Optional[AgentIdentity]:
        """Get an agent's current state."""
        data = await self._redis.get(f"{self.AGENT_KEY_PREFIX}{agent_id}")
        if data:
            return AgentIdentity.model_validate_json(data)
        return None

    async def update_agent_state(
        self, agent_id: str, updates: dict[str, Any]
    ) -> Optional[AgentIdentity]:
        """Update specific fields of an agent's state."""
        agent = await self.get_agent_state(agent_id)
        if not agent:
            return None

        agent_dict = agent.model_dump()
        agent_dict.update(updates)
        updated_agent = AgentIdentity.model_validate(agent_dict)
        await self._redis.set(
            f"{self.AGENT_KEY_PREFIX}{agent_id}",
            updated_agent.model_dump_json(),
        )
        return updated_agent

    async def get_all_agent_ids(self) -> list[str]:
        """Get all registered agent IDs."""
        members = await self._redis.smembers(self.AGENT_REGISTRY_KEY)
        return [m.decode() if isinstance(m, bytes) else m for m in members]

    async def get_all_agents(self) -> list[AgentIdentity]:
        """Get all registered agents."""
        agent_ids = await self.get_all_agent_ids()
        agents = []
        for aid in agent_ids:
            agent = await self.get_agent_state(aid)
            if agent:
                agents.append(agent)
        return agents

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_tranche(self, index: int) -> Optional[TrancheState]:
        data = await self._redis.get(f"{self.TRANCHE_KEY_PREFIX}{index}")
        if data:
            return TrancheState.model_validate_json(data)
        return None

    async def _save_tranche(self, tranche: TrancheState) -> None:
        await self._redis.set(
            f"{self.TRANCHE_KEY_PREFIX}{tranche.tranche_index}",
            tranche.model_dump_json(),
        )

    def _create_default_portfolio(self) -> PortfolioState:
        """Create the initial $100 portfolio state."""
        tranches = [
            TrancheState(tranche_index=i, amount=DEFAULT_TRANCHE_SIZES[i])
            for i in range(DEFAULT_TRANCHE_COUNT)
        ]
        return PortfolioState(
            total_equity=100.0,
            settled_cash=100.0,
            unsettled_cash=0.0,
            buying_power=100.0,
            tranches=tranches,
        )

    async def health_check(self) -> bool:
        """Verify Redis connectivity."""
        try:
            return await self._redis.ping()
        except Exception:
            return False
