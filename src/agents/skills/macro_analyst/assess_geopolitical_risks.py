def assess_geopolitical_risks(event_description: str, affected_regions: list[str]) -> dict:
    """
    Assesses the potential impact of geopolitical events (e.g., conflicts, policy changes) on global markets.

    Args:
        event_description: A description of the geopolitical event.
        affected_regions: A list of regions potentially impacted.

    Returns:
        A dictionary detailing the risk level, potential market sectors affected, and recommended responses.
    """
    print(f"Assessing geopolitical risk: '{event_description[:100]}' affecting {affected_regions}")
    if "conflict" in event_description.lower() and "middle east" in [r.lower() for r in affected_regions]:
        risk_level = "high"
        affected_sectors = ["energy", "defense"]
        recommendation = "Increase hedging in energy commodities."
    else:
        risk_level = "medium"
        affected_sectors = ["various"]
        recommendation = "Monitor closely."
    return {"risk_level": risk_level, "affected_sectors": affected_sectors, "recommendation": recommendation}
