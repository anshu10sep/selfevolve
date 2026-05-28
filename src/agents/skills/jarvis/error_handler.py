import logging
import socket
import requests
from typing import Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

def safe_execute(default_return: Any = None, log_level: int = logging.ERROR) -> Callable:
    """
    A decorator to safely execute a function, catching common network and system errors.
    Returns `default_return` if an exception occurs.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except socket.gaierror as e:
                logger.log(log_level, f"[{func.__name__}] DNS Resolution Error (Errno -3): {e}")
                return default_return
            except requests.exceptions.ConnectionError as e:
                logger.log(log_level, f"[{func.__name__}] Connection Error: {e}")
                return default_return
            except requests.exceptions.Timeout as e:
                logger.log(log_level, f"[{func.__name__}] Timeout Error: {e}")
                return default_return
            except requests.exceptions.RequestException as e:
                logger.log(log_level, f"[{func.__name__}] HTTP Request Error: {e}")
                return default_return
            except Exception as e:
                logger.log(log_level, f"[{func.__name__}] Unexpected Error: {e}")
                return default_return
        return wrapper
    return decorator

class ErrorHandler:
    """
    Centralized error handling utility for Jarvis.
    """
    
    @staticmethod
    def handle_network_error(error: Exception, context: str) -> None:
        """
        Logs network errors with appropriate severity and context.
        """
        if isinstance(error, socket.gaierror):
            logger.error(f"[{context}] Temporary failure in name resolution: {error}")
        elif isinstance(error, requests.exceptions.ConnectionError):
            logger.error(f"[{context}] Failed to establish a connection: {error}")
        elif isinstance(error, requests.exceptions.Timeout):
            logger.error(f"[{context}] Request timed out: {error}")
        else:
            logger.error(f"[{context}] Network operation failed: {error}")

    @staticmethod
    def is_recoverable(error: Exception) -> bool:
        """
        Determines if an error is likely recoverable via retries.
        """
        recoverable_exceptions = (
            socket.gaierror,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError
        )
        return isinstance(error, recoverable_exceptions)