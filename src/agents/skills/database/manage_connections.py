import time
import logging
import socket
import psycopg2
from psycopg2 import OperationalError

logger = logging.getLogger(__name__)

def get_database_connection(
    host: str = '127.0.0.1', 
    port: int = 5432, 
    dbname: str = 'selfevolve', 
    user: str = 'postgres', 
    password: str = '', 
    max_retries: int = 5, 
    backoff_factor: float = 2.0
):
    """
    Establish a connection to the PostgreSQL database with retry logic.
    This helps mitigate '[Errno 111] Connect call failed' errors when the DB is starting up.
    
    Args:
        host (str): Database host address.
        port (int): Database port.
        dbname (str): Database name.
        user (str): Database user.
        password (str): Database password.
        max_retries (int): Maximum number of connection retries.
        backoff_factor (float): Multiplier for exponential backoff.
        
    Returns:
        psycopg2.extensions.connection: A database connection object.
        
    Raises:
        OperationalError: If the connection fails after max_retries.
    """
    retries = 0
    delay = 1.0
    
    while retries <= max_retries:
        try:
            logger.info(f"Attempting to connect to database at {host}:{port} (Attempt {retries + 1}/{max_retries + 1})")
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=10
            )
            logger.info("Successfully connected to the database.")
            return conn
        except (OperationalError, socket.error) as e:
            logger.warning(f"Connection failed: {e}")
            if retries == max_retries:
                logger.error("Max retries reached. Could not connect to the database.")
                raise
            
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
            retries += 1
            delay *= backoff_factor

def close_connection(conn):
    """
    Safely close a database connection.
    
    Args:
        conn (psycopg2.extensions.connection): The database connection to close.
    """
    if conn is not None:
        try:
            if not conn.closed:
                conn.close()
                logger.info("Database connection closed.")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")

class DatabaseConnectionManager:
    """
    Context manager for database connections with built-in retry logic.
    """
    def __init__(
        self, 
        host: str = '127.0.0.1', 
        port: int = 5432, 
        dbname: str = 'selfevolve', 
        user: str = 'postgres', 
        password: str = '', 
        max_retries: int = 5
    ):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.max_retries = max_retries
        self.conn = None

    def __enter__(self):
        self.conn = get_database_connection(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            max_retries=self.max_retries
        )
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        close_connection(self.conn)