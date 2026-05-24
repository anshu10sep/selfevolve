import time
import logging
import redis
from typing import Optional, Any

logger = logging.getLogger(__name__)

class RedisConnectionManager:
    """
    Manages Redis connections with built-in retry logic and error handling.
    """
    
    def __init__(self, host: str = '127.0.0.1', port: int = 6379, db: int = 0, max_retries: int = 5, retry_delay: int = 2):
        """
        Initialize the Redis connection manager.
        
        Args:
            host (str): Redis server hostname.
            port (int): Redis server port.
            db (int): Redis database number.
            max_retries (int): Maximum number of connection retries.
            retry_delay (int): Delay between retries in seconds.
        """
        self.host = host
        self.port = port
        self.db = db
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client: Optional[redis.Redis] = None

    def get_connection(self) -> Optional[redis.Redis]:
        """
        Get a Redis connection, attempting to connect with retries if necessary.
        
        Returns:
            Optional[redis.Redis]: The Redis client instance, or None if connection failed.
        """
        if self._client is not None:
            try:
                self._client.ping()
                return self._client
            except redis.exceptions.ConnectionError:
                logger.warning("Existing Redis connection lost. Reconnecting...")
                self._client = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Attempting to connect to Redis at {self.host}:{self.port} (Attempt {attempt}/{self.max_retries})")
                client = redis.Redis(host=self.host, port=self.port, db=self.db, decode_responses=True)
                client.ping()
                logger.info("Successfully connected to Redis.")
                self._client = client
                return client
            except redis.exceptions.ConnectionError as e:
                logger.error(f"Redis connection failed: {e}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Max retries reached. Could not connect to Redis.")
                    
        return None

    def execute_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a Redis command safely using the managed connection.
        
        Args:
            command (str): The Redis command to execute (e.g., 'get', 'set').
            *args: Positional arguments for the command.
            **kwargs: Keyword arguments for the command.
            
        Returns:
            Any: The result of the Redis command, or None if execution failed.
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