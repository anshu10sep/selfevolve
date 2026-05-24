import socket
import logging
import time
import requests
from typing import Dict, Any, List
from functools import wraps

logger = logging.getLogger(__name__)

def retry_network_check(max_retries=3, backoff_factor=2):
    """
    Decorator to retry system audit network checks on temporary DNS/network failures.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (socket.gaierror, requests.exceptions.RequestException) as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"System audit network check failed after {max_retries} retries: {e}")
                        return {"status": "error", "message": str(e)}
                    sleep_time = backoff_factor ** retries
                    logger.warning(f"Audit network error: {e}. Retrying in {sleep_time}s... ({retries}/{max_retries})")
                    time.sleep(sleep_time)
        return wrapper
    return decorator

class SystemAuditor:
    """
    Skill for Jarvis to perform system audits, including checking external connectivity
    robustly against DNS and network failures.
    """
    
    @retry_network_check(max_retries=3, backoff_factor=2)
    def check_external_service(self, url: str) -> Dict[str, Any]:
        """Check if an external service is reachable."""
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return {"status": "ok", "url": url, "status_code": response.status_code}

    def audit_dns_resolution(self, hostname: str) -> Dict[str, Any]:
        """Audit DNS resolution for a specific hostname."""
        try:
            ip_address = socket.gethostbyname(hostname)
            return {"status": "ok", "hostname": hostname, "ip": ip_address}
        except socket.gaierror as e:
            logger.error(f"DNS resolution failed for {hostname}: {e}")
            return {"status": "error", "hostname": hostname, "message": str(e)}

    def run_full_audit(self, services_to_check: List[str]) -> Dict[str, Any]:
        """Run a full system audit including network checks."""
        results = {}
        for service in services_to_check:
            results[service] = self.check_external_service(service)
        return results

def run_system_audit(services: List[str] = None) -> Dict[str, Any]:
    """Helper function to run a system audit."""
    if services is None:
        services = [
            "https://api.github.com", 
            "https://api.openai.com",
            "https://1.1.1.1"
        ]
    auditor = SystemAuditor()
    return auditor.run_full_audit(services)