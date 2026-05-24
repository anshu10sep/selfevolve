import os
import time
import logging

try:
    import psycopg2
    from psycopg2 import OperationalError
except ImportError:
    raise ImportError("psycopg2 is required for database connections. Please install it using 'pip install psycopg2-binary'")

logger = logging.getLogger(__name__)

class DatabaseConnectionManager:
    """
    Manages database connections, providing robust retry logic and connection pooling capabilities.
    """
    def __init__(self, host=None, port=None, dbname=None, user=None, password=None):
        self.host = host or os.getenv("DB_HOST", "127.0.0.1")
        self.port = port or os.getenv("DB_PORT", "5432")
        self.dbname = dbname or os.getenv("DB_NAME", "selfevolve")
        self.user = user or os.getenv("DB_USER", "postgres")
        self.password = password or os.getenv("DB_PASSWORD", "postgres")
        self.connection = None

    def connect(self, max_retries=7, initial_retry_delay=2):
        """
        Attempt to connect to the database with exponential backoff retry logic.
        This is specifically designed to handle [Errno 111] Connection refused errors
        during system startup when the database might not be fully ready.
        
        :param max_retries: Maximum number of connection attempts
        :param initial_retry_delay: Initial delay between retries in seconds
        :return: psycopg2 connection object
        """
        retries = 0
        retry_delay = initial_retry_delay
        
        while retries < max_retries:
            try:
                logger.info(f"Attempting to connect to database at {self.host}:{self.port} (Attempt {retries + 1}/{max_retries})")
                self.connection = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    dbname=self.dbname,
                    user=self.user,
                    password=self.password
                )
                logger.info("Successfully connected to the database.")
                return self.connection
            except OperationalError as e:
                logger.warning(f"Database connection failed: {e}")
                retries += 1
                if retries < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Max retries ({max_retries}) reached. Could not connect to the database.")
                    raise ConnectionError(
                        f"Failed to connect to database at {self.host}:{self.port} after {max_retries} attempts. "
                        f"Original error: {e}"
                    ) from e
            except Exception as e:
                logger.error(f"Unexpected error during database connection: {e}")
                raise

    def disconnect(self):
        """
        Safely close the database connection.
        """
        if self.connection:
            try:
                self.connection.close()
                logger.info("Database connection closed gracefully.")
            except Exception as e:
                logger.error(f"Error while closing database connection: {e}")
            finally:
                self.connection = None

    def get_connection(self):
        """
        Get the current database connection, or create a new one if it doesn't exist or is closed.
        
        :return: psycopg2 connection object
        """
        if not self.connection or self.connection.closed != 0:
            return self.connect()
        return self.connection