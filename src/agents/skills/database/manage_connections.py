import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

async def connect_with_retry(
    connect_func: Callable[..., Any],
    address: str,
    max_retries: int = 5,
    base_delay: float = 1.0,
    **kwargs: Any
) -> Any:
    """
    Attempt to establish a connection using the provided connect function,
    with exponential backoff retry logic.

    Args:
        connect_func: The async function to call to establish the connection.
        address: The address being connected to (for logging).
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for exponential backoff.
        **kwargs: Additional arguments to pass to connect_func.

    Returns:
        The connection object returned by connect_func.

    Raises:
        OSError: If the connection fails after all retries.
    """
    retries = 0
    while True:
        try:
            logger.info(f"Attempting to connect to {address} (Attempt {retries + 1}/{max_retries + 1})")
            connection = await connect_func(**kwargs)
            logger.info(f"Successfully connected to {address}")
            return connection
        except OSError as e:
            retries += 1
            if retries > max_retries:
                logger.error(f"Failed to connect to {address} after {max_retries} retries. Error: {e}")
                # Re-raise the original OSError or a wrapped one
                raise OSError(getattr(e, 'errno', None), f"Connect call failed {address}") from e
            
            delay = base_delay * (2 ** (retries - 1))
            logger.warning(f"Connection to {address} failed. Retrying in {delay} seconds... Error: {e}")
            await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"Unexpected error connecting to {address}: {e}")
            raise

class ConnectionManager:
    """
    Manages database and service connections with robust error handling.
    """
    def __init__(self):
        self.connections: Dict[str, Any] = {}

    async def get_connection(self, name: str, connect_func: Callable[..., Any], address: str, **kwargs: Any) -> Any:
        """
        Get an existing connection or create a new one with retry logic.
        
        Args:
            name: Identifier for the connection.
            connect_func: The async function to call to establish the connection.
            address: The address being connected to.
            **kwargs: Additional arguments to pass to connect_func.
            
        Returns:
            The established connection.
        """
        if name in self.connections:
            return self.connections[name]
        
        connection = await connect_with_retry(connect_func, address, **kwargs)
        self.connections[name] = connection
        return connection

    def close_connection(self, name: str) -> None:
        """
        Close and remove a connection.
        
        Args:
            name: Identifier for the connection to close.
        """
        if name in self.connections:
            conn = self.connections.pop(name)
            if hasattr(conn, 'close') and callable(conn.close):
                try:
                    # Handle both async and sync close methods
                    if asyncio.iscoroutinefunction(conn.close):
                        asyncio.create_task(conn.close())
                    else:
                        conn.close()
                except Exception as e:
                    logger.error(f"Error closing connection {name}: {e}")

    def close_all(self) -> None:
        """
        Close all managed connections.
        """
        for name in list(self.connections.keys()):
            self.close_connection(name)