from typing import List
from agents.skills.validator import skill

@skill("bull")
def calculate_upside_potential(current_price: float, target_price: float) -> float:
    """
    Calculates the percentage upside potential to a target price.
    
    Args:
        current_price: The current asset price.
        target_price: The projected target price.
        
    Returns:
        The upside potential as a float (e.g., 0.20 for 20%).
    """
    if current_price <= 0:
        return 0.0
    if target_price <= current_price:
        return 0.0
    return (target_price - current_price) / current_price

@skill("bull")
def identify_breakout(prices: List[float], resistance_level: float) -> bool:
    """
    Identifies if the price has broken out above a key resistance level.
    
    Args:
        prices: A list of recent prices (oldest to newest).
        resistance_level: The identified resistance price level.
        
    Returns:
        True if the most recent price is above resistance and the previous was below, False otherwise.
    """
    if len(prices) < 2:
        return False
    
    previous_price = prices[-2]
    current_price = prices[-1]
    
    return previous_price <= resistance_level and current_price > resistance_level