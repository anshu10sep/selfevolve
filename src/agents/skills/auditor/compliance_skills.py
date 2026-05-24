from typing import Dict
from agents.skills.validator import skill

@skill("auditor")
def check_trade_compliance(trade_amount: float, max_allowed: float) -> bool:
    """
    Checks if a proposed trade amount is within the compliance limits.
    
    Args:
        trade_amount: The amount of the proposed trade.
        max_allowed: The maximum allowed trade amount.
        
    Returns:
        True if compliant, False otherwise.
    """
    return trade_amount <= max_allowed

@skill("auditor")
def verify_kyc_status(user_id: str, kyc_database: Dict[str, bool]) -> bool:
    """
    Verifies the KYC (Know Your Customer) status of a user.
    
    Args:
        user_id: The ID of the user.
        kyc_database: A dictionary mapping user IDs to their KYC status.
        
    Returns:
        True if the user is KYC verified, False otherwise.
    """
    return kyc_database.get(user_id, False)