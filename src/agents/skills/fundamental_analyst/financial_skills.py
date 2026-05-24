from agents.skills.validator import skill

@skill("fundamental_analyst")
def calculate_pe_ratio(price: float, earnings_per_share: float) -> float:
    """
    Calculates the Price-to-Earnings (P/E) ratio.
    
    Args:
        price: The current stock price.
        earnings_per_share: The earnings per share (EPS).
        
    Returns:
        The P/E ratio.
    """
    if earnings_per_share <= 0:
        return 0.0
    return price / earnings_per_share

@skill("fundamental_analyst")
def assess_debt_to_equity(total_debt: float, total_equity: float) -> float:
    """
    Calculates the Debt-to-Equity ratio to assess financial leverage.
    
    Args:
        total_debt: The total debt of the company.
        total_equity: The total shareholder equity.
        
    Returns:
        The Debt-to-Equity ratio.
    """
    if total_equity <= 0:
        return float('inf')
    return total_debt / total_equity