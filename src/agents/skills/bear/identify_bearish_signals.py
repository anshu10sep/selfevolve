from typing import List
from agents.skills.validator import skill

@skill("bear")
def detect_death_cross(short_term_ma: List[float], long_term_ma: List[float]) -> bool:
    """
    Detects a 'Death Cross' bearish signal where a short-term moving average crosses below a long-term moving average.
    
    Args:
        short_term_ma (List[float]): Time series data for the short-term moving average.
        long_term_ma (List[float]): Time series data for the long-term moving average.
        
    Returns:
        bool: True if a death cross is detected in the most recent data points, False otherwise.
    """
    if len(short_term_ma) < 2 or len(long_term_ma) < 2:
        return False
        
    # Check if previously short term was above long term, and now it is below
    prev_short = short_term_ma[-2]
    prev_long = long_term_ma[-2]
    curr_short = short_term_ma[-1]
    curr_long = long_term_ma[-1]
    
    if prev_short >= prev_long and curr_short < curr_long:
        return True
        
    return False
