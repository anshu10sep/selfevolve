import sqlite3
import logging
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.
    """
    if db_path is None:
        # Default to a data directory in the project root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        db_path = os.path.join(base_dir, "data", "trading_system.db")
        
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_top_20_stocks(db_path: str = None) -> List[Dict[str, Any]]:
    """
    Fetches the current top 20 selected stocks from the database.
    
    Args:
        db_path (str, optional): Path to the SQLite database.
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing stock information.
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        
        # Ensure table exists to prevent errors on fresh installations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS selected_stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                rank INTEGER,
                selection_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                strategy TEXT,
                score REAL,
                status TEXT DEFAULT 'active'
            )
        """)
        
        # Query to get the top 20 active/selected stocks
        # We order by rank (ascending, 1 is best) and score (descending)
        query = """
            SELECT symbol, rank, selection_date, strategy, score, status
            FROM selected_stocks
            WHERE status IN ('active', 'selected', 'pending')
            ORDER BY rank ASC, score DESC, selection_date DESC
            LIMIT 20
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        stocks = [dict(row) for row in rows]
        conn.close()
        
        logger.info(f"Successfully fetched {len(stocks)} top stocks from database.")
        return stocks
        
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching top 20 stocks: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while fetching top 20 stocks: {e}")
        return []
