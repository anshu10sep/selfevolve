from typing import Dict, Any
from agents.skills.validator import skill

@skill("crypto_analyst")
def evaluate_tokenomics(total_supply: float, circulating_supply: float, inflation_rate: float) -> Dict[str, Any]:
    """
    Evaluates the tokenomics of a cryptocurrency project.
    
    Args:
        total_supply (float): The maximum or total supply of the token.
        circulating_supply (float): The currently circulating supply of the token.
        inflation_rate (float): The annual inflation rate of the token supply.
        
    Returns:
        Dict[str, Any]: An evaluation report containing a score and risk assessment.
    """
    score = 100
    risk = "LOW"
    
    if total_supply <= 0 or circulating_supply < 0:
        return {"tokenomics_score": 0, "risk_level": "CRITICAL", "is_viable": False}
        
    if circulating_supply / total_supply < 0.2:
        score -= 30
        risk = "HIGH"
        
    if inflation_rate > 0.15:
        score -= 40
        risk = "HIGH"
    elif inflation_rate > 0.05:
        score -= 15
        risk = "MEDIUM"
        
    return {
        "tokenomics_score": max(0, score),
        "risk_level": risk,
        "is_viable": score >= 60
    }
