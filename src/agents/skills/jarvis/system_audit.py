import logging
import traceback
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def perform_system_audit(directory: str = ".") -> Dict[str, Any]:
    """
    Perform a system audit on the given directory.
    Catches exceptions to avoid plain text errors in logs.
    
    Args:
        directory (str): The root directory to audit.
        
    Returns:
        dict: Audit results including status and scanned file count.
    """
    audit_results = {
        "status": "success",
        "scanned_files": 0,
        "errors": []
    }
    
    try:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    audit_results["scanned_files"] += 1
                    # Simulated audit logic per file
                    
    except Exception as e:
        logger.error(f"System audit failed: {str(e)}")
        logger.debug(traceback.format_exc())
        audit_results["status"] = "failed"
        audit_results["errors"].append(str(e))
        
    return audit_results

def parse_error_logs(log_file_path: str) -> List[str]:
    """
    Parse error logs to identify tracebacks and plain text errors.
    
    Args:
        log_file_path (str): Path to the log file.
        
    Returns:
        list: A list of extracted error traces.
    """
    errors = []
    try:
        if not os.path.exists(log_file_path):
            logger.warning(f"Log file not found: {log_file_path}")
            return errors
            
        with open(log_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines):
            if "Traceback (most recent call last):" in line:
                error_trace = "".join(lines[i:i+15]) # Capture traceback context
                errors.append(error_trace)
                
    except Exception as e:
        logger.error(f"Error parsing log file {log_file_path}: {str(e)}")
        logger.debug(traceback.format_exc())
        
    return errors