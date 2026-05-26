from agents.skills.validator import skill

@skill("journaling")
def record_decisions(decision_maker: str, decision_details: dict, rationale: str) -> dict:
    """
    Records strategic and operational decisions made by agents or the system, along with their rationale.

    Args:
        decision_maker: The agent or entity that made the decision.
        decision_details: A dictionary describing the decision (e.g., "buy_asset", "adjust_strategy").
        rationale: The reasoning behind the decision.

    Returns:
        A dictionary confirming the recording and providing a timestamp.
    """
    import datetime
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"Journaling: Recording decision by {decision_maker} at {timestamp}. Rationale: {rationale[:100]}...")
    # Placeholder for actual persistent storage
    return {"status": "recorded", "timestamp": timestamp, "decision_maker": decision_maker, "decision": decision_details}
