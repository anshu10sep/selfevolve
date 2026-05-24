import logging
import json
from typing import Any, Optional
from .manage_connections import get_redis_client
from .handle_errors import handle_redis_errors

logger = logging.getLogger(__name__)

class RedisManager:
    """
    A class to manage Redis queries and operations with built-in error handling
    and connection retries.
    """
    def __init__(self, host: str = None, port: int = None, db: int = 0):
        """
        Initialize the RedisManager.
        
        Args:
            host (str, optional): Redis host.
            port (int, optional): Redis port.
            db (int, optional): Redis database number.
        """
        self.client = get_redis_client(host=host, port=port, db=db)

    @handle_redis_errors(default_return=False)
    def set_value(self, key: str, value: Any, expire: int = None) -> bool:
        """
        Set a value in Redis. Automatically serializes dicts and lists to JSON.
        
        Args:
            key (str): The key to set.
            value (Any): The value to store.
            expire (int, optional): Expiration time in seconds.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
            
        if expire:
            return bool(self.client.setex(key, expire, value))
        return bool(self.client.set(key, value))

    @handle_redis_errors(default_return=None)
    def get_value(self, key: str) -> Optional[Any]:
        """
        Get a value from Redis. Automatically deserializes JSON strings.
        
        Args:
            key (str): The key to retrieve.
            
        Returns:
            Optional[Any]: The retrieved value, or None if not found or error occurs.
        """
        value = self.client.get(key)
        if not value:
            return None
            
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    @handle_redis_errors(default_return=False)
    def delete_value(self, key: str) -> bool:
        """
        Delete a value from Redis.
        
        Args:
            key (str): The key to delete.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        return bool(self.client.delete(key))