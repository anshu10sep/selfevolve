from agents.skills.validator import skill

@skill("judge")
def resolve_conflicts(conflicting_proposals: list[str], conflict_type: str) -> dict:
    """
    Resolves conflicts between competing proposals or agent recommendations.

    Args:
        conflicting_proposals: A list of proposals that are in conflict.
        conflict_type: The nature of the conflict (e.g., "resource_contention", "opposing_strategies").

    Returns:
        A dictionary outlining the resolution, including any compromises or chosen alternatives.
    """
    print(f"Resolving conflict of type '{conflict_type}' between {len(conflicting_proposals)} proposals.")
    if conflict_type == "opposing_strategies":
        # Example: if bull and bear agents have opposing views, find a neutral or compromise strategy
        bull_proposal = next((p for p in conflicting_proposals if p.get("agent") == "bull"), None)
        bear_proposal = next((p for p in conflicting_proposals if p.get("agent") == "bear"), None)

        if bull_proposal and bear_proposal:
            return {"resolution_strategy": "neutral_stance", "details": "Adopted a wait-and-see approach due to conflicting bullish/bearish signals.", "compromise": True}
    return {"resolution_strategy": "default_to_safety", "details": "Prioritized risk mitigation due to unresolved conflict.", "compromise": False}
