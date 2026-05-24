def growth_potential_assessment(company_data: dict, industry_outlook: dict) -> dict:
    """
    Assesses the long-term growth potential of a company or asset.

    Args:
        company_data: Financial and operational data of the company.
        industry_outlook: Data on the overall industry's growth prospects.

    Returns:
        A dictionary containing growth potential score and key drivers.
    """
    print(f"Assessing growth potential for {company_data.get('name', 'N/A')} in industry {industry_outlook.get('name', 'N/A')}")
    growth_score = company_data.get("revenue_growth_rate", 0) * 0.6 + industry_outlook.get("market_expansion", 0) * 0.4
    if growth_score > 0.7:
        return {"growth_potential": "high", "score": growth_score, "drivers": ["innovation", "market_demand"]}
    return {"growth_potential": "moderate", "score": growth_score, "drivers": ["stable_market"]}
===