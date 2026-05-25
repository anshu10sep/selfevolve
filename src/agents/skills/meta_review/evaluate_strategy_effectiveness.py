from agents.skills.validator import skill

@skill("meta_review")
def evaluate_strategy_effectiveness(strategy_id: str, performance_data: dict, market_conditions: dict) -> dict:
    """
    Evaluates the effectiveness of a specific trading strategy under various market conditions.

    Args:
        strategy_id: The identifier of the trading strategy.
        performance_data: A dictionary of historical performance metrics for the strategy.
        market_conditions: A dictionary describing the market conditions during the performance period.

    Returns:
        A dictionary with an assessment of the strategy's effectiveness, strengths, weaknesses, and recommendations.
    """
    print(f"Evaluating strategy '{strategy_id}' effectiveness.")
    # Placeholder for actual strategy evaluation logic
    if performance_data.get("sharpe_ratio", 0) > 1.0 and market_conditions.get("volatility", "low") == "low":
        effectiveness = "highly_effective_in_low_volatility"
        recommendations = ["Consider scaling up in similar conditions."]
    else:
        effectiveness = "moderate_effectiveness"
        recommendations = ["Review parameters for high volatility markets."]
    return {"effectiveness": effectiveness, "strengths": ["consistent_returns"], "weaknesses": ["poor_in_high_volatility"], "recommendations": recommendations}
