import socket
import subprocess
import logging
import time
import os

logger = logging.getLogger(__name__)

def check_dns_resolution(domain: str = "api.telegram.org") -> bool:
    """
    Check if a domain can be resolved to an IP address.
    
    Args:
        domain (str): The domain name to resolve.
        
    Returns:
        bool: True if resolution is successful, False otherwise.
    """
    try:
        ip = socket.gethostbyname(domain)
        logger.info(f"Successfully resolved {domain} to {ip}")
        return True
    except socket.gaierror as e:
        logger.error(f"DNS resolution failed for {domain}: {e}")
        return False

def check_internet_connectivity(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> bool:
    """
    Check internet connectivity by attempting to connect to a known host.
    
    Args:
        host (str): The IP address to connect to.
        port (int): The port to connect to.
        timeout (int): Connection timeout in seconds.
        
    Returns:
        bool: True if connection is successful, False otherwise.
    """
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
        logger.info(f"Successfully connected to {host}:{port}")
        return True
    except socket.error as e:
        logger.error(f"Internet connectivity check failed: {e}")
        return False

def diagnose_network_issues() -> dict:
    """
    Diagnose network and DNS issues on the host machine.
    
    Returns:
        dict: A dictionary containing the diagnostic results.
    """
    results = {
        "dns_resolution_telegram": check_dns_resolution("api.telegram.org"),
        "dns_resolution_github": check_dns_resolution("github.com"),
        "internet_connectivity": check_internet_connectivity(),
        "resolv_conf": ""
    }
    
    try:
        if os.path.exists("/etc/resolv.conf"):
            with open("/etc/resolv.conf", "r") as f:
                results["resolv_conf"] = f.read()
        else:
            results["resolv_conf"] = "/etc/resolv.conf does not exist."
    except Exception as e:
        results["resolv_conf"] = f"Failed to read /etc/resolv.conf: {e}"
        
    return results

def escalate_to_devops(diagnostic_results: dict) -> None:
    """
    Escalate network issues to DevOps by logging a critical error and writing to an escalation file.
    
    Args:
        diagnostic_results (dict): The results from diagnose_network_issues.
    """
    logger.critical("ESCALATION TO DEVOPS: Network/DNS resolution failure detected.")
    logger.critical(f"Diagnostic Results: {diagnostic_results}")
    
    escalation_file = "/tmp/devops_escalation.log"
    try:
        with open(escalation_file, "a") as f:
            f.write(f"[{time.ctime()}] ESCALATION: Network/DNS failure.\n")
            f.write(f"Diagnostics: {diagnostic_results}\n")
            f.write("Action Required: Investigate host network and DNS settings.\n\n")
        logger.info(f"Escalation written to {escalation_file}")
    except Exception as e:
        logger.error(f"Failed to write escalation file: {e}")

def verify_and_repair_network() -> bool:
    """
    Verify network connectivity and attempt basic repair or escalate if it fails.
    
    Returns:
        bool: True if network is healthy, False if it failed and was escalated.
    """
    if check_dns_resolution("api.telegram.org") and check_internet_connectivity():
        logger.info("Network and DNS are functioning correctly.")
        return True
        
    logger.warning("Network or DNS issue detected. Running diagnostics...")
    diagnostics = diagnose_network_issues()
    
    # Attempt basic repair (e.g., restarting systemd-resolved if possible)
    try:
        logger.info("Attempting to restart systemd-resolved...")
        subprocess.run(["sudo", "-n", "systemctl", "restart", "systemd-resolved"], check=True, capture_output=True)
        time.sleep(2)
        
        if check_dns_resolution("api.telegram.org"):
            logger.info("Network recovery successful after restarting systemd-resolved.")
            return True
    except Exception as e:
        logger.error(f"Automated network recovery failed or is not permitted: {e}")
        
    # Escalate if repair fails
    escalate_to_devops(diagnostics)
    return False