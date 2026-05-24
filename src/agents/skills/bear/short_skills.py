from typing import List
from agents.skills.validator import skill

@skill("bear")
def calculate_drawdown(peak_price: float, current_price: float) -> float:
    """
    Calculates the current drawdown from the peak price.
    
    Args:
        peak_price: The highest historical price.
        current_price: The current asset price.
        
    Returns:
        The drawdown percentage as a float (e.g., 0.15 for 15%).
    """
    if peak_price <= 0:
        return 0.0
    drawdown = (peak_price - current_price) / peak_price
    return max(0.0, drawdown)

@skill("bear")
def identify_resistance_breakdown(prices: List[float], support_level: float) -> bool:
    """
    Identifies if the price has broken down below a key support level.
    
    Args:
        prices: A list of recent prices (oldest to newest).
        support_level: The identified support price level.
        
    Returns:
        True if the most recent price is below support and the previous was above, False otherwise.
    """
    if len(prices) < 2:
        return False
    
    previous_price = prices[-2]
    current_price = prices[-1]
    
    return previous_price >= support_level and current_price < support_level