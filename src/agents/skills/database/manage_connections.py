import logging
import os
from typing import Optional, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Manages connections to PostgreSQL and Redis databases.
    Includes robust error handling for connection failures to prevent application crashes
    when infrastructure services are down.
    """
    
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))
        
        self.pg_host = os.getenv("PG_HOST", "127.0.0.1")
        self.pg_port = int(os.getenv("PG_PORT", 5432))
        self.pg_user = os.getenv("PG_USER", "postgres")
        self.pg_password = os.getenv("PG_PASSWORD", "")
        self.pg_db = os.getenv("PG_DB", "trading_db")
        
        self._redis_client = None
        self._pg_conn = None

    def get_redis_connection(self) -> Optional[Any]:
        """Gets a Redis connection, handling connection errors gracefully."""
        if self._redis_client is None:
            try:
                import redis
                client = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=self.redis_db,
                    decode_responses=True
                )
                # Ping to verify connection
                client.ping()
                self._redis_client = client
                logger.info(f"Successfully connected to Redis at {self.redis_host}:{self.redis_port}")
            except ImportError:
                logger.error("Redis library is not installed. Run `pip install redis`.")
                return None
            except Exception as e:
                logger.error(f"Failed to connect to Redis at {self.redis_host}:{self.redis_port}. Is the service running? Error: {e}")
                return None
        return self._redis_client

    def get_pg_connection(self) -> Optional[Any]:
        """Gets a PostgreSQL connection, handling connection errors gracefully."""
        if self._pg_conn is None:
            try:
                import psycopg2
                from psycopg2 import OperationalError
                conn = psycopg2.connect(
                    host=self.pg_host,
                    port=self.pg_port,
                    user=self.pg_user,
                    password=self.pg_password,
                    dbname=self.pg_db
                )
                self._pg_conn = conn
                logger.info(f"Successfully connected to PostgreSQL at {self.pg_host}:{self.pg_port}")
            except ImportError:
                logger.error("psycopg2 library is not installed. Run `pip install psycopg2-binary`.")
                return None
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL at {self.pg_host}:{self.pg_port}. Is the service running? Error: {e}")
                return None
        return self._pg_conn

    def close_all(self):
        """Closes all active database connections."""
        if self._redis_client:
            try:
                self._redis_client.close()
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._redis_client = None
                
        if self._pg_conn:
            try:
                self._pg_conn.close()
            except Exception as e:
                logger.warning(f"Error closing PostgreSQL connection: {e}")
            finally:
                self._pg_conn = None