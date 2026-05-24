from agents.skills.validator import skill

@skill("crypto_analyst")
def analyze_gas_fees(current_gas_price: float, historical_average: float) -> str:
    """
    Analyzes current Ethereum gas fees compared to historical averages.
    
    Args:
        current_gas_price: The current gas price in Gwei.
        historical_average: The historical average gas price in Gwei.
        
    Returns:
        A string indicating whether fees are 'high', 'low', or 'normal'.
    """
    if current_gas_price > historical_average * 1.5:
        return "high"
    elif current_gas_price < historical_average * 0.5:
        return "low"
    return "normal"

@skill("crypto_analyst")
def evaluate_tokenomics(total_supply: float, circulating_supply: float) -> float:
    """
    Evaluates tokenomics by calculating the circulating supply ratio.
    
    Args:
        total_supply: The total maximum supply of the token.
        circulating_supply: The currently circulating supply.
        
    Returns:
        The ratio of circulating supply to total supply (0.0 to 1.0).
    """
    if total_supply <= 0:
        return 0.0
    return circulating_supply / total_supply