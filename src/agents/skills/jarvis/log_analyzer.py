import os
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def analyze_error_log(log_file_path: str) -> List[Dict[str, Any]]:
    """
    Analyzes an error log file to identify plain text errors and extract surrounding context.
    
    Args:
        log_file_path (str): Path to the log file.
        
    Returns:
        List[Dict[str, Any]]: A list of extracted error events with context.
    """
    if not os.path.exists(log_file_path):
        logger.error(f"Log file not found: {log_file_path}")
        return []
        
    errors = []
    # Match common error indicators
    error_pattern = re.compile(r'(?i)(error|exception|traceback|fail|fatal)')
    
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines):
            if error_pattern.search(line):
                # Extract surrounding context (2 lines before, 2 lines after)
                start_idx = max(0, i - 2)
                end_idx = min(len(lines), i + 3)
                context = "".join(lines[start_idx:end_idx])
                
                # Flag specifically for the plain_text_error bug
                error_type = "plain_text_error" if "raise error" in line.lower() else "standard_error"
                
                errors.append({
                    "line_number": i + 1,
                    "message": line.strip(),
                    "context": context,
                    "type": error_type
                })
                
    except Exception as e:
        logger.error(f"Error reading log file {log_file_path}: {str(e)}")
        
    return errors

def generate_bug_report(error_data: Dict[str, Any]) -> str:
    """
    Generates a formatted bug report from parsed error data.
    
    Args:
        error_data (Dict[str, Any]): The parsed error data dictionary.
        
    Returns:
        str: A formatted bug report string ready for logging or ticketing.
    """
    report = f"BUG REPORT\n"
    report += f"==========\n"
    report += f"Type: {error_data.get('type', 'Unknown')}\n"
    report += f"Message: {error_data.get('message', 'No message provided')}\n"
    report += f"Line Number: {error_data.get('line_number', 'N/A')}\n"
    report += f"\nContext:\n{error_data.get('context', 'No context available')}\n"
    
    return report
