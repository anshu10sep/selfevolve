def analyze_global_economy(economic_reports: list, geopolitical_events: list) -> dict:
    """
    Analyzes global economic trends, including GDP growth, inflation, and trade balances across major economies.

    Args:
        economic_reports: A list of recent global economic reports.
        geopolitical_events: A list of recent geopolitical events.

    Returns:
        A dictionary summarizing the global economic outlook and key influencing factors.
    """
    print(f"Analyzing global economy based on {len(economic_reports)} reports and {len(geopolitical_events)} events.")
    # Placeholder for actual macro-economic analysis
    if any("recession" in r.lower() for r in economic_reports):
        outlook = "bearish"
        factors = ["high inflation", "interest rate hikes"]
    else:
        outlook = "neutral_to_bullish"
        factors = ["stable growth", "easing inflation"]
    return {"global_outlook": outlook, "key_factors": factors}
