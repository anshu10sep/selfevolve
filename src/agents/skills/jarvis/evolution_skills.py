import time
import logging
import socket
import requests
from requests.exceptions import RequestException
from typing import Dict, Any, Optional, Callable
from functools import wraps

logger = logging.getLogger(__name__)

def with_network_retry(max_retries: int = 5, backoff_factor: float = 2.0):
    """
    Decorator to retry network operations with exponential backoff.
    Specifically handles DNS resolution errors like [Errno -3] Temporary failure in name resolution.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (socket.gaierror, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    retries += 1
                    wait_time = backoff_factor ** retries
                    logger.warning(
                        f"Network error in {func.__name__}: {e}. "
                        f"Retry {retries}/{max_retries} in {wait_time}s..."
                    )
                    if retries >= max_retries:
                        logger.error(f"Max retries reached for {func.__name__}. Failing with error: {e}")
                        raise
                    time.sleep(wait_time)
                except Exception as e:
                    logger.error(f"Unexpected error in {func.__name__}: {e}")
                    raise
        return wrapper
    return decorator

class EvolutionManager:
    """
    Manages the continuous evolution process for the SelfEvolve system.
    Includes robust error handling for network and DNS resolution issues.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.evolution_api = self.config.get("evolution_api", "https://api.github.com/repos/self-evolve/core")
        self.session = requests.Session()
        
        # Configure session with retries at the urllib3 level as a fallback
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @with_network_retry(max_retries=5, backoff_factor=2.0)
    def fetch_evolution_state(self) -> Dict[str, Any]:
        """
        Fetches the current state required for continuous evolution.
        """
        logger.info(f"Fetching evolution state from {self.evolution_api}")
        response = self.session.get(f"{self.evolution_api}/commits", timeout=15)
        response.raise_for_status()
        return {"commits": response.json()}

    @with_network_retry(max_retries=5, backoff_factor=2.0)
    def push_evolution_metrics(self, metrics: Dict[str, Any]) -> bool:
        """
        Pushes evolution metrics to the remote repository or tracking service.
        """
        endpoint = self.config.get("metrics_endpoint", "https://api.selfevolve.local/metrics")
        logger.info(f"Pushing evolution metrics to {endpoint}")
        response = self.session.post(endpoint, json=metrics, timeout=15)
        response.raise_for_status()
        return True

    def run_continuous_evolution(self) -> bool:
        """
        Main entry point for the continuous evolution process.
        Catches all exceptions to prevent the main loop from crashing.
        """
        try:
            logger.info("Starting continuous evolution cycle...")
            
            # 1. Fetch latest state
            state = self.fetch_evolution_state()
            logger.info(f"Successfully fetched evolution state. Found {len(state.get('commits', []))} commits.")
            
            # 2. Perform evolution logic (placeholder)
            metrics = {
                "status": "success",
                "commits_processed": len(state.get('commits', [])),
                "timestamp": time.time()
            }
            
            # 3. Push metrics
            try:
                self.push_evolution_metrics(metrics)
            except Exception as e:
                logger.warning(f"Failed to push metrics, but evolution cycle continues: {e}")
            
            logger.info("Continuous evolution cycle completed successfully.")
            return True
            
        except socket.gaierror as e:
            logger.error(f"continuous_evolution_failed: [Errno -3] Temporary failure in name resolution: {e}")
            return False
        except Exception as e:
            logger.error(f"continuous_evolution_failed: {e}")
            return False

def trigger_evolution(config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Helper function to trigger the evolution process.
    """
    manager = EvolutionManager(config)
    return manager.run_continuous_evolution()