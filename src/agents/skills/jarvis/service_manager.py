import subprocess
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class ServiceManager:
    """
    Manages system services like Redis and PostgreSQL to ensure infrastructure is running.
    """
    
    @staticmethod
    def check_service_status(service_name: str) -> bool:
        """
        Check if a system service is running.
        
        Args:
            service_name: The name of the service (e.g., 'redis', 'postgresql').
            
        Returns:
            True if the service is active and running, False otherwise.
        """
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service_name],
                capture_output=True,
                text=True,
                check=False
            )
            return result.stdout.strip() == 'active'
        except Exception as e:
            logger.error(f"Error checking status for service {service_name}: {e}")
            return False

    @staticmethod
    def start_service(service_name: str) -> bool:
        """
        Start a system service.
        
        Args:
            service_name: The name of the service to start.
            
        Returns:
            True if the service was started successfully, False otherwise.
        """
        try:
            logger.info(f"Attempting to start service: {service_name}")
            result = subprocess.run(
                ['sudo', 'systemctl', 'start', service_name],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.info(f"Successfully started service: {service_name}")
                return True
            else:
                logger.error(f"Failed to start service {service_name}. Error: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Exception while starting service {service_name}: {e}")
            return False

    @staticmethod
    def ensure_services_running(services: List[str]) -> Dict[str, str]:
        """
        Ensure that a list of services are running.
        
        Args:
            services: A list of service names to check and start.
            
        Returns:
            A dictionary mapping service names to their status ('running' or 'failed').
        """
        status_report = {}
        
        for service in services:
            is_running = ServiceManager.check_service_status(service)
            if not is_running:
                logger.warning(f"Service {service} is not running. Attempting to start...")
                started = ServiceManager.start_service(service)
                status_report[service] = 'running' if started else 'failed'
            else:
                status_report[service] = 'running'
                
        return status_report

def ensure_infrastructure() -> Dict[str, str]:
    """
    Convenience function to ensure Redis and PostgreSQL are running.
    
    Returns:
        A dictionary with the status of the infrastructure services.
    """
    services_to_check = ['redis', 'redis-server', 'postgresql']
    return ServiceManager.ensure_services_running(services_to_check)