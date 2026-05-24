import logging
import traceback
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def analyze_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Analyzes an exception and provides structured information about it,
    specifically identifying common infrastructure issues like Redis connection failures.
    
    Args:
        error (Exception): The exception to analyze.
        context (Dict, optional): Additional context about where the error occurred.
        
    Returns:
        Dict[str, Any]: Structured error analysis.
    """
    error_type = type(error).__name__
    error_msg = str(error)
    
    analysis = {
        "error_type": error_type,
        "message": error_msg,
        "traceback": traceback.format_exc(),
        "context": context or {},
        "severity": "high",
        "suggested_action": "investigate",
        "category": "general"
    }
    
    # Specific handling for Redis Connection Errors
    if "redis" in error_type.lower() or "redis" in error_msg.lower():
        if "Temporary failure in name resolution" in error_msg:
            analysis["severity"] = "critical"
            analysis["suggested_action"] = "Check DNS settings and ensure Redis container/service is running and accessible."
            analysis["category"] = "network_dns"
        elif "Connection refused" in error_msg:
            analysis["severity"] = "critical"
            analysis["suggested_action"] = "Ensure Redis server is started and listening on the correct port."
            analysis["category"] = "service_down"
        else:
            analysis["severity"] = "high"
            analysis["suggested_action"] = "Check Redis connection parameters and network connectivity."
            analysis["category"] = "database_connection"
            
    return analysis

def handle_system_error(error: Exception, component: str) -> Dict[str, Any]:
    """
    Main entry point for handling system errors. Logs the error appropriately
    based on its severity and returns the analysis.
    
    Args:
        error (Exception): The exception that occurred.
        component (str): The component where the error occurred.
        
    Returns:
        Dict[str, Any]: The error analysis result.
    """
    analysis = analyze_error(error, {"component": component})
    
    log_msg = f"[{analysis['severity'].upper()}] Error in {component}: {analysis['error_type']} - {analysis['message']}"
    
    if analysis["severity"] == "critical":
        logger.critical(log_msg)
        logger.critical(f"Suggested Action: {analysis['suggested_action']}")
    else:
        logger.error(log_msg)
        
    return analysis