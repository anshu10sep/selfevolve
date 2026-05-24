import logging
from typing import List, Dict, Any, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from agents.skills.database.manage_connections import DatabaseConnectionManager
from agents.skills.database.handle_errors import handle_db_errors

logger = logging.getLogger(__name__)

@handle_db_errors
def execute_query(
    query: str, 
    params: Optional[Tuple] = None, 
    fetch: bool = True, 
    **db_kwargs
) -> Optional[List[Dict[str, Any]]]:
    """
    Execute a SQL query and return the results.
    
    Args:
        query (str): The SQL query to execute.
        params (tuple, optional): Parameters to substitute into the query.
        fetch (bool): Whether to fetch results (True for SELECT, False for INSERT/UPDATE/DELETE).
        **db_kwargs: Additional arguments for DatabaseConnectionManager.
        
    Returns:
        Optional[List[Dict[str, Any]]]: The query results as a list of dictionaries, or None if fetch=False.
    """
    with DatabaseConnectionManager(**db_kwargs) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            logger.debug(f"Executing query: {query}")
            cursor.execute(query, params)
            
            if fetch:
                results = cursor.fetchall()
                # Convert RealDictRow to standard dict
                return [dict(row) for row in results]
            else:
                conn.commit()
                return None

@handle_db_errors
def execute_many(
    query: str, 
    params_list: List[Tuple], 
    **db_kwargs
) -> None:
    """
    Execute a SQL query multiple times with different parameters.
    
    Args:
        query (str): The SQL query to execute.
        params_list (List[tuple]): A list of parameter tuples.
        **db_kwargs: Additional arguments for DatabaseConnectionManager.
    """
    with DatabaseConnectionManager(**db_kwargs) as conn:
        with conn.cursor() as cursor:
            logger.debug(f"Executing query {len(params_list)} times: {query}")
            cursor.executemany(query, params_list)
            conn.commit()

@handle_db_errors
def check_database_health(**db_kwargs) -> bool:
    """
    Check if the database is accessible and responding.
    Useful for readiness probes.
    
    Args:
        **db_kwargs: Additional arguments for DatabaseConnectionManager.
        
    Returns:
        bool: True if the database is healthy, False otherwise.
    """
    try:
        result = execute_query("SELECT 1 as health_check", fetch=True, **db_kwargs)
        if result and result[0].get('health_check') == 1:
            logger.info("Database health check passed.")
            return True
        return False
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False