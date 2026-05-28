import os
import subprocess
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def verify_dns_resolution(domain: str = "api.telegram.org") -> bool:
    """
    Verify DNS resolution using dig or nslookup.
    
    Args:
        domain (str): The domain to resolve. Defaults to api.telegram.org.
        
    Returns:
        bool: True if resolution succeeds, False otherwise.
    """
    try:
        # Try dig
        result = subprocess.run(
            ["dig", "+short", domain],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
            
        # Fallback to nslookup
        result = subprocess.run(
            ["nslookup", domain],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0 and "Address:" in result.stdout:
            return True
            
    except Exception as e:
        logger.error(f"Error verifying DNS resolution: {e}")
        
    return False

def check_resolv_conf() -> List[str]:
    """
    Check /etc/resolv.conf for valid nameservers.
    
    Returns:
        List[str]: A list of configured nameservers.
    """
    nameservers = []
    try:
        if os.path.exists("/etc/resolv.conf"):
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) > 1:
                            nameservers.append(parts[1])
    except Exception as e:
        logger.error(f"Error reading /etc/resolv.conf: {e}")
    return nameservers

def repair_dns() -> bool:
    """
    Repair DNS by adding 8.8.8.8 and 1.1.1.1 to /etc/resolv.conf and restarting network.
    
    Returns:
        bool: True if repair was successful or not needed, False otherwise.
    """
    reliable_ns = ["8.8.8.8", "1.1.1.1"]
    current_ns = check_resolv_conf()
    
    # Check if we need to add them
    missing_ns = [ns for ns in reliable_ns if ns not in current_ns]
    
    if not missing_ns:
        logger.info("Reliable nameservers already present.")
        return True
        
    try:
        # Try to append to resolv.conf
        if os.access("/etc/resolv.conf", os.W_OK):
            with open("/etc/resolv.conf", "a") as f:
                for ns in missing_ns:
                    f.write(f"\nnameserver {ns}\n")
        else:
            # Try with sudo
            ns_lines = "\n".join([f"nameserver {ns}" for ns in missing_ns])
            cmd = f"echo '{ns_lines}' | sudo tee -a /etc/resolv.conf"
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
        # Restart network services
        subprocess.run(["sudo", "systemctl", "restart", "systemd-resolved"], 
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        return True
    except Exception as e:
        logger.error(f"Failed to repair DNS: {e}")
        return False

def diagnose_and_fix_network() -> Dict[str, Any]:
    """
    Diagnose network DNS issues and fix them.
    
    Returns:
        Dict[str, Any]: A report containing the diagnosis and repair status.
    """
    report = {
        "initial_dns_ok": False,
        "initial_nameservers": [],
        "repair_attempted": False,
        "repair_successful": False,
        "final_dns_ok": False
    }
    
    report["initial_dns_ok"] = verify_dns_resolution()
    report["initial_nameservers"] = check_resolv_conf()
    
    if not report["initial_dns_ok"]:
        logger.warning("DNS resolution failed. Attempting repair...")
        report["repair_attempted"] = True
        report["repair_successful"] = repair_dns()
        report["final_dns_ok"] = verify_dns_resolution()
    else:
        logger.info("DNS resolution is working correctly.")
        report["final_dns_ok"] = True
        
    return report