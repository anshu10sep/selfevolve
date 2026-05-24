import os
import platform
import psutil
from typing import Dict, Any

def perform_system_audit() -> Dict[str, Any]:
    """
    Perform a basic system audit to check resources and environment.
    Useful for diagnosing environment-related errors.
    """
    audit_results = {
        "os": platform.system(),
        "os_release": platform.release(),
        "python_version": platform.python_version(),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "disk_total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
        "disk_free_gb": round(psutil.disk_usage('/').free / (1024**3), 2),
        "status": "healthy"
    }
    
    if audit_results["memory_available_gb"] < 1.0:
        audit_results["status"] = "warning"
        audit_results["warning_reason"] = "Low memory available"
        
    if audit_results["disk_free_gb"] < 5.0:
        audit_results["status"] = "warning"
        audit_results["warning_reason"] = "Low disk space"
        
    return audit_results

def check_log_directory_health(log_dir: str) -> Dict[str, Any]:
    """
    Check the health and size of the log directory to ensure logs 
    are not growing uncontrollably due to spamming errors.
    """
    if not os.path.exists(log_dir):
        return {"status": "error", "message": f"Log directory {log_dir} does not exist"}
        
    total_size = 0
    file_count = 0
    
    for root, _, files in os.walk(log_dir):
        for file in files:
            if file.endswith(".log"):
                file_count += 1
                file_path = os.path.join(root, file)
                total_size += os.path.getsize(file_path)
                
    size_mb = round(total_size / (1024 * 1024), 2)
    
    return {
        "status": "healthy" if size_mb < 500 else "warning",
        "log_directory": log_dir,
        "file_count": file_count,
        "total_size_mb": size_mb
    }