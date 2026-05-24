import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class GlobalErrorHandler:
    """
    Global error handler for Jarvis to process and categorize system errors.
    """
    
    def __init__(self):
        self.error_patterns = {
            "connection_failed": re.compile(r"Connect call failed\s+(.+)"),
            "connection_refused": re.compile(r"Connection refused", re.IGNORECASE),
            "timeout": re.compile(r"Timeout|timed out", re.IGNORECASE),
            "auth_failed": re.compile(r"Authentication failed|Unauthorized|401|403", re.IGNORECASE),
            "not_found": re.compile(r"Not found|404", re.IGNORECASE)
        }

    def parse_error_log(self, log_message: str) -> Dict[str, Any]:
        """
        Parse an error log message to extract meaningful information.
        
        Args:
            log_message: The raw error log message.
            
        Returns:
            A dictionary with parsed error details.
        """
        result = {
            "category": "unknown",
            "target": None,
            "raw_message": log_message,
            "action_required": True
        }
        
        for category, pattern in self.error_patterns.items():
            match = pattern.search(log_message)
            if match:
                result["category"] = category
                if category == "connection_failed" and match.groups():
                    result["target"] = match.group(1).strip()
                break
                
        return result

    def handle_error(self, error: Exception, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Handle an exception and determine the appropriate response.
        
        Args:
            error: The exception that occurred.
            context: Optional context where the error occurred.
            
        Returns:
            A dictionary containing the handling strategy.
        """
        error_msg = str(error)
        parsed = self.parse_error_log(error_msg)
        
        strategy = {
            "log_level": logging.ERROR,
            "retry_recommended": False,
            "alert_admin": False,
            "parsed_info": parsed,
            "context": context
        }
        
        if parsed["category"] in ["connection_failed", "connection_refused", "timeout"]:
            strategy["retry_recommended"] = True
            strategy["alert_admin"] = True
            logger.error(f"Network error detected in {context or 'unknown context'}: {error_msg}")
        elif parsed["category"] == "auth_failed":
            strategy["alert_admin"] = True
            logger.critical(f"Authentication error detected in {context or 'unknown context'}: {error_msg}")
        else:
            logger.error(f"Unhandled error in {context or 'unknown context'}: {error_msg}")
            
        return strategy

def process_system_error(error_message: str, source: str) -> None:
    """
    Process a system error reported by the bug scanner.
    
    Args:
        error_message: The error message.
        source: The source file or component.
    """
    handler = GlobalErrorHandler()
    parsed = handler.parse_error_log(error_message)
    
    if parsed["category"] == "connection_failed":
        target = parsed.get("target", "unknown address")
        logger.warning(f"System Error Processed: Connection failed to {target} in {source}. "
                       f"Recommendation: Implement retry logic and verify service availability.")
    else:
        logger.warning(f"System Error Processed: {error_message} in {source}")