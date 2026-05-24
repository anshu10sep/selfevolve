import subprocess
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class InfrastructureManager:
    """
    Manages system infrastructure services like Redis and PostgreSQL.
    Provides methods to check status and start services if they are down.
    """
    
    @staticmethod
    def check_service_status(service_name: str) -> bool:
        """
        Check if a system service is running.
        
        Args:
            service_name (str): The name of the service to check.
            
        Returns:
            bool: True if the service is active and running, False otherwise.
        """
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                check=False
            )
            return result.stdout.strip() == "active"
        except Exception as e:
            logger.error(f"Failed to check status for {service_name}: {e}")
            # Fallback for systems without systemctl (like some Docker containers)
            try:
                if service_name in ["redis", "redis-server"]:
                    result = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True, check=False)
                    return "PONG" in result.stdout
                elif service_name == "postgresql":
                    result = subprocess.run(["pg_isready"], capture_output=True, text=True, check=False)
                    return result.returncode == 0
            except Exception as fallback_e:
                logger.error(f"Fallback status check failed for {service_name}: {fallback_e}")
            return False

    @staticmethod
    def start_service(service_name: str) -> bool:
        """
        Attempt to start a system service.
        
        Args:
            service_name (str): The name of the service to start.
            
        Returns:
            bool: True if the service was successfully started, False otherwise.
        """
        try:
            logger.info(f"Attempting to start service: {service_name}")
            result = subprocess.run(
                ["sudo", "systemctl", "start", service_name],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.info(f"Successfully started {service_name}")
                return True
            else:
                logger.error(f"Failed to start {service_name}: {result.stderr}")
                
                # Fallback for non-systemd environments
                if service_name in ["redis", "redis-server"]:
                    logger.info("Attempting fallback start for Redis...")
                    fb_result = subprocess.run(["redis-server", "--daemonize", "yes"], capture_output=True, text=True, check=False)
                    return fb_result.returncode == 0
                    
                return False
        except Exception as e:
            logger.error(f"Exception while starting {service_name}: {e}")
            return False

    @classmethod
    def ensure_infrastructure_services(cls) -> Dict[str, Any]:
        """
        Ensure that required infrastructure services (Redis, PostgreSQL) are running.
        
        Returns:
            Dict[str, Any]: A dictionary containing the status of each service.
        """
        services = ["redis", "postgresql"]
        status_report = {}
        
        for service in services:
            svc_name = service
            if service == "redis" and not cls.check_service_status("redis"):
                if cls.check_service_status("redis-server"):
                    svc_name = "redis-server"
                    
            is_running = cls.check_service_status(svc_name)
            if not is_running:
                logger.warning(f"Service {svc_name} is not running. Attempting to start...")
                started = cls.start_service(svc_name)
                status_report[service] = {
                    "running": started,
                    "action_taken": "started" if started else "failed_to_start"
                }
            else:
                status_report[service] = {
                    "running": True,
                    "action_taken": "none"
                }
                
        return status_report