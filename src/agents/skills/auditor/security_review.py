from typing import Dict, Any, List
from agents.skills.validator import skill

@skill("auditor")
def review_smart_contract_security(contract_code: str, known_vulnerabilities: List[str]) -> Dict[str, Any]:
    """
    Reviews smart contract code for known security vulnerabilities.
    
    Args:
        contract_code (str): The source code of the smart contract.
        known_vulnerabilities (List[str]): A list of known vulnerability patterns to look for.
        
    Returns:
        Dict[str, Any]: A report containing the security score and any found vulnerabilities.
    """
    report = {
        "is_secure": True,
        "vulnerabilities_found": [],
        "security_score": 100
    }
    
    if not contract_code:
        report["is_secure"] = False
        report["security_score"] = 0
        return report
        
    for vuln in known_vulnerabilities:
        if vuln in contract_code:
            report["vulnerabilities_found"].append(vuln)
            report["is_secure"] = False
            report["security_score"] -= 20
            
    report["security_score"] = max(0, report["security_score"])
    return report
