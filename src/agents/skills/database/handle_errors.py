import logging
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)

def with_db_error_handling(fallback_value: Any = None) -> Callable:
    """
    A decorator to handle database-related errors gracefully.
    
    Args:
        fallback_value: The value to return if a database error occurs.
        
    Returns:
        A decorated function that catches and logs database errors.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                if 'connection refused' in error_msg or 'error 111' in error_msg:
                    logger.critical(f"Database connection refused in {func.__name__}. Is the service running? Error: {e}")
                elif 'timeout' in error_msg:
                    logger.error(f"Database timeout in {func.__name__}. Error: {e}")
                else:
                    logger.error(f"Database error in {func.__name__}: {e}")
                return fallback_value
        return wrapper
    return decorator

class DatabaseErrorHandler:
    """
    Utility class for handling and categorizing database errors.
    """
    
    @staticmethod
    def is_connection_error(error: Exception) -> bool:
        """
        Check if the exception is a connection error.
        
        Args:
            error: The exception to check.
            
        Returns:
            True if it's a connection error, False otherwise.
        """
        error_str = str(error).lower()
        return any(term in error_str for term in [
            'connection refused',
            'error 111',
            'connection reset',
            'broken pipe',
            'network is unreachable'
        ])
        
    @staticmethod
    def log_and_diagnose(error: Exception, context: str = "") -> None:
        """
        Log the error and provide a diagnosis if possible.
        
        Args:
            error: The exception that occurred.
            context: Additional context about where the error occurred.
        """
        prefix = f"[{context}] " if context else ""
        
        if DatabaseErrorHandler.is_connection_error(error):
            logger.critical(f"{prefix}Connection Error: {error}")
            logger.info("Diagnosis: The database service (e.g., Redis, PostgreSQL) may be down or inaccessible. "
                        "Action: Check if the service is running using 'systemctl status <service>' or 'docker ps'.")
        else:
            logger.error(f"{prefix}Unexpected Database Error: {error}")