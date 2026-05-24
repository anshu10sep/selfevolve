import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def handle_plain_text_error(error_message: str, source: str, timestamp: Optional[str] = None) -> Dict[str, Any]:
    """
    Handles plain text errors detected in logs, such as generic 'raise error' statements.
    
    Args:
        error_message (str): The error message extracted from the log.
        source (str): The source file or log where the error was detected.
        timestamp (str, optional): The timestamp of the error event.
        
    Returns:
        Dict[str, Any]: A dictionary containing the parsed error details and recommended actions.
    """
    logger.info(f"Handling plain text error from {source}: {error_message}")
    
    # Determine severity based on keywords
    severity = "high" if any(keyword in error_message.lower() for keyword in ["critical", "fatal"]) else "medium"
    
    # Determine recommended action
    action = "investigate"
    if "raise error" in error_message.lower():
        action = "scan_and_replace_generic_exceptions"
        
    return {
        "status": "processed",
        "source": source,
        "original_message": error_message,
        "timestamp": timestamp,
        "severity": severity,
        "recommended_action": action,
        "requires_human_intervention": severity == "high"
    }

def format_error_response(error_details: Dict[str, Any]) -> str:
    """
    Formats the processed error details into a readable response string.
    
    Args:
        error_details (Dict[str, Any]): The dictionary returned by handle_plain_text_error.
        
    Returns:
        str: A formatted summary of the error and the action to take.
    """
    return (
        f"Error Processed: {error_details['original_message']}\n"
        f"Source: {error_details['source']}\n"
        f"Severity: {error_details['severity'].upper()}\n"
        f"Action Required: {error_details['recommended_action']}"
    )
