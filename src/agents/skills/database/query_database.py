import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from .manage_connections import DatabaseConnectionManager
from .handle_errors import with_error_handling

logger = logging.getLogger(__name__)

class DatabaseQueryExecutor:
    """
    Executes SQL queries against the database using a managed connection.
    """
    def __init__(self, connection_manager: Optional[DatabaseConnectionManager] = None):
        self.connection_manager = connection_manager or DatabaseConnectionManager()

    @with_error_handling
    def execute_query(self, query: str, params: Optional[Union[Tuple, Dict[str, Any]]] = None, fetch: bool = False) -> Optional[List[Tuple]]:
        """
        Execute a single SQL query.
        
        :param query: SQL query string
        :param params: Tuple or dict of parameters for the query
        :param fetch: Boolean indicating if results should be fetched (for SELECT queries)
        :return: Fetched results if fetch=True, else None
        """
        conn = self.connection_manager.get_connection()
        with conn.cursor() as cursor:
            logger.debug(f"Executing query: {query}")
            cursor.execute(query, params)
            
            if fetch:
                results = cursor.fetchall()
                return results
            else:
                conn.commit()
                return None

    @with_error_handling
    def execute_many(self, query: str, params_list: List[Union[Tuple, Dict[str, Any]]]) -> None:
        """
        Execute a SQL query multiple times with different parameters (e.g., for bulk inserts).
        
        :param query: SQL query string
        :param params_list: List of tuples or dicts of parameters
        """
        conn = self.connection_manager.get_connection()
        with conn.cursor() as cursor:
            logger.debug(f"Executing executemany query: {query} with {len(params_list)} parameter sets")
            cursor.executemany(query, params_list)
            conn.commit()
            
    @with_error_handling
    def fetch_one(self, query: str, params: Optional[Union[Tuple, Dict[str, Any]]] = None) -> Optional[Tuple]:
        """
        Execute a query and fetch a single row.
        
        :param query: SQL query string
        :param params: Tuple or dict of parameters for the query
        :return: A single row as a tuple, or None if no results
        """
        conn = self.connection_manager.get_connection()
        with conn.cursor() as cursor:
            logger.debug(f"Executing fetch_one query: {query}")
            cursor.execute(query, params)
            return cursor.fetchone()