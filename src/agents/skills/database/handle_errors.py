import logging
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)

def with_db_error_handling(exceptions: tuple = (Exception,), default_return: Any = None) -> Callable:
    """
    A decorator to handle database-related errors gracefully.
    
    Args:
        exceptions (tuple): A tuple of exception classes to catch.
        default_return (Any): The value to return if an exception is caught.
        
    Returns:
        Callable: The decorated function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.error(f"Database error in {func.__name__}: {str(e)}")
                return default_return
        return wrapper
    return decorator

class DatabaseErrorHandler:
    """
    Utility class for handling and logging database connection and query errors.
    """
    
    @staticmethod
    def log_connection_error(db_type: str, host: str, port: int, error: Exception) -> None:
        """
        Log a database connection error with standard formatting.
        
        Args:
            db_type (str): The type of database (e.g., 'Redis', 'PostgreSQL').
            host (str): The host address.
            port (int): The port number.
            error (Exception): The exception that was raised.
        """
        logger.error(f"[{db_type}] Connection failed to {host}:{port}. Error: {error}")
        
    @staticmethod
    def is_recoverable(error: Exception) -> bool:
        """
        Determine if a database error is potentially recoverable (e.g., connection timeout).
        
        Args:
            error (Exception): The exception to evaluate.
            
        Returns:
            bool: True if the error is recoverable, False otherwise.
        """
        error_str = str(error).lower()
        recoverable_keywords = ['timeout', 'connection refused', 'network is unreachable', 'reset by peer', 'error 111']
        
        return any(keyword in error_str for keyword in recoverable_keywords)