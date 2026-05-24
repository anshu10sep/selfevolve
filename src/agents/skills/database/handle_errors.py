import logging
import psycopg2
from psycopg2 import OperationalError, ProgrammingError, IntegrityError, DataError
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

def handle_db_errors(func: Callable) -> Callable:
    """
    Decorator to handle database errors gracefully and log them appropriately.
    
    Args:
        func (Callable): The function to wrap.
        
    Returns:
        Callable: The wrapped function.
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except OperationalError as e:
            logger.error(f"OperationalError in {func.__name__}: {e}")
            # This includes connection errors like [Errno 111] Connect call failed
            raise
        except IntegrityError as e:
            logger.error(f"IntegrityError in {func.__name__}: {e}")
            raise
        except DataError as e:
            logger.error(f"DataError in {func.__name__}: {e}")
            raise
        except ProgrammingError as e:
            logger.error(f"ProgrammingError in {func.__name__}: {e}")
            raise
        except psycopg2.Error as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise
    return wrapper

def is_connection_error(error: Exception) -> bool:
    """
    Check if an error is a connection error (e.g., Errno 111).
    
    Args:
        error (Exception): The error to check.
        
    Returns:
        bool: True if it's a connection error, False otherwise.
    """
    if isinstance(error, OperationalError):
        error_msg = str(error).lower()
        if "connect call failed" in error_msg or "connection refused" in error_msg:
            return True
    return False