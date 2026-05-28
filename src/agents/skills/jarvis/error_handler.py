import logging
import socket
import time
from typing import Callable, Any
from functools import wraps
import requests

logger = logging.getLogger(__name__)

def handle_network_errors(max_retries: int = 5, backoff_factor: float = 2.0) -> Callable:
    """
    A decorator to handle network errors, specifically DNS resolution failures like
    '[Errno -3] Temporary failure in name resolution'.
    
    Args:
        max_retries (int): Maximum number of times to retry the function.
        backoff_factor (float): Multiplier for exponential backoff sleep time.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            retries = 0
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                except (socket.gaierror, requests.exceptions.RequestException, ConnectionError) as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(f"Network error in {func.__name__} after {max_retries} retries: {e}")
                        raise
                    sleep_time = backoff_factor ** retries
                    logger.warning(f"Network error in {func.__name__}: {e}. Retrying in {sleep_time}s... ({retries}/{max_retries})")
                    time.sleep(sleep_time)
                except Exception as e:
                    # Catch generic exceptions that might wrap the underlying socket error string
                    if "[Errno -3]" in str(e) or "Temporary failure in name resolution" in str(e):
                        retries += 1
                        if retries > max_retries:
                            logger.error(f"DNS error in {func.__name__} after {max_retries} retries: {e}")
                            raise
                        sleep_time = backoff_factor ** retries
                        logger.warning(f"DNS resolution error in {func.__name__}: {e}. Retrying in {sleep_time}s... ({retries}/{max_retries})")
                        time.sleep(sleep_time)
                    else:
                        raise
        return wrapper
    return decorator

class ErrorHandler:
    """
    Centralized error handling for the Jarvis agent.
    """
    @staticmethod
    def log_error(component: str, event: str, message: str, exc_info: bool = True):
        logger.error(f"[{component}] {event}: {message}", exc_info=exc_info)

    @staticmethod
    def is_transient_error(error_message: str) -> bool:
        transient_indicators = [
            "[Errno -3]",
            "Temporary failure in name resolution",
            "Connection reset by peer",
            "Timeout",
            "502 Bad Gateway",
            "503 Service Unavailable",
            "504 Gateway Timeout"
        ]
        return any(indicator in error_message for indicator in transient_indicators)