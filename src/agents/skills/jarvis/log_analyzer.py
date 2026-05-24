import os
import re
import json
from typing import List, Dict, Any

def parse_log_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a log file and extract structured information.
    Gracefully handles both structured JSON logs and plain text tracebacks.
    """
    if not os.path.exists(file_path):
        return []

    parsed_logs = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return [{"type": "error", "message": f"Failed to read log file: {str(e)}", "source": file_path}]

    current_traceback = []
    in_traceback = False

    for line in lines:
        clean_line = line.strip()
        if not clean_line:
            continue

        # Detect the start of a Python traceback
        if "Traceback (most recent call last):" in clean_line:
            if in_traceback and current_traceback:
                # Save previous traceback if we somehow started a new one unexpectedly
                parsed_logs.append({
                    "type": "plain_text_error",
                    "message": "\n".join(current_traceback),
                    "source": file_path
                })
            in_traceback = True
            current_traceback = [clean_line]
            continue

        if in_traceback:
            # Check if the line looks like part of a traceback
            is_traceback_line = (
                clean_line.startswith("File ") or 
                clean_line.startswith("line ") or 
                clean_line.startswith("^") or 
                clean_line.startswith("~") or 
                "Error:" in clean_line or 
                "Exception:" in clean_line or 
                line.startswith("  ")
            )
            
            if is_traceback_line:
                current_traceback.append(clean_line)
                # If it's the actual error message line (e.g., ValueError: ...), it's usually the end
                if re.match(r'^[A-Za-z0-9_.]+(?:Error|Exception):', clean_line):
                    parsed_logs.append({
                        "type": "plain_text_error",
                        "message": "\n".join(current_traceback),
                        "source": file_path
                    })
                    in_traceback = False
                    current_traceback = []
            else:
                # Traceback ended unexpectedly, save what we have
                parsed_logs.append({
                    "type": "plain_text_error",
                    "message": "\n".join(current_traceback),
                    "source": file_path
                })
                in_traceback = False
                current_traceback = []
                
        if not in_traceback:
            try:
                # Attempt to parse as structured JSON log
                log_entry = json.loads(clean_line)
                parsed_logs.append(log_entry)
            except json.JSONDecodeError:
                # Plain text log that is not a traceback
                parsed_logs.append({
                    "type": "info",
                    "message": clean_line,
                    "source": file_path
                })

    # Catch any trailing traceback at the end of the file
    if in_traceback and current_traceback:
        parsed_logs.append({
            "type": "plain_text_error",
            "message": "\n".join(current_traceback),
            "source": file_path
        })

    return parsed_logs

def analyze_logs(log_directory: str) -> Dict[str, Any]:
    """
    Analyze all logs in a directory and summarize errors and tracebacks.
    """
    summary = {
        "total_errors": 0,
        "error_types": {},
        "tracebacks": [],
        "files_scanned": 0
    }
    
    if not os.path.exists(log_directory):
        return summary

    for filename in os.listdir(log_directory):
        if filename.endswith(".log"):
            file_path = os.path.join(log_directory, filename)
            summary["files_scanned"] += 1
            logs = parse_log_file(file_path)
            
            for log in logs:
                if isinstance(log, dict):
                    log_type = log.get("type", "unknown")
                    if log_type in ["error", "plain_text_error"] or log.get("level", "").lower() == "error":
                        summary["total_errors"] += 1
                        summary["error_types"][log_type] = summary["error_types"].get(log_type, 0) + 1
                        
                        if log_type == "plain_text_error":
                            summary["tracebacks"].append({
                                "source": log.get("source", file_path),
                                "message": log.get("message", "")
                            })
                            
    return summary