import logging
import time
from typing import Optional, Any
import redis
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)

class RedisConnectionManager:
    """
    Manages Redis connections with built-in retry logic and error handling.
    """
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0, max_retries: int = 3):
        """
        Initialize the Redis connection manager.
        
        Args:
            host: Redis server host.
            port: Redis server port.
            db: Redis database number.
            max_retries: Maximum number of connection retries.
        """
        self.host = host
        self.port = port
        self.db = db
        self.max_retries = max_retries
        self._client: Optional[redis.Redis] = None
        
    def get_connection(self) -> Optional[redis.Redis]:
        """
        Get a Redis connection, attempting to reconnect if necessary.
        
        Returns:
            A Redis client instance, or None if connection fails after retries.
        """
        if self._client is not None:
            try:
                self._client.ping()
                return self._client
            except (ConnectionError, TimeoutError):
                logger.warning("Existing Redis connection lost. Attempting to reconnect...")
                self._client = None
                
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Connecting to Redis at {self.host}:{self.port} (Attempt {attempt}/{self.max_retries})")
                client = redis.Redis(host=self.host, port=self.port, db=self.db, decode_responses=True)
                client.ping()
                self._client = client
                logger.info("Successfully connected to Redis.")
                return self._client
            except ConnectionError as e:
                logger.error(f"Redis connection error on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                logger.error(f"Unexpected error connecting to Redis: {e}")
                break
                
        logger.critical(f"Failed to connect to Redis after {self.max_retries} attempts. Ensure the Redis service is running.")
        return None
        
    def execute_command(self, command: str, *args, **kwargs) -> Any:
        """
        Execute a Redis command safely using the managed connection.
        
        Args:
            command: The Redis command to execute (e.g., 'get', 'set').
            *args: Positional arguments for the command.
            **kwargs: Keyword arguments for the command.
            
        Returns:
            The result of the Redis command, or None if execution fails.
        """
        client = self.get_connection()
        if not client:
            logger.error(f"Cannot execute command '{command}': No Redis connection available.")
            return None
            
        try:
            method = getattr(client, command)
            return method(*args, **kwargs)
        except AttributeError:
            logger.error(f"Invalid Redis command: {command}")
            return None
        except Exception as e:
            logger.error(f"Error executing Redis command '{command}': {e}")
            return None

def get_redis_client(host: str = 'localhost', port: int = 6379, db: int = 0) -> Optional[redis.Redis]:
    """
    Helper function to get a managed Redis client.
    
    Args:
        host: Redis server host.
        port: Redis server port.
        db: Redis database number.
        
    Returns:
        A connected Redis client, or None if connection fails.
    """
    manager = RedisConnectionManager(host=host, port=port, db=db)
    return manager.get_connection()