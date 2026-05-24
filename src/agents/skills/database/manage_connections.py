import os
import time
import logging
import redis
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)

def get_redis_client(host=None, port=None, db=0, max_retries=5, backoff_factor=2):
    """
    Establishes a connection to Redis with retry logic for handling temporary failures
    such as DNS resolution errors or service startup delays.
    
    Args:
        host (str): Redis host. Defaults to REDIS_HOST env var or 'redis'.
        port (int): Redis port. Defaults to REDIS_PORT env var or 6379.
        db (int): Redis database number. Defaults to 0.
        max_retries (int): Maximum number of connection retries.
        backoff_factor (int): Multiplier for exponential backoff.
        
    Returns:
        redis.Redis: A connected Redis client instance.
        
    Raises:
        ConnectionError: If unable to connect after max_retries.
    """
    host = host or os.environ.get("REDIS_HOST", "redis")
    port = port or int(os.environ.get("REDIS_PORT", 6379))
    
    client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    
    retries = 0
    delay = 1
    
    while retries <= max_retries:
        try:
            # Ping the server to verify connection
            client.ping()
            logger.info(f"Successfully connected to Redis at {host}:{port}")
            return client
        except (ConnectionError, TimeoutError) as e:
            retries += 1
            if retries > max_retries:
                logger.error(f"Failed to connect to Redis at {host}:{port} after {max_retries} retries. Error: {e}")
                raise
            
            logger.warning(f"Redis connection failed (Attempt {retries}/{max_retries}): {e}. Retrying in {delay} seconds...")
            time.sleep(delay)
            delay *= backoff_factor

    return client