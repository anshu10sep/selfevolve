from agents.skills.validator import skill

@skill("product")
def roadmap_management(current_roadmap: list[str], new_features: list[str], priorities: dict) -> list[str]:
    """
    Manages the product roadmap, prioritizing features and adjusting timelines.

    Args:
        current_roadmap: The existing product roadmap.
        new_features: A list of newly defined features.
        priorities: A dictionary defining prioritization rules (e.g., "high_value", "low_effort").

    Returns:
        An updated and prioritized product roadmap.
    """
    print(f"Managing product roadmap with {len(new_features)} new features.")
    updated_roadmap = list(current_roadmap) # Create a copy
    for feature in new_features:
        # Simple prioritization logic
        if feature.get("business_value") == "high" and feature.get("effort") == "low":
            updated_roadmap.insert(0, feature) # Add to top
        else:
            updated_roadmap.append(feature)
    # In a real scenario, this would involve more complex sorting and scheduling
    return updated_roadmap
