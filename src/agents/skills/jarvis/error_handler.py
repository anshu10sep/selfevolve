import logging
import os
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def analyze_plain_text_error(error_message: str, source: str = "unknown") -> Dict[str, Any]:
    """
    Analyzes a plain text error to determine its severity and required action.
    
    Args:
        error_message (str): The raw error message.
        source (str): The source of the error (e.g., log file path).
        
    Returns:
        Dict[str, Any]: Analysis results including severity and recommended action.
    """
    analysis = {
        "original_message": error_message,
        "source": source,
        "severity": "low",
        "action_required": False,
        "recommendation": "None",
        "event_type": "plain_text_error"
    }
    
    error_lower = error_message.lower()
    
    if "raise error" in error_lower:
        analysis["severity"] = "medium"
        analysis["action_required"] = True
        analysis["recommendation"] = "Investigate the source code for generic 'raise error' statements and replace them with specific exception types. Suppress to prevent crash."
    elif "critical" in error_lower or "fatal" in error_lower:
        analysis["severity"] = "high"
        analysis["action_required"] = True
        analysis["recommendation"] = "Immediate attention required. Check system integrity and halt affected subsystems."
    elif "timeout" in error_lower:
        analysis["severity"] = "low"
        analysis["action_required"] = True
        analysis["recommendation"] = "Implement exponential backoff and retry logic."
        
    return analysis

def scan_error_logs(log_dir: str) -> List[Dict[str, Any]]:
    """
    Scans error logs in the specified directory for plain text errors.
    
    Args:
        log_dir (str): Directory containing log files.
        
    Returns:
        List[Dict[str, Any]]: A list of analyzed errors.
    """
    analyzed_errors = []
    
    if not os.path.exists(log_dir):
        logger.error(f"Log directory not found: {log_dir}")
        return analyzed_errors
        
    for filename in os.listdir(log_dir):
        if filename.endswith("-error.log"):
            file_path = os.path.join(log_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # Simple heuristic for plain text error (no JSON structure)
                        if not line.startswith("{"):
                            analysis = analyze_plain_text_error(line, source=file_path)
                            analyzed_errors.append(analysis)
            except Exception as e:
                logger.error(f"Failed to read log file {file_path}: {str(e)}")
                
    return analyzed_errors

def mitigate_plain_text_error(error_analysis: Dict[str, Any]) -> bool:
    """
    Attempts to mitigate a plain text error based on its analysis.
    
    Args:
        error_analysis (Dict[str, Any]): The analysis of the error.
        
    Returns:
        bool: True if mitigation was successful or not required, False otherwise.
    """
    if not error_analysis.get("action_required"):
        return True
        
    logger.info(f"Mitigating error from {error_analysis['source']}: {error_analysis['original_message']}")
    logger.info(f"Recommendation: {error_analysis['recommendation']}")
    
    # Handle generic "raise error" to prevent system crash loops
    if "raise error" in error_analysis["original_message"].lower():
        logger.warning("Intercepted generic 'raise error'. Suppressing exception propagation.")
        return True
    
    # In a real system, this might trigger an alert, create a ticket, or attempt auto-remediation
    if error_analysis["severity"] == "high":
        logger.error("High severity error detected. Escalating to human operator.")
        return False
        
    return True