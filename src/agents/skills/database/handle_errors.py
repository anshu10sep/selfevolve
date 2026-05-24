import logging
from functools import wraps

try:
    import psycopg2
except ImportError:
    raise ImportError("psycopg2 is required for database connections. Please install it using 'pip install psycopg2-binary'")

logger = logging.getLogger(__name__)

def with_error_handling(func):
    """
    Decorator to handle database errors gracefully.
    Catches specific psycopg2 exceptions and logs them with context before re-raising.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except psycopg2.OperationalError as e:
            logger.error(f"OperationalError in {func.__name__}: {e}. This may indicate a connection issue or database server downtime.")
            raise
        except psycopg2.ProgrammingError as e:
            logger.error(f"ProgrammingError in {func.__name__}: {e}. Check your SQL syntax and table structures.")
            raise
        except psycopg2.IntegrityError as e:
            logger.error(f"IntegrityError in {func.__name__}: {e}. This is usually caused by a constraint violation (e.g., duplicate key).")
            raise
        except psycopg2.DataError as e:
            logger.error(f"DataError in {func.__name__}: {e}. Invalid data type or value passed to the database.")
            raise
        except Exception as e:
            logger.error(f"Unexpected database error in {func.__name__}: {e}")
            raise
    return wrapper

class DatabaseErrorHandler:
    """
    Utility class for handling and categorizing database errors.
    """
    @staticmethod
    def log_and_raise(error, context=""):
        """
        Log the error with context and re-raise.
        
        :param error: The exception object
        :param context: Additional context about where/why the error occurred
        """
        logger.error(f"Database error [{context}]: {error}")
        raise error
        
    @staticmethod
    def is_connection_error(error):
        """
        Determine if the error is related to a connection failure.
        
        :param error: The exception object
        :return: True if it's a connection error, False otherwise
        """
        if isinstance(error, psycopg2.OperationalError):
            error_msg = str(error).lower()
            return "connection refused" in error_msg or "could not connect to server" in error_msg
        return False