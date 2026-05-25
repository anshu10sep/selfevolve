from agents.skills.validator import skill
from core.event_bus import EventBus, EventChannels, Event
from persistence.redis_client import get_redis_client
import asyncio
import logging

logger = logging.getLogger(__name__)

@skill("common")
def propose_prompt_update(new_nuance: str, rationale: str) -> str:
    """Propose an update to your own Strategic Nuance (system prompt).
    Use this when you have learned a new lesson from the market or realize
    you need a persistent new rule to improve your performance.

    Args:
        new_nuance: The new rule or nuance to add to your prompt (max 3 sentences).
        rationale: Why this update is necessary and how it improves performance.

    Returns:
        Confirmation that the proposal was submitted to the Evolution Director.
    """
    async def _publish():
        try:
            redis = await get_redis_client()
            bus = EventBus(redis)
            event = Event(
                event_type="EVOLUTION_PROPOSAL",
                data={"new_nuance": new_nuance, "rationale": rationale},
                source="agent_self_reflection"
            )
            await bus.publish(EventChannels.EVOLUTION_EVENTS, event)
            return True
        except Exception as e:
            logger.error(f"Failed to publish evolution proposal: {e}")
            return False

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            success = pool.submit(lambda: asyncio.run(_publish())).result(timeout=10)
    else:
        success = asyncio.run(_publish())

    if success:
        return f"✅ Evolution proposal submitted successfully. Rationale logged: '{rationale[:50]}...'"
    else:
        return "❌ Failed to submit evolution proposal due to Event Bus error."
