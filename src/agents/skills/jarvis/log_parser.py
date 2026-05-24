import re
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def parse_log_line(line: str) -> Dict[str, Any]:
    """
    Parses a single log line into a structured dictionary.
    Supports JSON logs and standard plain text logs.
    
    Args:
        line (str): The log line to parse.
        
    Returns:
        Dict[str, Any]: Structured log data.
    """
    line = line.strip()
    
    # Try JSON parsing first for structured logs
    if line.startswith('{') and line.endswith('}'):
        try:
            data = json.loads(line)
            data["is_plain_text"] = False
            return data
        except json.JSONDecodeError:
            pass
            
    # Fallback to regex for standard log formats
    # Example: 2026-05-24T16:45:18.905276+00:00 [ERROR] Component: unknown - Message
    pattern = r'^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?\s*(?:\[(?P<level>[A-Z]+)\])?\s*(?P<message>.*)$'
    match = re.match(pattern, line)
    
    if match:
        data = match.groupdict()
        return {
            "timestamp": data.get("timestamp"),
            "level": data.get("level") or "UNKNOWN",
            "message": data.get("message", line),
            "is_plain_text": True
        }
        
    # Ultimate fallback for completely unstructured plain text
    return {
        "timestamp": None,
        "level": "UNKNOWN",
        "message": line,
        "is_plain_text": True
    }

def extract_errors(log_lines: List[str]) -> List[Dict[str, Any]]:
    """
    Extracts only the error entries from a list of log lines.
    
    Args:
        log_lines (List[str]): List of raw log lines.
        
    Returns:
        List[Dict[str, Any]]: List of parsed error logs.
    """
    errors = []
    for line in log_lines:
        if not line.strip():
            continue
            
        parsed = parse_log_line(line)
        
        # Identify errors based on level or keywords in the message
        is_error_level = parsed.get("level") in ["ERROR", "CRITICAL", "FATAL"]
        has_error_keyword = "error" in str(parsed.get("message", "")).lower()
        
        if is_error_level or has_error_keyword:
            errors.append(parsed)
            
    return errors