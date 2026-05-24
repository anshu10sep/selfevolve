import logging
from functools import wraps
import redis

logger = logging.getLogger(__name__)

def handle_redis_errors(default_return=None):
    """
    A decorator to catch and handle Redis connection errors gracefully.
    This prevents the application from crashing due to temporary Redis unavailability.
    
    Args:
        default_return: The value to return if a Redis error occurs.
        
    Returns:
        Function wrapper.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except redis.exceptions.ConnectionError as e:
                logger.error(f"Redis ConnectionError in {func.__name__}: {e}")
                return default_return
            except redis.exceptions.TimeoutError as e:
                logger.error(f"Redis TimeoutError in {func.__name__}: {e}")
                return default_return
            except redis.exceptions.RedisError as e:
                logger.error(f"Redis Error in {func.__name__}: {e}")
                return default_return
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                raise
        return wrapper
    return decorator