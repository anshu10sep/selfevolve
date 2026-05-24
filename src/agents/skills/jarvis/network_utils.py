import time
import socket
import logging
import requests

logger = logging.getLogger(__name__)

def robust_request(method: str, url: str, max_retries: int = 5, backoff_factor: float = 2.0, **kwargs) -> requests.Response:
    """
    Executes a network request with robust retry logic, specifically handling
    DNS resolution failures (socket.gaierror) and connection errors.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: The URL to request
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff
        **kwargs: Additional arguments to pass to requests.request
        
    Returns:
        requests.Response object
        
    Raises:
        requests.exceptions.RequestException: If the request fails after all retries
    """
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
            
        except (requests.exceptions.ConnectionError, socket.gaierror) as e:
            logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}) for {url}: {e}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to connect to {url} after {max_retries} attempts.")
                raise
            time.sleep(backoff_factor ** attempt)
            
        except requests.exceptions.Timeout as e:
            logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries}) for {url}: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff_factor ** attempt)
            
        except requests.exceptions.RequestException as e:
            # For 5xx server errors, we retry as they might be temporary
            if hasattr(e, 'response') and e.response is not None:
                if 500 <= e.response.status_code < 600:
                    logger.warning(f"Server error {e.response.status_code} (attempt {attempt + 1}/{max_retries}) for {url}")
                    if attempt < max_retries - 1:
                        time.sleep(backoff_factor ** attempt)
                        continue
            logger.error(f"HTTP Request exception: {e}")
            raise