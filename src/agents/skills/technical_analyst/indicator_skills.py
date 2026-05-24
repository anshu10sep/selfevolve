from typing import List
from agents.skills.validator import skill

@skill("technical_analyst")
def calculate_sma(prices: List[float], period: int) -> List[float]:
    """
    Calculates the Simple Moving Average (SMA) for a given list of prices.
    
    Args:
        prices: A list of historical prices.
        period: The number of periods to calculate the SMA over.
        
    Returns:
        A list of SMA values.
    """
    if len(prices) < period or period <= 0:
        return []
    
    sma = []
    for i in range(len(prices) - period + 1):
        window = prices[i:i + period]
        sma.append(sum(window) / period)
    return sma

@skill("technical_analyst")
def identify_trend(current_price: float, sma_value: float) -> str:
    """
    Identifies the current trend based on price and SMA.
    
    Args:
        current_price: The current asset price.
        sma_value: The current Simple Moving Average value.
        
    Returns:
        'bullish' if price > SMA, 'bearish' if price < SMA, 'neutral' otherwise.
    """
    if current_price > sma_value:
        return "bullish"
    elif current_price < sma_value:
        return "bearish"
    return "neutral"