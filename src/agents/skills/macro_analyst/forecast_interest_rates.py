def forecast_interest_rates(central_bank_statements: list, inflation_data: dict) -> dict:
    """
    Forecasts future interest rate movements based on central bank communications and inflation data.

    Args:
        central_bank_statements: A list of recent statements or minutes from central banks.
        inflation_data: A dictionary containing current and projected inflation rates.

    Returns:
        A dictionary with interest rate predictions (e.g., "hike", "cut", "hold") and confidence level.
    """
    print(f"Forecasting interest rates based on central bank statements and inflation: {inflation_data.get('current_cpi', 'N/A')}")
    if any("hawkish" in s.lower() for s in central_bank_statements) and inflation_data.get("current_cpi", 0) > 0.03:
        prediction = "hike"
        confidence = 0.8
    elif any("dovish" in s.lower() for s in central_bank_statements) and inflation_data.get("current_cpi", 0) < 0.02:
        prediction = "cut"
        confidence = 0.7
    else:
        prediction = "hold"
        confidence = 0.6
    return {"rate_prediction": prediction, "confidence": confidence, "implications": "bond_market_impact"}
