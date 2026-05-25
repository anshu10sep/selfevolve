from typing import Dict, Any, List
from agents.skills.validator import skill

@skill("auditor")
def verify_trade_compliance(trade_details: Dict[str, Any], compliance_rules: List[str]) -> bool:
    """
    Verifies if a proposed trade meets all compliance rules.
    
    Args:
        trade_details (Dict[str, Any]): A dictionary containing trade information (e.g., asset, amount, price).
        compliance_rules (List[str]): A list of compliance rule identifiers to check against.
        
    Returns:
        bool: True if the trade is compliant with all rules, False otherwise.
    """
    if not trade_details or not compliance_rules:
        return False
        
    for rule in compliance_rules:
        if rule == "MAX_VOLUME" and trade_details.get("volume", 0) > 1000000:
            return False
        if rule == "RESTRICTED_ASSET" and trade_details.get("asset") in ["XMR", "ZEC"]:
            return False
            
    return True
