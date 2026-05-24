from typing import Dict, Any
from agents.skills.validator import skill

@skill
def generate_trading_algorithm(strategy_name: str, parameters: Dict[str, Any]) -> str:
    """
    Generates Python code for a specific trading algorithm based on provided parameters.
    
    Args:
        strategy_name (str): The name of the trading strategy (e.g., 'mean_reversion', 'momentum').
        parameters (Dict[str, Any]): Configuration parameters for the algorithm.
        
    Returns:
        str: The generated Python source code for the trading algorithm.
    """
    if strategy_name == "mean_reversion":
        window = parameters.get("window", 20)
        threshold = parameters.get("threshold", 2.0)
        return f'''
def mean_reversion_strategy(prices):
    """Generated mean reversion strategy"""
    window = {window}
    threshold = {threshold}
    if len(prices) < window:
        return "HOLD"
    moving_avg = sum(prices[-window:]) / window
    return "BUY" if prices[-1] < moving_avg - threshold else "HOLD"
'''
    return "# Strategy not recognized"
